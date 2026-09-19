"""Emissão de NF-e: rascunho, transmissão para a SEFAZ e cancelamento.

Rotas
-----
GET    /api/nfe/series                 numeração das séries da empresa
POST   /api/nfe/series                 cria/ajusta uma série
GET    /api/nfe/preparo                o que já está pronto e o que falta para emitir
POST   /api/nfe/rascunho               cria a nota (avulsa ou a partir de um contrato de venda)
GET    /api/nfe/{id}                   abre o rascunho para edição
PUT    /api/nfe/{id}                   salva o rascunho
DELETE /api/nfe/{id}                   apaga o rascunho
GET    /api/nfe/{id}/previa            DANFE de conferência (sem valor fiscal)
POST   /api/nfe/{id}/transmitir        assina e envia para a SEFAZ
POST   /api/nfe/{id}/cancelar          evento de cancelamento
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import danfe, dfe as motor, emissao as nfe, notas as regras, rejeicoes
from ..database import get_db
from ..deps import acesso_liberado, validar_empresa
from ..models import (
    Contrato,
    Empresa,
    Nota,
    NotaItem,
    NotaPagamento,
    Parceiro,
    Produto,
    SerieNota,
    Usuario,
)
from ..schemas import CancelarNotaIn, NotaEmitidaIn, SerieNotaIn, TransmitirNotaIn
from ..utils import dinheiro, parse_data, serializar
from .dfe import _abrir_certificado, _certificado_da_empresa

router = APIRouter(prefix="/api/nfe", tags=["nfe"])


# --------------------------------------------------------------------------- #
# Numeração
# --------------------------------------------------------------------------- #
def _serie(db: Session, empresa_id: int, serie: str, ambiente: str,
           criar: bool = True) -> SerieNota | None:
    linha = (
        db.query(SerieNota)
        .filter(SerieNota.empresa_id == empresa_id, SerieNota.modelo == "55",
                SerieNota.serie == str(serie), SerieNota.ambiente == ambiente)
        .first()
    )
    if linha is None and criar:
        linha = SerieNota(empresa_id=empresa_id, modelo="55", serie=str(serie),
                          ambiente=ambiente, proximo_numero=1)
        db.add(linha)
        db.flush()
    return linha


@router.get("/series")
def listar_series(empresa_id: int, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    linhas = (
        db.query(SerieNota)
        .filter(SerieNota.empresa_id == empresa_id)
        .order_by(SerieNota.ambiente, SerieNota.serie)
        .all()
    )
    return [serializar(l, extras={
        "ambiente_nome": motor.AMBIENTES.get(l.ambiente, "Produção")}) for l in linhas]


@router.post("/series")
def salvar_serie(dados: SerieNotaIn, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(acesso_liberado)):
    """Cria a série ou acerta o próximo número (para continuar a numeração do sistema antigo)."""
    validar_empresa(db, dados.empresa_id, usuario)
    if usuario.perfil not in ("ADMIN", "MASTER"):
        raise HTTPException(403, "Apenas administradores mexem na numeração das notas.")
    ambiente = "2" if str(dados.ambiente) == "2" else "1"
    linha = _serie(db, dados.empresa_id, dados.serie, ambiente)
    if dados.proximo_numero is not None:
        if dados.proximo_numero < 1:
            raise HTTPException(400, "O próximo número tem de ser 1 ou mais.")
        linha.proximo_numero = int(dados.proximo_numero)
    linha.descricao = (dados.descricao or "").strip() or None
    linha.ativo = dados.ativo
    db.commit()
    db.refresh(linha)
    return serializar(linha)


def _reservar_numero(db: Session, empresa_id: int, serie: str, ambiente: str) -> int:
    """Pega o próximo número da série e já avança o contador.

    Só é chamado na hora de transmitir: rascunho não gasta numeração.
    """
    linha = _serie(db, empresa_id, serie, ambiente)
    numero = int(linha.proximo_numero or 1)
    linha.proximo_numero = numero + 1
    db.flush()
    return numero


# --------------------------------------------------------------------------- #
# O que falta para poder emitir
# --------------------------------------------------------------------------- #
@router.get("/preparo")
def preparo(empresa_id: int, db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    """Lista o que ainda falta para a empresa conseguir emitir nota."""
    empresa = validar_empresa(db, empresa_id, usuario)
    cert = _certificado_da_empresa(db, empresa_id)
    pendencias = []
    if not motor.so_numeros(empresa.cnpj):
        pendencias.append("CNPJ da empresa")
    if not (empresa.inscricao_estadual or "").strip():
        pendencias.append("Inscrição estadual da empresa")
    if not (empresa.codigo_municipio or "").strip():
        pendencias.append("Código do município (IBGE) da empresa")
    if not (empresa.uf or "").strip():
        pendencias.append("UF da empresa")
    if not (empresa.logradouro or "").strip():
        pendencias.append("Endereço da empresa")
    if not cert:
        pendencias.append("Certificado digital A1 (aba Certificado do DF-e)")
    elif cert.valido_ate and cert.valido_ate.date() < date.today():
        pendencias.append("Certificado digital vencido")

    return {
        "pronto": not pendencias,
        "pendencias": pendencias,
        "empresa": {
            "razao_social": empresa.razao_social,
            "cnpj": motor.formatar_documento(empresa.cnpj),
            "uf": empresa.uf,
            "crt": empresa.crt or "1",
            "crt_nome": nfe.CRT.get(empresa.crt or "1", ""),
            "codigo_municipio": empresa.codigo_municipio,
        },
        "ambiente_certificado": cert.ambiente if cert else None,
        "series": [serializar(s) for s in db.query(SerieNota)
                   .filter(SerieNota.empresa_id == empresa_id).all()],
        "finalidades": [{"codigo": c, "nome": n} for c, n in nfe.FINALIDADES.items()],
        "modalidades_frete": [{"codigo": c, "nome": n}
                              for c, n in nfe.MODALIDADES_FRETE.items()],
    }


# --------------------------------------------------------------------------- #
# Rascunho
# --------------------------------------------------------------------------- #
def _nota_emitida(db: Session, nota_id: int, usuario: Usuario) -> Nota:
    nota = db.get(Nota, nota_id)
    if not nota:
        raise HTTPException(404, "Nota não encontrada.")
    validar_empresa(db, nota.empresa_id, usuario)
    if nota.origem != "EMITIDA":
        raise HTTPException(400, "Esta nota veio da SEFAZ; ela não é emitida pelo AgroDock.")
    return nota


def _item_do_produto(db: Session, empresa_id: int, produto_id: int | None) -> Produto | None:
    if not produto_id:
        return None
    produto = db.get(Produto, produto_id)
    if not produto or produto.empresa_id != empresa_id:
        raise HTTPException(400, "Produto inválido.")
    return produto


def _aplicar_itens(db: Session, nota: Nota, itens: list) -> None:
    """Grava os itens do rascunho, puxando os dados fiscais do cadastro do produto."""
    nota.itens.clear()
    db.flush()
    for numero, entrada in enumerate(itens, start=1):
        produto = _item_do_produto(db, nota.empresa_id, entrada.produto_id)
        quantidade = float(entrada.quantidade or 0)
        unitario = float(entrada.valor_unitario or 0)
        total = round(quantidade * unitario - float(entrada.desconto or 0) + 1e-9, 2)
        base = float(entrada.icms_base) if entrada.icms_base is not None else total
        aliquota = float(entrada.icms_aliquota if entrada.icms_aliquota is not None
                         else (produto.aliquota_icms if produto else 0) or 0)
        cst = (entrada.icms_cst or (produto.cst_icms if produto else None) or "").strip()
        nota.itens.append(NotaItem(
            numero=numero,
            codigo=(entrada.codigo or (produto.codigo if produto else "") or str(numero))[:60],
            gtin=(entrada.gtin or (produto.gtin if produto else "") or "")[:14],
            descricao=(entrada.descricao or (produto.nome if produto else "") or "ITEM")[:200],
            ncm=(entrada.ncm or (produto.ncm if produto else "") or "")[:10],
            cest=(entrada.cest or (produto.cest if produto else "") or "")[:9],
            cfop=(entrada.cfop or (produto.cfop_padrao if produto else "") or "")[:5],
            unidade=(entrada.unidade or (produto.unidade_comercial if produto else "")
                     or "UN")[:10],
            quantidade=quantidade,
            valor_unitario=unitario,
            valor_total=total,
            desconto=dinheiro(entrada.desconto),
            frete=dinheiro(entrada.frete),
            icms_cst=cst[:3],
            icms_base=dinheiro(base),
            icms_aliquota=aliquota,
            icms_valor=dinheiro(base * aliquota / 100) if cst not in ("40", "41", "51", "60") else 0,
            icms_reducao=float(produto.reducao_base_icms or 0) if produto else 0,
            origem_mercadoria=(entrada.origem_mercadoria
                               or (produto.origem if produto else None) or "0")[:1],
            cst_pis=(entrada.cst_pis or (produto.cst_pis if produto else None) or "")[:2] or None,
            aliquota_pis=float(produto.aliquota_pis or 0) if produto else 0,
            pis_valor=dinheiro(total * float(produto.aliquota_pis or 0) / 100) if produto else 0,
            cst_cofins=(entrada.cst_cofins
                        or (produto.cst_cofins if produto else None) or "")[:2] or None,
            aliquota_cofins=float(produto.aliquota_cofins or 0) if produto else 0,
            cofins_valor=(dinheiro(total * float(produto.aliquota_cofins or 0) / 100)
                          if produto else 0),
            cst_ipi=(produto.cst_ipi if produto else None),
            aliquota_ipi=float(produto.aliquota_ipi or 0) if produto else 0,
            produto_id=produto.id if produto else None,
        ))
    db.flush()


def _aplicar_parcelas(db: Session, nota: Nota, parcelas: list) -> None:
    for pagamento in list(nota.pagamentos):
        db.delete(pagamento)
    db.flush()
    for numero, parcela in enumerate(parcelas, start=1):
        nota.pagamentos.append(NotaPagamento(
            origem="DUPLICATA", codigo="15", descricao="Duplicata",
            numero=str(parcela.numero or numero), vencimento=parcela.vencimento,
            valor=dinheiro(parcela.valor),
        ))
    db.flush()


def _cabecalho(nota: Nota, dados: NotaEmitidaIn, db: Session) -> None:
    empresa = db.get(Empresa, nota.empresa_id)
    parceiro = db.get(Parceiro, dados.parceiro_id) if dados.parceiro_id else None
    if dados.parceiro_id and (not parceiro or parceiro.empresa_id != nota.empresa_id):
        raise HTTPException(400, "Cliente inválido.")
    nota.parceiro_id = dados.parceiro_id
    # o ambiente é escolha do usuário na tela: homologação (2) ou produção (1).
    # Sem isso, salvar o rascunho jogava a nota de volta para o ambiente do certificado.
    if dados.ambiente:
        nota.ambiente = "2" if str(dados.ambiente) == "2" else "1"
    nota.natureza_operacao = (dados.natureza_operacao or "VENDA DE MERCADORIA")[:120]
    nota.tipo_operacao = dados.tipo_operacao or "1"
    nota.finalidade = dados.finalidade or "1"
    nota.serie = str(dados.serie or "1")[:3]
    nota.data_emissao = (datetime.combine(dados.data_emissao, datetime.now().time())
                         if dados.data_emissao else nota.data_emissao or datetime.utcnow())
    nota.cfop = (dados.cfop or "")[:5] or None
    nota.frete_modalidade = (dados.frete_modalidade or "9")[:1]
    nota.transportadora_id = dados.transportadora_id
    nota.placa_veiculo = (dados.placa_veiculo or "")[:8] or None
    nota.uf_veiculo = (dados.uf_veiculo or "")[:2] or None
    nota.volumes = dados.volumes
    nota.especie_volume = (dados.especie_volume or "")[:30] or None
    nota.peso_liquido = float(dados.peso_liquido or 0)
    nota.peso_bruto = float(dados.peso_bruto or 0)
    nota.informacoes_complementares = (dados.informacoes_complementares or "").strip() or None
    if not nota.informacoes_complementares and empresa and empresa.texto_nota:
        nota.informacoes_complementares = empresa.texto_nota
    nota.destinatario_cnpj = parceiro.cpf_cnpj if parceiro else None
    nota.destinatario_nome = parceiro.nome if parceiro else None
    if empresa:
        nota.emitente_cnpj = motor.so_numeros(empresa.cnpj)
        nota.emitente_nome = empresa.razao_social
        nota.emitente_ie = empresa.inscricao_estadual
        nota.emitente_uf = empresa.uf


@router.post("/rascunho")
def criar_rascunho(dados: NotaEmitidaIn, db: Session = Depends(get_db),
                   usuario: Usuario = Depends(acesso_liberado)):
    """Cria a nota em rascunho. `contrato_id` puxa cliente, produto e valores do contrato."""
    empresa = validar_empresa(db, dados.empresa_id, usuario)
    cert = _certificado_da_empresa(db, dados.empresa_id)
    ambiente = dados.ambiente or (cert.ambiente if cert else "2")

    nota = Nota(
        empresa_id=dados.empresa_id,
        chave=f"RASCUNHO-{int(datetime.utcnow().timestamp() * 1000)}",
        origem="EMITIDA",
        status_emissao="RASCUNHO",
        ambiente="2" if str(ambiente) == "2" else "1",
        modelo="55",
        tipo="NFE",
        resumo=False,
        situacao="AUTORIZADA",
        data_emissao=datetime.utcnow(),
    )
    db.add(nota)
    db.flush()

    itens = list(dados.itens or [])
    if dados.contrato_id:
        contrato = db.get(Contrato, dados.contrato_id)
        if not contrato or contrato.empresa_id != dados.empresa_id:
            raise HTTPException(400, "Contrato inválido.")
        if contrato.tipo != "VENDA":
            raise HTTPException(
                400, "Só contratos de venda viram nota fiscal de saída aqui.")
        nota.contrato_id = contrato.id
        if not dados.parceiro_id:
            dados.parceiro_id = contrato.comprador_id
        if not dados.natureza_operacao:
            dados.natureza_operacao = "VENDA DE MERCADORIA"
        if not itens:
            from ..schemas import ItemNotaIn

            itens = [ItemNotaIn(
                produto_id=contrato.produto_id,
                descricao=contrato.produto or "CAFE",
                unidade=contrato.unidade or "SC",
                quantidade=float(contrato.quantidade or 0),
                valor_unitario=float(contrato.preco_unitario or 0),
            )]
        if not dados.informacoes_complementares:
            dados.informacoes_complementares = f"Contrato {contrato.numero}"

    _cabecalho(nota, dados, db)
    _aplicar_itens(db, nota, itens)
    _aplicar_parcelas(db, nota, dados.parcelas or [])
    nota.valor_total = dinheiro(sum(float(i.valor_total or 0) for i in nota.itens))
    nota.valor_produtos = nota.valor_total
    db.commit()
    db.refresh(nota)
    return _ficha(db, nota)


@router.put("/{nota_id}")
def salvar_rascunho(nota_id: int, dados: NotaEmitidaIn, db: Session = Depends(get_db),
                    usuario: Usuario = Depends(acesso_liberado)):
    nota = _nota_emitida(db, nota_id, usuario)
    if nota.status_emissao != "RASCUNHO":
        raise HTTPException(
            400, "Esta nota já foi transmitida — não dá mais para mexer nela.")
    dados.empresa_id = nota.empresa_id
    _cabecalho(nota, dados, db)
    _aplicar_itens(db, nota, list(dados.itens or []))
    _aplicar_parcelas(db, nota, dados.parcelas or [])
    nota.valor_total = dinheiro(sum(float(i.valor_total or 0) for i in nota.itens))
    nota.valor_produtos = nota.valor_total
    db.commit()
    db.refresh(nota)
    return _ficha(db, nota)


@router.delete("/{nota_id}")
def excluir_rascunho(nota_id: int, db: Session = Depends(get_db),
                     usuario: Usuario = Depends(acesso_liberado)):
    nota = _nota_emitida(db, nota_id, usuario)
    if nota.status_emissao not in ("RASCUNHO", "REJEITADA"):
        raise HTTPException(
            400, "Só dá para apagar rascunho ou nota rejeitada. Nota autorizada se cancela.")
    db.delete(nota)
    db.commit()
    return {"ok": True}


def _ficha(db: Session, nota: Nota) -> dict:
    empresa = db.get(Empresa, nota.empresa_id)
    return {
        "nota": serializar(nota, exclude={"xml"}, extras={
            "chave_formatada": motor.formatar_chave(nota.chave)
            if not nota.chave.startswith("RASCUNHO") else "",
            "parceiro_nome": nota.parceiro.nome if nota.parceiro else None,
            "ambiente_nome": motor.AMBIENTES.get(nota.ambiente or "2", ""),
            "crt": empresa.crt if empresa else "1",
            "pode_editar": nota.status_emissao == "RASCUNHO",
            "pode_cancelar": nota.status_emissao == "AUTORIZADA",
            # a última recusa continua explicada quando a nota é reaberta
            "erro": rejeicoes.explicar(nota.codigo_sefaz, nota.mensagem_sefaz)
            if nota.mensagem_sefaz and nota.status_emissao != "AUTORIZADA" else None,
        }),
        "itens": [serializar(i) for i in nota.itens],
        "parcelas": [serializar(p) for p in nota.pagamentos if p.origem == "DUPLICATA"],
    }


@router.get("/{nota_id}")
def abrir(nota_id: int, db: Session = Depends(get_db),
          usuario: Usuario = Depends(acesso_liberado)):
    return _ficha(db, _nota_emitida(db, nota_id, usuario))


# --------------------------------------------------------------------------- #
# Prévia, transmissão e cancelamento
# --------------------------------------------------------------------------- #
def _montar(db: Session, nota: Nota, numero: int) -> tuple[str, str, float]:
    empresa = db.get(Empresa, nota.empresa_id)
    cabecalho = {
        "natureza_operacao": nota.natureza_operacao,
        "tipo_operacao": nota.tipo_operacao or "1",
        "finalidade": nota.finalidade or "1",
        "consumidor_final": "0",
        "presenca": "9",
        "ambiente": nota.ambiente or "2",
        "destinatario_uf": nota.parceiro.uf if nota.parceiro else empresa.uf,
        "frete_modalidade": nota.frete_modalidade or "9",
        "placa_veiculo": nota.placa_veiculo,
        "uf_veiculo": nota.uf_veiculo,
        "volumes": nota.volumes,
        "especie_volume": nota.especie_volume,
        "peso_liquido": nota.peso_liquido,
        "peso_bruto": nota.peso_bruto,
        "informacoes_complementares": nota.informacoes_complementares,
    }
    duplicatas = [p for p in nota.pagamentos if p.origem == "DUPLICATA"]
    try:
        return nfe.montar_nfe(
            empresa, cabecalho, list(nota.itens), nota.parceiro, nota.transportadora,
            duplicatas, list(nota.pagamentos), numero, nota.serie or "1",
            nota.data_emissao,
        )
    except nfe.ErroEmissao as erro:
        raise HTTPException(400, str(erro)) from None


@router.get("/{nota_id}/previa")
def previa(nota_id: int, db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    """DANFE de conferência do rascunho — não vale como documento fiscal."""
    from fastapi.responses import HTMLResponse

    nota = _nota_emitida(db, nota_id, usuario)
    empresa = db.get(Empresa, nota.empresa_id)
    if nota.xml:
        html = danfe.gerar(nota.xml, empresa.razao_social if empresa else "")
    else:
        inf, _chave, _total = _montar(db, nota, int(nota.numero or 0) or 1)
        html = danfe.gerar(f'<NFe xmlns="{nfe.NS}">{inf}</NFe>',
                           empresa.razao_social if empresa else "")
        html = html.replace(
            '<div class="folha">',
            '<div class="folha"><div class="tarja">PRÉVIA — SEM VALOR FISCAL</div>', 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@router.post("/{nota_id}/transmitir")
def transmitir(nota_id: int, dados: TransmitirNotaIn, db: Session = Depends(get_db),
               usuario: Usuario = Depends(acesso_liberado)):
    """Assina a nota e envia para a SEFAZ. É o ato que gasta o número da série."""
    nota = _nota_emitida(db, nota_id, usuario)
    if nota.status_emissao == "AUTORIZADA":
        raise HTTPException(400, "Esta nota já está autorizada.")
    empresa = db.get(Empresa, nota.empresa_id)
    cert, chave_privada, certificado, cadeia = _abrir_certificado(db, nota.empresa_id)
    ambiente = nota.ambiente or cert.ambiente or "2"
    if ambiente == "1" and not dados.confirmo_producao:
        raise HTTPException(
            400,
            "Esta nota vai para PRODUÇÃO e passa a valer de verdade. Marque a confirmação "
            "para seguir, ou troque para homologação enquanto estiver testando.",
        )

    numero = _reservar_numero(db, nota.empresa_id, nota.serie or "1", ambiente)
    inf, chave, total = _montar(db, nota, numero)
    assinada = nfe.assinar_nfe(inf, chave_privada, certificado)

    nota.numero = str(numero)
    nota.chave = chave
    nota.valor_total = dinheiro(total)
    nota.status_emissao = "ENVIADA"
    nota.enviada_em = datetime.utcnow()
    db.flush()

    try:
        retorno = nfe.transmitir(chave_privada, certificado, cadeia, empresa.uf,
                                 ambiente, assinada)
    except nfe.ErroEmissao as erro:
        # não deu para falar com a SEFAZ: a nota fica como rascunho e o número volta
        nota.status_emissao = "RASCUNHO"
        nota.chave = f"RASCUNHO-{nota.id}"
        nota.numero = None
        nota.codigo_sefaz = None
        nota.mensagem_sefaz = str(erro)[:300]
        serie = _serie(db, nota.empresa_id, nota.serie or "1", ambiente)
        serie.proximo_numero = numero
        db.commit()
        db.refresh(nota)
        # 200 com ok=False: a tela mostra o painel de erro explicado, não um toast que some
        return {
            "ok": False,
            "codigo": "",
            "mensagem": str(erro),
            "erro": rejeicoes.explicar_falha(str(erro)),
            "nota": _ficha(db, nota)["nota"],
        }

    nota.codigo_sefaz = (retorno["codigo"] or "")[:5]
    nota.mensagem_sefaz = (retorno["mensagem"] or "")[:300]
    nota.recibo = (retorno["recibo"] or "")[:20]
    if retorno["autorizada"]:
        nota.status_emissao = "AUTORIZADA"
        nota.protocolo = retorno["protocolo"]
        nota.data_autorizacao = retorno["autorizada_em"]
        nota.xml = retorno["xml"]
        nota.esquema = "procNFe_v4.00"
        nota.situacao = "AUTORIZADA"
    else:
        nota.status_emissao = "REJEITADA"
        nota.situacao = "DENEGADA" if retorno["denegada"] else "AUTORIZADA"
        # rejeitada: o número é devolvido para não abrir buraco na sequência
        if not retorno["denegada"]:
            serie = _serie(db, nota.empresa_id, nota.serie or "1", ambiente)
            if serie.proximo_numero == numero + 1:
                serie.proximo_numero = numero
            nota.numero = None
            nota.chave = f"RASCUNHO-{nota.id}"
            nota.status_emissao = "RASCUNHO"
    db.commit()
    db.refresh(nota)

    return {
        "ok": retorno["autorizada"],
        "codigo": retorno["codigo"],
        "mensagem": (
            f"Nota {numero} autorizada pela SEFAZ (protocolo {retorno['protocolo']})."
            if retorno["autorizada"]
            else f"A SEFAZ não autorizou ({retorno['codigo']}): {retorno['mensagem']}"
        ),
        # o que deu errado, explicado e com o lugar do conserto
        "erro": None if retorno["autorizada"] else {
            **rejeicoes.explicar(retorno["codigo"], retorno["mensagem"]),
            "denegada": retorno["denegada"],
        },
        "nota": _ficha(db, nota)["nota"],
    }


@router.post("/{nota_id}/cancelar")
def cancelar(nota_id: int, dados: CancelarNotaIn, db: Session = Depends(get_db),
             usuario: Usuario = Depends(acesso_liberado)):
    """Cancela na SEFAZ uma nota que ela autorizou (evento 110111)."""
    nota = _nota_emitida(db, nota_id, usuario)
    if nota.status_emissao != "AUTORIZADA":
        raise HTTPException(400, "Só dá para cancelar uma nota autorizada.")
    if regras.titulo_da_nota(db, nota) is not None:
        raise HTTPException(
            400, "Esta nota está faturada. Desfature antes de cancelar na SEFAZ.")
    empresa = db.get(Empresa, nota.empresa_id)
    cert, chave_privada, certificado, cadeia = _abrir_certificado(db, nota.empresa_id)
    try:
        retorno = nfe.cancelar(
            chave_privada, certificado, cadeia, empresa.uf, nota.ambiente or cert.ambiente,
            nota.chave, motor.so_numeros(empresa.cnpj), nota.protocolo,
            dados.justificativa or "",
        )
    except nfe.ErroEmissao as erro:
        return {
            "ok": False,
            "mensagem": str(erro),
            "erro": rejeicoes.explicar_falha(str(erro)),
            "nota": _ficha(db, nota)["nota"],
        }

    if not retorno["ok"]:
        return {
            "ok": False,
            "mensagem": f"A SEFAZ não cancelou ({retorno['cstat']}): {retorno['motivo']}",
            "erro": rejeicoes.explicar(retorno["cstat"], retorno["motivo"]),
            "nota": _ficha(db, nota)["nota"],
        }
    nota.status_emissao = "CANCELADA"
    nota.situacao = "CANCELADA"
    nota.cancelamento_justificativa = (dados.justificativa or "").strip()[:255]
    nota.cancelamento_protocolo = retorno["protocolo"]
    nota.cancelada_em = retorno["registrado_em"] or datetime.utcnow()
    db.commit()
    db.refresh(nota)
    return {
        "ok": True,
        "mensagem": f"Nota {nota.numero} cancelada na SEFAZ "
                    f"({retorno['cstat']} — {retorno['motivo']}).",
        "nota": _ficha(db, nota)["nota"],
    }
