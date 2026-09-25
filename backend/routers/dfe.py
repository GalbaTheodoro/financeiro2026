"""DF-e — baixar da SEFAZ, guardar, imprimir e importar os documentos fiscais.

Rotas
-----
Certificado ....... GET/POST/DELETE /api/dfe/certificado
Buscar na SEFAZ ... POST /api/dfe/buscar
Documentos ........ GET /api/dfe/notas, GET /api/dfe/notas/{id}, DELETE
Arquivos .......... GET /api/dfe/notas/{id}/xml, .../danfe, GET /api/dfe/xml-lote
Manifestação ...... POST /api/dfe/notas/{id}/manifestar
Importação ........ POST /api/dfe/notas/{id}/importar, POST /api/dfe/enviar-xml

Nada aqui apaga documento na SEFAZ: excluir uma nota no AgroDock só a tira da
lista daqui (ela volta se o NSU for consultado de novo).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import danfe, dfe as motor, notas as regras
from ..database import get_db
from ..deps import acesso_liberado, exigir_modulo, validar_empresa
from ..models import CertificadoDigital, Empresa, Nota, Usuario
from ..schemas import BuscarDFeIn, ImportarNotaIn, ManifestarIn
from ..utils import dinheiro, parse_data, serializar

# O menu deste módulo pode ser tirado de um plano (ou de um cliente) na área
# do administrador. Quem fecha a porta de verdade é a dependência abaixo:
# esconder o botão no menu não impede ninguém de chamar a rota pelo endereço.
router = APIRouter(prefix="/api/dfe", tags=["dfe"],
                   dependencies=[Depends(exigir_modulo("NFE"))])

# quantas páginas de até 50 documentos buscar de uma vez
MAX_PAGINAS = 20


# --------------------------------------------------------------------------- #
# Certificado digital
# --------------------------------------------------------------------------- #
def _certificado_da_empresa(db: Session, empresa_id: int) -> CertificadoDigital | None:
    return (
        db.query(CertificadoDigital)
        .filter(CertificadoDigital.empresa_id == empresa_id)
        .first()
    )


def _resumo_certificado(cert: CertificadoDigital | None) -> dict:
    """Só o que pode aparecer na tela — nunca o arquivo nem a senha."""
    if not cert:
        return {"configurado": False, "ambiente": "1", "ambiente_nome": "Produção"}
    dias = None
    if cert.valido_ate:
        dias = (cert.valido_ate.date() - date.today()).days
    return {
        "configurado": True,
        "id": cert.id,
        "arquivo_nome": cert.arquivo_nome,
        "titular": cert.titular,
        "cnpj": motor.formatar_documento(cert.cnpj),
        "valido_de": cert.valido_de.isoformat(timespec="seconds") if cert.valido_de else None,
        "valido_ate": cert.valido_ate.isoformat(timespec="seconds") if cert.valido_ate else None,
        "dias_para_vencer": dias,
        "vencido": dias is not None and dias < 0,
        "ambiente": cert.ambiente,
        "ambiente_nome": motor.AMBIENTES.get(cert.ambiente, "Produção"),
        "uf_autor": cert.uf_autor,
        "ultimo_nsu": cert.ultimo_nsu,
        "max_nsu": cert.max_nsu,
        "faltam_documentos": bool(
            cert.max_nsu and cert.ultimo_nsu and cert.max_nsu > cert.ultimo_nsu
        ),
        "ultima_consulta": (cert.ultima_consulta.isoformat(timespec="seconds")
                            if cert.ultima_consulta else None),
        "ultima_mensagem": cert.ultima_mensagem,
        "ativo": cert.ativo,
    }


@router.get("/certificado")
def ver_certificado(empresa_id: int, db: Session = Depends(get_db),
                    usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    return _resumo_certificado(_certificado_da_empresa(db, empresa_id))


@router.post("/certificado")
async def salvar_certificado(
    empresa_id: int = Form(...),
    senha: str = Form(...),
    ambiente: str = Form("1"),
    uf_autor: str | None = Form(None),
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    """Recebe o arquivo A1 (.pfx/.p12) e guarda cifrado.

    O arquivo é conferido na hora: se a senha estiver errada ou não for um A1,
    nada é gravado.
    """
    empresa = validar_empresa(db, empresa_id, usuario)
    if usuario.perfil not in ("ADMIN", "MASTER"):
        raise HTTPException(403, "Apenas administradores podem cadastrar o certificado.")
    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(400, "Escolha o arquivo do certificado (.pfx ou .p12).")
    if len(conteudo) > 400 * 1024:
        raise HTTPException(400, "Arquivo muito grande para ser um certificado A1.")
    try:
        _chave, certificado, _cadeia = motor.abrir_pfx(conteudo, senha)
        dados = motor.dados_do_certificado(certificado)
    except motor.ErroDFe as erro:
        raise HTTPException(400, str(erro)) from None

    if dados["valido_ate"] and dados["valido_ate"] < datetime.utcnow():
        raise HTTPException(
            400,
            f"Este certificado venceu em {dados['valido_ate'].strftime('%d/%m/%Y')}. "
            "Envie o certificado novo.",
        )
    cnpj_empresa = motor.so_numeros(empresa.cnpj)
    if dados["cnpj"] and cnpj_empresa and dados["cnpj"] != cnpj_empresa:
        raise HTTPException(
            400,
            f"O certificado é do CNPJ {motor.formatar_documento(dados['cnpj'])} e a empresa "
            f"selecionada é {motor.formatar_documento(empresa.cnpj)}. Escolha a empresa certa.",
        )

    cert = _certificado_da_empresa(db, empresa_id) or CertificadoDigital(empresa_id=empresa_id)
    cert.arquivo_nome = (arquivo.filename or "certificado.pfx")[:160]
    cert.conteudo = motor.cifrar(conteudo)
    cert.senha = motor.cifrar((senha or "").encode())
    cert.titular = dados["titular"][:200]
    cert.cnpj = dados["cnpj"] or cnpj_empresa
    cert.valido_de = dados["valido_de"]
    cert.valido_ate = dados["valido_ate"]
    cert.ambiente = "2" if str(ambiente) == "2" else "1"
    cert.uf_autor = (uf_autor or empresa.uf or "").upper()[:2] or None
    cert.ativo = True
    cert.atualizado_em = datetime.utcnow()
    if cert.id is None:
        db.add(cert)
    db.commit()
    db.refresh(cert)
    return _resumo_certificado(cert)


@router.delete("/certificado")
def excluir_certificado(empresa_id: int, db: Session = Depends(get_db),
                        usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    if usuario.perfil not in ("ADMIN", "MASTER"):
        raise HTTPException(403, "Apenas administradores podem remover o certificado.")
    cert = _certificado_da_empresa(db, empresa_id)
    if cert:
        db.delete(cert)
        db.commit()
    return {"ok": True}


def _abrir_certificado(db: Session, empresa_id: int):
    cert = _certificado_da_empresa(db, empresa_id)
    if not cert or not cert.ativo:
        raise HTTPException(
            400,
            "Cadastre o certificado digital A1 desta empresa na aba Certificado antes de "
            "buscar os documentos na SEFAZ.",
        )
    try:
        chave, certificado, cadeia = motor.abrir_pfx(
            motor.decifrar(cert.conteudo), motor.decifrar(cert.senha).decode()
        )
    except motor.ErroDFe as erro:
        raise HTTPException(400, str(erro)) from None
    return cert, chave, certificado, cadeia


# --------------------------------------------------------------------------- #
# Buscar na SEFAZ
# --------------------------------------------------------------------------- #
def _gravar_documento(db: Session, empresa_id: int, documento: dict, nsu: str,
                      esquema: str) -> tuple[Nota | None, str]:
    """Guarda (ou completa) o documento recebido. Devolve (nota, 'nova'|'atualizada'|'ignorada')."""
    dados = motor.ler_documento(documento, esquema) if isinstance(documento, str) else documento
    if not dados or not dados.get("chave"):
        return None, "ignorada"

    nota = (
        db.query(Nota)
        .filter(Nota.empresa_id == empresa_id, Nota.chave == dados["chave"])
        .first()
    )

    # evento (cancelamento, ciência de terceiros...) atualiza a nota que já existe
    if dados["tipo"] == "EVENTO":
        if not nota:
            return None, "ignorada"
        codigo = dados.get("codigo_evento") or ""
        if codigo in ("110111", "110112"):
            nota.situacao = "CANCELADA"
        if codigo in motor.EVENTO_POR_CODIGO:
            nota.manifestacao = motor.EVENTO_POR_CODIGO[codigo]
            nota.manifestacao_em = dados.get("data_evento")
            nota.manifestacao_protocolo = dados.get("protocolo")
        if nsu > (nota.nsu or ""):
            nota.nsu = nsu
        return nota, "atualizada"

    if nota and not nota.resumo and dados["resumo"]:
        return nota, "ignorada"  # já temos o XML completo: o resumo não acrescenta nada

    novo = nota is None
    if novo:
        nota = Nota(empresa_id=empresa_id, chave=dados["chave"])
        db.add(nota)

    for campo in ("modelo", "serie", "numero", "data_emissao", "natureza_operacao",
                  "tipo_operacao", "finalidade", "emitente_cnpj", "emitente_nome",
                  "emitente_ie", "emitente_uf", "destinatario_cnpj", "destinatario_nome",
                  "protocolo", "data_autorizacao"):
        valor = dados.get(campo)
        if valor not in (None, ""):
            setattr(nota, campo, valor)
    for campo in ("valor_total", "valor_produtos", "valor_icms", "valor_ipi",
                  "valor_frete", "valor_desconto"):
        if dados.get(campo):
            setattr(nota, campo, dinheiro(dados[campo]))
    nota.nsu = nsu
    nota.esquema = dados["esquema"]
    nota.tipo = dados["tipo"]
    nota.resumo = dados["resumo"]
    nota.xml = dados["xml"]
    if nota.situacao != "CANCELADA":
        nota.situacao = dados.get("situacao") or "AUTORIZADA"
    if not nota.emitente_uf:
        nota.emitente_uf = motor.uf_da_chave(nota.chave)
    db.flush()
    return nota, "nova" if novo else "atualizada"


@router.post("/buscar")
def buscar(dados: BuscarDFeIn, db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    """Consulta a SEFAZ e guarda os documentos novos.

    A SEFAZ entrega até 50 documentos por consulta; o sistema repete a consulta
    enquanto houver documento novo (até `paginas`, no máximo 20 por vez), para
    não segurar a tela quando a empresa tem muita nota atrasada.
    """
    empresa = validar_empresa(db, dados.empresa_id, usuario)
    cert, chave_privada, certificado, cadeia = _abrir_certificado(db, dados.empresa_id)

    cnpj = motor.so_numeros(cert.cnpj or empresa.cnpj)
    if not cnpj:
        raise HTTPException(400, "Preencha o CNPJ da empresa em Cadastros > Empresas.")
    ultimo = "000000000000000" if dados.desde_o_inicio else (cert.ultimo_nsu or "0".zfill(15))

    novas = atualizadas = recebidos = 0
    mensagem = ""
    paginas = max(1, min(int(dados.paginas or 5), MAX_PAGINAS))
    for _ in range(paginas):
        try:
            retorno = motor.consultar_distribuicao(
                chave_privada, certificado, cadeia, cert.ambiente,
                cert.uf_autor or empresa.uf or "MG", cnpj, ultimo,
            )
        except motor.ErroDFe as erro:
            if recebidos:
                mensagem = str(erro)
                break
            raise HTTPException(400, str(erro)) from None

        mensagem = f"{retorno['cstat']} — {retorno['motivo']}"
        for documento in retorno["documentos"]:
            recebidos += 1
            _nota, situacao = _gravar_documento(
                db, dados.empresa_id, documento["xml"], documento["nsu"], documento["esquema"]
            )
            if situacao == "nova":
                novas += 1
            elif situacao == "atualizada":
                atualizadas += 1

        if retorno["ultimo_nsu"]:
            ultimo = retorno["ultimo_nsu"]
        cert.ultimo_nsu = ultimo
        cert.max_nsu = retorno["max_nsu"] or cert.max_nsu
        # 137 = nenhum documento localizado; sem documentos não há o que continuar
        if retorno["cstat"] == "137" or not retorno["documentos"]:
            break

    cert.ultima_consulta = datetime.utcnow()
    cert.ultima_mensagem = mensagem[:300]
    db.commit()
    return {
        "recebidos": recebidos,
        "novas": novas,
        "atualizadas": atualizadas,
        "mensagem": (
            f"{recebidos} documento(s) recebido(s) da SEFAZ: {novas} novo(s) e "
            f"{atualizadas} atualizado(s). {mensagem}"
            if recebidos else f"Nenhum documento novo. {mensagem}"
        ),
        "certificado": _resumo_certificado(cert),
    }


@router.post("/enviar-xml")
async def enviar_xml(
    empresa_id: int = Form(...),
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    """Sobe um XML que a empresa recebeu por e-mail (sem passar pela SEFAZ)."""
    validar_empresa(db, empresa_id, usuario)
    conteudo = (await arquivo.read()).decode("utf-8", "replace")
    if len(conteudo) > 4_000_000:
        raise HTTPException(400, "Arquivo XML muito grande.")
    nota, situacao = _gravar_documento(db, empresa_id, conteudo, "", "")
    if not nota:
        raise HTTPException(
            400, "Este arquivo não é o XML de uma NF-e (esperado nfeProc, NFe ou resNFe).")
    db.commit()
    db.refresh(nota)
    return {
        "situacao": situacao,
        "nota": _linha(nota, _cnpj_da_empresa(db, empresa_id)),
        "mensagem": f"Nota {nota.numero or ''} de {nota.emitente_nome or ''} "
                    f"{'importada' if situacao == 'nova' else 'atualizada'}.",
    }


# --------------------------------------------------------------------------- #
# Lista e ficha
# --------------------------------------------------------------------------- #
def _linha(nota: Nota, cnpj_empresa: str = "") -> dict:
    return serializar(nota, exclude={"xml"}, extras={
        "emitente_documento": motor.formatar_documento(nota.emitente_cnpj),
        "chave_formatada": motor.formatar_chave(nota.chave),
        "manifestacao_nome": motor.ROTULO_EVENTO.get(nota.manifestacao or "", ""),
        "sentido": regras.sentido(nota, cnpj_empresa),
        "tem_xml": bool(nota.xml) and not nota.resumo,
    })


def _cnpj_da_empresa(db: Session, empresa_id: int) -> str:
    return regras.cnpj_da_empresa(db, empresa_id)


@router.get("/notas")
def listar(
    empresa_id: int,
    inicio: str | None = None,
    fim: str | None = None,
    situacao: str | None = None,
    manifestacao: str | None = None,
    formato: str | None = Query(None, description="resumo | completo | importada | pendente"),
    busca: str | None = None,
    limite: int = 400,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    validar_empresa(db, empresa_id, usuario)
    consulta = db.query(Nota).filter(Nota.empresa_id == empresa_id, Nota.tipo != "EVENTO")
    if inicio:
        consulta = consulta.filter(Nota.data_emissao >= datetime.combine(
            parse_data(inicio), datetime.min.time()))
    if fim:
        consulta = consulta.filter(Nota.data_emissao <= datetime.combine(
            parse_data(fim), datetime.max.time()))
    if situacao:
        consulta = consulta.filter(Nota.situacao == situacao.upper())
    if manifestacao == "SEM":
        consulta = consulta.filter(or_(Nota.manifestacao.is_(None), Nota.manifestacao == ""))
    elif manifestacao:
        consulta = consulta.filter(Nota.manifestacao == manifestacao.upper())
    if formato == "resumo":
        consulta = consulta.filter(Nota.resumo.is_(True))
    elif formato == "completo":
        consulta = consulta.filter(Nota.resumo.is_(False))
    elif formato == "importada":
        consulta = consulta.filter(Nota.importada.is_(True))
    elif formato == "pendente":
        consulta = consulta.filter(Nota.importada.is_(False))
    if busca:
        termo = f"%{busca.strip()}%"
        consulta = consulta.filter(or_(
            Nota.emitente_nome.ilike(termo),
            Nota.chave.ilike(termo),
            Nota.numero.ilike(termo),
            Nota.emitente_cnpj.ilike(f"%{motor.so_numeros(busca) or busca}%"),
        ))
    notas = (
        consulta.order_by(func.coalesce(Nota.data_emissao, Nota.criado_em).desc(), Nota.id.desc())
        .limit(max(1, min(limite, 2000)))
        .all()
    )
    cnpj = _cnpj_da_empresa(db, empresa_id)
    return [_linha(n, cnpj) for n in notas]


@router.get("/resumo")
def resumo(empresa_id: int, db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    """Números do topo da tela."""
    validar_empresa(db, empresa_id, usuario)
    base = db.query(Nota).filter(Nota.empresa_id == empresa_id, Nota.tipo != "EVENTO")
    total = base.count()
    valor = db.query(func.coalesce(func.sum(Nota.valor_total), 0)).filter(
        Nota.empresa_id == empresa_id, Nota.tipo != "EVENTO",
        Nota.situacao != "CANCELADA").scalar() or 0
    return {
        "documentos": total,
        "valor_total": dinheiro(valor),
        "sem_manifestacao": base.filter(
            or_(Nota.manifestacao.is_(None), Nota.manifestacao == "")).count(),
        "somente_resumo": base.filter(Nota.resumo.is_(True)).count(),
        "nao_importadas": base.filter(Nota.importada.is_(False)).count(),
        "canceladas": base.filter(Nota.situacao == "CANCELADA").count(),
        "certificado": _resumo_certificado(_certificado_da_empresa(db, empresa_id)),
    }


def _nota_da_conta(db: Session, nota_id: int, usuario: Usuario) -> Nota:
    nota = db.get(Nota, nota_id)
    if not nota:
        raise HTTPException(404, "Documento não encontrado.")
    validar_empresa(db, nota.empresa_id, usuario)
    return nota


@router.get("/notas/{nota_id}")
def ficha(nota_id: int, db: Session = Depends(get_db),
          usuario: Usuario = Depends(acesso_liberado)):
    nota = _nota_da_conta(db, nota_id, usuario)
    dados = motor.ler_documento(nota.xml or "", nota.esquema or "") if nota.xml else None
    itens = [serializar(i, extras={"produto_nome": i.produto.nome if i.produto else None})
             for i in nota.itens]
    if not itens and dados:
        itens = dados.get("itens", [])  # ainda não importada: mostra o que está no XML
    pagamentos = [serializar(p) for p in nota.pagamentos] or (
        dados.get("pagamentos", []) if dados else [])
    eventos = (
        db.query(Nota)
        .filter(Nota.empresa_id == nota.empresa_id, Nota.chave == nota.chave,
                Nota.tipo == "EVENTO")
        .all()
    )
    return {
        "nota": _linha(nota, _cnpj_da_empresa(db, nota.empresa_id)),
        "itens": itens,
        "pagamentos": pagamentos,
        "eventos": [serializar(e, exclude={"xml"}) for e in eventos],
        "manifestacoes": [
            {"tipo": nome, "rotulo": motor.ROTULO_EVENTO[nome],
             "codigo": dados_evento[0], "exige_justificativa": dados_evento[2]}
            for nome, dados_evento in motor.EVENTOS.items()
        ],
    }


@router.get("/notas/{nota_id}/xml")
def baixar_xml(nota_id: int, db: Session = Depends(get_db),
               usuario: Usuario = Depends(acesso_liberado)):
    nota = _nota_da_conta(db, nota_id, usuario)
    if not nota.xml:
        raise HTTPException(404, "Este documento não tem XML guardado.")
    nome = f"{nota.chave or nota.id}.xml"
    return Response(
        content=nota.xml,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.get("/notas/{nota_id}/danfe", response_class=HTMLResponse)
def imprimir_danfe(nota_id: int, db: Session = Depends(get_db),
                   usuario: Usuario = Depends(acesso_liberado)):
    nota = _nota_da_conta(db, nota_id, usuario)
    empresa = db.get(Empresa, nota.empresa_id)
    if not nota.xml:
        raise HTTPException(404, "Este documento não tem XML guardado.")
    try:
        html = danfe.gerar(nota.xml, empresa.razao_social if empresa else "")
    except ValueError as erro:
        raise HTTPException(400, str(erro)) from None
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@router.delete("/notas/{nota_id}")
def excluir(nota_id: int, db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    """Tira o documento da lista do AgroDock (não mexe na SEFAZ nem nos títulos gerados)."""
    nota = _nota_da_conta(db, nota_id, usuario)
    db.delete(nota)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Manifestação do destinatário
# --------------------------------------------------------------------------- #
@router.post("/notas/{nota_id}/manifestar")
def manifestar(nota_id: int, dados: ManifestarIn, db: Session = Depends(get_db),
               usuario: Usuario = Depends(acesso_liberado)):
    """Envia à SEFAZ a manifestação do destinatário.

    É um ato definitivo: uma vez registrado, o evento não é apagado. Depois da
    ciência, a SEFAZ passa a entregar o XML completo da nota na próxima busca.
    """
    nota = _nota_da_conta(db, nota_id, usuario)
    empresa = db.get(Empresa, nota.empresa_id)
    cert, chave_privada, certificado, cadeia = _abrir_certificado(db, nota.empresa_id)
    tipo = (dados.tipo or "").upper()
    if tipo not in motor.EVENTOS:
        raise HTTPException(400, "Escolha uma das manifestações disponíveis.")
    if nota.tipo != "NFE":
        raise HTTPException(400, "Só é possível manifestar notas fiscais (modelo 55).")

    try:
        retorno = motor.manifestar(
            chave_privada, certificado, cadeia, cert.ambiente, nota.chave,
            motor.so_numeros(cert.cnpj or (empresa.cnpj if empresa else "")),
            tipo, dados.justificativa or "", max(1, int(dados.sequencia or 1)),
        )
    except motor.ErroDFe as erro:
        raise HTTPException(400, str(erro)) from None

    if not retorno["ok"]:
        raise HTTPException(
            400, f"A SEFAZ não registrou a manifestação ({retorno['cstat']}): {retorno['motivo']}")

    nota.manifestacao = tipo
    nota.manifestacao_em = retorno["registrado_em"] or datetime.utcnow()
    nota.manifestacao_protocolo = retorno["protocolo"]
    nota.manifestacao_justificativa = (dados.justificativa or "").strip()[:255] or None
    db.commit()
    return {
        "ok": True,
        "nota": _linha(nota, _cnpj_da_empresa(db, nota.empresa_id)),
        "mensagem": f"{motor.ROTULO_EVENTO[tipo]} registrada na SEFAZ "
                    f"({retorno['cstat']} — {retorno['motivo']}).",
    }


# --------------------------------------------------------------------------- #
# Importação: XML -> itens, pagamentos, cadastros e título a pagar
# --------------------------------------------------------------------------- #
@router.post("/notas/{nota_id}/importar")
def importar(nota_id: int, dados: ImportarNotaIn, db: Session = Depends(get_db),
             usuario: Usuario = Depends(acesso_liberado)):
    """Grava os itens e os pagamentos do XML e completa os cadastros.

    O que acontece, na ordem:
      1. itens do XML -> tabela de itens da nota (NOTA_ITEM);
      2. formas de pagamento e duplicatas -> pagamentos da nota (NOTA_PAGAMENTOS);
      3. emitente -> cliente/fornecedor, completando IE, endereço e código do município;
      4. cada item -> produto do cadastro, completando NCM, CEST, CFOP e unidade;
      5. se pedido, **fatura** a nota, gerando a conta a pagar/receber com as
         parcelas das duplicatas (o mesmo que o botão Faturar da tela Notas Fiscais).

    As regras ficam em ``backend/notas.py``, compartilhadas com a tela de gestão.
    """
    nota = _nota_da_conta(db, nota_id, usuario)
    resultado = regras.importar_xml(db, nota, dados.criar_parceiro, dados.atualizar_produtos)

    lancamento = None
    if dados.gerar_titulo:
        lancamento = regras.faturar(db, nota, dados, usuario)

    db.commit()
    db.refresh(nota)
    partes = [
        f"{resultado['itens']} item(ns)",
        f"{resultado['pagamentos']} forma(s)/parcela(s) de pagamento",
    ]
    if resultado["parceiro"] is not None:
        partes.append(f"cliente/fornecedor {resultado['parceiro'].nome}")
    if resultado["produtos_ligados"]:
        partes.append(
            f"{resultado['produtos_ligados']} produto(s) do cadastro"
            + (f" ({resultado['produtos_criados']} novo(s))"
               if resultado["produtos_criados"] else "")
        )
    if lancamento:
        partes.append(
            f"conta a {'pagar' if lancamento.tipo == 'PAGAR' else 'receber'} nº {lancamento.id}")
    return {
        "ok": True,
        "nota": _linha(nota, _cnpj_da_empresa(db, nota.empresa_id)),
        "lancamento_id": lancamento.id if lancamento else None,
        "mensagem": "Importado: " + ", ".join(partes) + ".",
    }
