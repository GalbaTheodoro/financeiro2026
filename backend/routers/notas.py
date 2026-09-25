"""Notas Fiscais — a tela onde a nota vira dinheiro no financeiro.

O **DF-e** é a caixa de entrada: traz da SEFAZ o que foi emitido contra o CNPJ.
Aqui é a **gestão**: ver a nota, os itens, o cliente/fornecedor, e então

* **Faturar** — gerar a conta a pagar (nota de entrada) ou a receber (nota que a
  empresa emitiu), com as parcelas das duplicatas da nota;
* **Desfaturar** — apagar esse título e liberar a nota de novo. Só no AgroDock:
  a nota na SEFAZ não é tocada.

Rotas
-----
GET  /api/notas                  lista com filtros
GET  /api/notas/resumo           números do topo da tela
GET  /api/notas/{id}             ficha completa (dados, itens, parceiro, pagamentos, título)
PUT  /api/notas/{id}             ajustes manuais (parceiro e observação)
POST /api/notas/{id}/faturar     gera o título
POST /api/notas/{id}/desfaturar  apaga o título
POST /api/notas/faturar-lote     fatura várias de uma vez
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import dfe as motor, estoque, notas as regras
from ..database import get_db
from ..deps import acesso_liberado, exigir_modulo, validar_empresa
from ..models import Lancamento, Nota, Parceiro, Usuario
from ..schemas import AjustarNotaIn, FaturarLoteIn, FaturarNotaIn
from ..utils import dinheiro, endereco_linha, parse_data, serializar

# O menu deste módulo pode ser tirado de um plano (ou de um cliente) na área
# do administrador. Quem fecha a porta de verdade é a dependência abaixo:
# esconder o botão no menu não impede ninguém de chamar a rota pelo endereço.
router = APIRouter(prefix="/api/notas", tags=["notas"],
                   dependencies=[Depends(exigir_modulo("NFE"))])

SITUACOES = ["AUTORIZADA", "CANCELADA", "DENEGADA"]


# --------------------------------------------------------------------------- #
# Serialização
# --------------------------------------------------------------------------- #
def _resumo_titulo(db: Session, nota: Nota) -> dict | None:
    """Como está o título gerado pela nota: valor, parcelas, quanto já foi baixado."""
    lancamento = regras.titulo_da_nota(db, nota)
    if lancamento is None:
        return None
    parcelas = lancamento.parcelas
    baixado = sum(float(p.valor_baixado or 0) for p in parcelas)
    return {
        "id": lancamento.id,
        "tipo": lancamento.tipo,
        "status": lancamento.status,
        "descricao": lancamento.descricao,
        "valor_total": dinheiro(lancamento.valor_total),
        "valor_baixado": dinheiro(baixado),
        "saldo": dinheiro(float(lancamento.valor_total or 0) - baixado),
        "num_parcelas": len(parcelas),
        "tem_baixa": any(p.baixas for p in parcelas),
        "primeiro_vencimento": min((p.data_vencimento for p in parcelas), default=None),
        "parcelas": [
            {"numero": p.numero, "data_vencimento": p.data_vencimento, "valor": dinheiro(p.valor),
             "valor_baixado": dinheiro(p.valor_baixado), "status": p.status,
             "baixas": len(p.baixas)}
            for p in parcelas
        ],
    }


def _resumo_estoque(db: Session, nota: Nota, entrada: bool) -> dict:
    """O que a tela precisa saber sobre o estoque desta nota."""
    itens = estoque.itens_com_estoque(db, nota)
    return {
        "gerado": bool(nota.estoque_em),
        "gerado_em": (nota.estoque_em.isoformat(timespec="seconds")
                      if nota.estoque_em else None),
        "itens": len(itens),
        # o botão só aparece na nota de entrada com item que controla estoque
        "pode_gerar": bool(entrada and itens and not nota.estoque_em),
        "pode_estornar": bool(nota.estoque_em),
    }


def linha(db: Session, nota: Nota, cnpj_empresa: str) -> dict:
    titulo = _resumo_titulo(db, nota)
    entrada = regras.sentido(nota, cnpj_empresa) == "Entrada"
    return serializar(nota, exclude={"xml"}, extras={
        "estoque": _resumo_estoque(db, nota, entrada),
        "emitente_documento": motor.formatar_documento(nota.emitente_cnpj),
        "chave_formatada": motor.formatar_chave(nota.chave),
        "manifestacao_nome": motor.ROTULO_EVENTO.get(nota.manifestacao or "", ""),
        "sentido": regras.sentido(nota, cnpj_empresa),
        "tem_xml": bool(nota.xml) and not nota.resumo,
        "parceiro_nome": nota.parceiro.nome if nota.parceiro else None,
        "faturada": titulo is not None,
        "tipo_titulo_sugerido": regras.tipo_titulo_da_nota(db, nota),
        "titulo": titulo,
    })


# --------------------------------------------------------------------------- #
# Lista e resumo
# --------------------------------------------------------------------------- #
def _consulta(db: Session, empresa_id: int):
    return db.query(Nota).filter(Nota.empresa_id == empresa_id, Nota.tipo != "EVENTO")


@router.get("")
def listar(
    empresa_id: int,
    inicio: str | None = None,
    fim: str | None = None,
    situacao: str | None = None,
    faturamento: str | None = Query(None, description="faturadas | a-faturar"),
    sentido: str | None = Query(None, description="entrada | saida"),
    origem: str | None = Query(None, description="DFE (recebidas) | EMITIDA"),
    parceiro_id: int | None = None,
    busca: str | None = None,
    limite: int = 400,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    validar_empresa(db, empresa_id, usuario)
    consulta = _consulta(db, empresa_id)
    if inicio:
        consulta = consulta.filter(
            Nota.data_emissao >= datetime.combine(parse_data(inicio), datetime.min.time()))
    if fim:
        consulta = consulta.filter(
            Nota.data_emissao <= datetime.combine(parse_data(fim), datetime.max.time()))
    if situacao:
        consulta = consulta.filter(Nota.situacao == situacao.upper())
    if faturamento == "faturadas":
        consulta = consulta.filter(Nota.lancamento_id.isnot(None))
    elif faturamento == "a-faturar":
        consulta = consulta.filter(Nota.lancamento_id.is_(None))
    if origem in ("DFE", "EMITIDA"):
        consulta = consulta.filter(Nota.origem == origem)
    if parceiro_id:
        consulta = consulta.filter(Nota.parceiro_id == parceiro_id)
    if busca:
        termo = f"%{busca.strip()}%"
        consulta = consulta.filter(or_(
            Nota.emitente_nome.ilike(termo),
            Nota.destinatario_nome.ilike(termo),
            Nota.chave.ilike(termo),
            Nota.numero.ilike(termo),
            Nota.emitente_cnpj.ilike(f"%{motor.so_numeros(busca) or busca}%"),
        ))

    cnpj = regras.cnpj_da_empresa(db, empresa_id)
    encontradas = (
        consulta.order_by(func.coalesce(Nota.data_emissao, Nota.criado_em).desc(), Nota.id.desc())
        .limit(max(1, min(limite, 2000)))
        .all()
    )
    linhas = [linha(db, n, cnpj) for n in encontradas]
    db.commit()  # titulo_da_nota pode ter limpado vínculos de títulos apagados por fora
    if sentido in ("entrada", "saida"):
        alvo = "Entrada" if sentido == "entrada" else "Saída"
        linhas = [x for x in linhas if x["sentido"] == alvo]

    # rascunho ainda não é documento: fica de fora dos totais
    validas = [x for x in linhas
               if x["situacao"] != "CANCELADA" and x.get("status_emissao") != "RASCUNHO"]
    return {
        "linhas": linhas,
        "totais": {
            "quantidade": len(linhas),
            "valor": dinheiro(sum(x["valor_total"] for x in validas)),
            "faturadas": sum(1 for x in linhas if x["faturada"]),
            "valor_faturado": dinheiro(sum(x["valor_total"] for x in validas if x["faturada"])),
            "a_faturar": sum(1 for x in validas if not x["faturada"]),
            "emitidas": sum(1 for x in linhas if x["origem"] == "EMITIDA"),
            "rascunhos": sum(1 for x in linhas if x.get("status_emissao") == "RASCUNHO"),
            "valor_a_faturar": dinheiro(
                sum(x["valor_total"] for x in validas if not x["faturada"])),
        },
    }


@router.get("/resumo")
def resumo(empresa_id: int, db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    base = _consulta(db, empresa_id)
    validas = base.filter(Nota.situacao != "CANCELADA")
    a_faturar = validas.filter(Nota.lancamento_id.is_(None))
    return {
        "documentos": base.count(),
        "faturadas": base.filter(Nota.lancamento_id.isnot(None)).count(),
        "a_faturar": a_faturar.count(),
        "valor_a_faturar": dinheiro(
            db.query(func.coalesce(func.sum(Nota.valor_total), 0))
            .filter(Nota.empresa_id == empresa_id, Nota.tipo != "EVENTO",
                    Nota.situacao != "CANCELADA", Nota.lancamento_id.is_(None))
            .scalar() or 0),
        "canceladas": base.filter(Nota.situacao == "CANCELADA").count(),
        "so_resumo": base.filter(Nota.resumo.is_(True)).count(),
    }


# --------------------------------------------------------------------------- #
# Ficha
# --------------------------------------------------------------------------- #
def _nota_da_conta(db: Session, nota_id: int, usuario: Usuario) -> Nota:
    nota = db.get(Nota, nota_id)
    if not nota:
        raise HTTPException(404, "Nota não encontrada.")
    validar_empresa(db, nota.empresa_id, usuario)
    return nota


@router.get("/{nota_id}")
def ficha(nota_id: int, db: Session = Depends(get_db),
          usuario: Usuario = Depends(acesso_liberado)):
    """Tudo da nota numa resposta só: dados, itens, quem é o parceiro e o título."""
    nota = _nota_da_conta(db, nota_id, usuario)
    lido = motor.ler_documento(nota.xml or "", nota.esquema or "") if nota.xml else None

    itens = [
        serializar(i, extras={
            "produto_nome": i.produto.nome if i.produto else None,
            "produto_codigo": i.produto.codigo if i.produto else None,
        })
        for i in nota.itens
    ]
    if not itens and lido:
        itens = lido.get("itens", [])  # ainda não importada: mostra o que está no XML
    pagamentos = [serializar(p) for p in nota.pagamentos] or (
        lido.get("pagamentos", []) if lido else [])

    parceiro = db.get(Parceiro, nota.parceiro_id) if nota.parceiro_id else None
    dados_parceiro = None
    if parceiro:
        dados_parceiro = serializar(parceiro, extras={
            "endereco": endereco_linha(parceiro),
            "documento": motor.formatar_documento(parceiro.cpf_cnpj),
            "completo_para_nota": bool(parceiro.codigo_municipio and parceiro.uf
                                       and parceiro.indicador_ie),
        })

    eventos = (
        db.query(Nota)
        .filter(Nota.empresa_id == nota.empresa_id, Nota.chave == nota.chave,
                Nota.tipo == "EVENTO")
        .all()
    )
    resultado = {
        "nota": linha(db, nota, regras.cnpj_da_empresa(db, nota.empresa_id)),
        "itens": itens,
        "pagamentos": pagamentos,
        "parceiro": dados_parceiro,
        "eventos": [serializar(e, exclude={"xml"}) for e in eventos],
        "totais_itens": {
            "quantidade": len(itens),
            "produtos": dinheiro(sum(float(i.get("valor_total") or 0) for i in itens)),
            "icms": dinheiro(sum(float(i.get("icms_valor") or 0) for i in itens)),
            "sem_produto": sum(1 for i in itens if not i.get("produto_id")),
        },
        "manifestacoes": [
            {"tipo": nome, "rotulo": motor.ROTULO_EVENTO[nome],
             "codigo": dados_evento[0], "exige_justificativa": dados_evento[2]}
            for nome, dados_evento in motor.EVENTOS.items()
        ],
    }
    db.commit()
    return resultado


@router.put("/{nota_id}")
def ajustar(nota_id: int, dados: AjustarNotaIn, db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    """Troca o cliente/fornecedor da nota e guarda uma observação."""
    nota = _nota_da_conta(db, nota_id, usuario)
    # "parceiro_id": null no JSON é uma troca (para nenhum), diferente de não mandar o campo
    if "parceiro_id" in dados.model_fields_set:
        if regras.titulo_da_nota(db, nota) is not None:
            raise HTTPException(
                400, "A nota está faturada. Desfature antes de trocar o cliente/fornecedor.")
        parceiro = db.get(Parceiro, dados.parceiro_id) if dados.parceiro_id else None
        if dados.parceiro_id and (not parceiro or parceiro.empresa_id != nota.empresa_id):
            raise HTTPException(400, "Cliente/fornecedor inválido.")
        nota.parceiro_id = dados.parceiro_id or None
    if dados.observacao is not None:
        nota.observacao = (dados.observacao or "").strip() or None
    db.commit()
    db.refresh(nota)
    return linha(db, nota, regras.cnpj_da_empresa(db, nota.empresa_id))


# --------------------------------------------------------------------------- #
# Faturar e desfaturar
# --------------------------------------------------------------------------- #
@router.post("/{nota_id}/faturar")
def faturar(nota_id: int, dados: FaturarNotaIn, db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    """Gera a conta a pagar (ou a receber) da nota."""
    nota = _nota_da_conta(db, nota_id, usuario)
    lancamento = regras.faturar(db, nota, dados, usuario)
    db.commit()
    db.refresh(nota)
    return {
        "ok": True,
        "nota": linha(db, nota, regras.cnpj_da_empresa(db, nota.empresa_id)),
        "lancamento_id": lancamento.id,
        "mensagem": (
            f"Nota {nota.numero or ''} faturada: conta a "
            f"{'pagar' if lancamento.tipo == 'PAGAR' else 'receber'} nº {lancamento.id}, "
            f"{len(lancamento.parcelas)} parcela(s)."
        ),
    }


@router.post("/{nota_id}/desfaturar")
def desfaturar(nota_id: int, db: Session = Depends(get_db),
               usuario: Usuario = Depends(acesso_liberado)):
    """Apaga o título gerado pela nota e libera a nota para faturar de novo."""
    nota = _nota_da_conta(db, nota_id, usuario)
    apagado = regras.desfaturar(db, nota)
    db.commit()
    db.refresh(nota)
    return {
        "ok": True,
        "nota": linha(db, nota, regras.cnpj_da_empresa(db, nota.empresa_id)),
        "mensagem": (
            f"Nota {nota.numero or ''} desfaturada: a conta a "
            f"{'pagar' if apagado['tipo'] == 'PAGAR' else 'receber'} nº {apagado['lancamento_id']} "
            "foi apagada. A nota na SEFAZ continua como estava."
        ),
    }


# --------------------------------------------------------------------------- #
# Estoque da nota
# --------------------------------------------------------------------------- #
@router.post("/{nota_id}/estoque")
def gerar_estoque(nota_id: int, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(acesso_liberado)):
    """Põe no estoque a mercadoria da nota de entrada.

    É manual de propósito: nota de entrada chega da SEFAZ o tempo todo, e nem
    toda ela é mercadoria que a empresa guarda. A baixa da venda, essa sim, é
    automática — acontece quando a SEFAZ autoriza a nota de saída.
    """
    nota = _nota_da_conta(db, nota_id, usuario)
    cnpj = regras.cnpj_da_empresa(db, nota.empresa_id)
    if regras.sentido(nota, cnpj) != "Entrada":
        raise HTTPException(
            400, "Esta nota é de saída: o estoque dela é baixado sozinho quando a SEFAZ "
                 "autoriza a nota.")
    try:
        retorno = estoque.entrada_da_nota(db, nota, usuario.id)
    except estoque.ErroEstoque as erro:
        raise HTTPException(400, str(erro)) from None
    db.commit()
    db.refresh(nota)
    return {"ok": True, "nota": linha(db, nota, cnpj), **retorno}


@router.post("/{nota_id}/estoque/estornar")
def estornar_estoque(nota_id: int, db: Session = Depends(get_db),
                     usuario: Usuario = Depends(acesso_liberado)):
    """Desfaz o que a nota fez no estoque, com movimentos de sentido contrário."""
    nota = _nota_da_conta(db, nota_id, usuario)
    try:
        retorno = estoque.estornar_nota(db, nota, usuario.id)
    except estoque.ErroEstoque as erro:
        raise HTTPException(400, str(erro)) from None
    db.commit()
    db.refresh(nota)
    return {"ok": True, "nota": linha(db, nota, regras.cnpj_da_empresa(db, nota.empresa_id)),
            **retorno}


@router.post("/faturar-lote")
def faturar_lote(dados: FaturarLoteIn, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(acesso_liberado)):
    """Fatura várias notas de uma vez. O que falhar é listado, sem derrubar o resto."""
    validar_empresa(db, dados.empresa_id, usuario)
    if not dados.notas:
        raise HTTPException(400, "Escolha pelo menos uma nota.")
    if len(dados.notas) > 200:
        raise HTTPException(400, "Fature no máximo 200 notas por vez.")

    faturadas, recusadas = [], []
    for nota_id in dados.notas:
        nota = db.get(Nota, nota_id)
        if not nota or nota.empresa_id != dados.empresa_id:
            recusadas.append({"nota_id": nota_id, "motivo": "Nota não encontrada."})
            continue
        try:
            lancamento = regras.faturar(db, nota, dados, usuario)
            db.commit()
            faturadas.append({"nota_id": nota.id, "numero": nota.numero,
                              "lancamento_id": lancamento.id,
                              "valor": dinheiro(lancamento.valor_total)})
        except HTTPException as erro:
            db.rollback()
            recusadas.append({"nota_id": nota_id, "numero": nota.numero,
                              "emitente": nota.emitente_nome, "motivo": erro.detail})

    total = dinheiro(sum(f["valor"] for f in faturadas))
    return {
        "faturadas": faturadas,
        "recusadas": recusadas,
        "mensagem": (
            f"{len(faturadas)} nota(s) faturada(s), somando {total:,.2f}".replace(",", "@")
            .replace(".", ",").replace("@", ".")
            + (f". {len(recusadas)} não deu(ram) certo." if recusadas else ".")
        ),
    }
