"""Estoque: posição, extrato e acertos à mão.

Rotas
-----
GET  /api/estoque              posição: saldo, custo médio e valor por produto
GET  /api/estoque/extrato      os movimentos, com filtro por produto e período
POST /api/estoque/ajuste       acerto de inventário (entrada ou saída à mão)
POST /api/estoque/saldo-inicial  o que já existia quando o controle começou

A entrada pela nota fica em `/api/notas/{id}/estoque` (é lá que está o botão) e
a baixa da venda acontece sozinha na autorização, em `routers/emissao.py`.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import estoque as motor
from ..database import get_db
from ..deps import acesso_liberado, exigir_modulo, validar_empresa
from ..models import MovimentoEstoque, Produto, Usuario
from ..utils import parse_data, serializar

# O menu deste módulo pode ser tirado de um plano (ou de um cliente) na área
# do administrador. Quem fecha a porta de verdade é a dependência abaixo:
# esconder o botão no menu não impede ninguém de chamar a rota pelo endereço.
router = APIRouter(prefix="/api/estoque", tags=["estoque"],
                   dependencies=[Depends(exigir_modulo("NFE"))])


class AjusteIn(BaseModel):
    empresa_id: int
    produto_id: int
    tipo: str = "E"                  # E entrada | S saída
    quantidade: float = 0
    custo_unitario: float = 0        # só usado na entrada
    unidade: str | None = None
    data: str | None = None
    historico: str | None = None


class SaldoInicialIn(BaseModel):
    empresa_id: int
    produto_id: int
    quantidade: float = 0
    custo_unitario: float = 0
    unidade: str | None = None
    data: str | None = None


def _produto(db: Session, produto_id: int, empresa_id: int) -> Produto:
    produto = db.get(Produto, produto_id)
    if not produto or produto.empresa_id != empresa_id:
        raise HTTPException(404, "Produto não encontrado nesta empresa.")
    if not produto.controla_estoque:
        raise HTTPException(
            400,
            f"O produto {produto.nome} não controla estoque. Marque "
            "\"controla estoque\" no cadastro do produto para movimentá-lo.")
    return produto


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #
@router.get("")
def posicao(empresa_id: int, busca: str | None = None,
            apenas_com_saldo: bool = False, db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    return motor.posicao(db, empresa_id, busca or "", apenas_com_saldo)


@router.get("/extrato")
def extrato(empresa_id: int, produto_id: int | None = None, de: str | None = None,
            ate: str | None = None, origem: str | None = None,
            db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    """Os movimentos, do mais novo para o mais antigo."""
    validar_empresa(db, empresa_id, usuario)
    consulta = db.query(MovimentoEstoque).filter(
        MovimentoEstoque.empresa_id == empresa_id)
    if produto_id:
        consulta = consulta.filter(MovimentoEstoque.produto_id == produto_id)
    inicio, fim = parse_data(de), parse_data(ate)
    if inicio:
        consulta = consulta.filter(MovimentoEstoque.data >= inicio)
    if fim:
        consulta = consulta.filter(MovimentoEstoque.data <= fim)
    if origem:
        consulta = consulta.filter(MovimentoEstoque.origem == origem.upper())

    linhas = consulta.order_by(MovimentoEstoque.data.desc(),
                               MovimentoEstoque.id.desc()).limit(500).all()
    entradas = sum(float(m.quantidade) for m in linhas if m.tipo == "E")
    saidas = sum(float(m.quantidade) for m in linhas if m.tipo == "S")
    return {
        "movimentos": [serializar(m, extras={
            "produto_nome": m.produto.nome if m.produto else "-",
            "produto_codigo": m.produto.codigo if m.produto else "",
            "parceiro_nome": m.parceiro.nome if m.parceiro else None,
        }) for m in linhas],
        "resumo": {"linhas": len(linhas), "entradas": round(entradas, 4),
                   "saidas": round(saidas, 4)},
        "origens": list(motor.ORIGENS),
    }


# --------------------------------------------------------------------------- #
# Acertos à mão
# --------------------------------------------------------------------------- #
@router.post("/ajuste")
def ajustar(dados: AjusteIn, db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    """Acerto de inventário: põe ou tira do estoque, com histórico obrigatório."""
    validar_empresa(db, dados.empresa_id, usuario)
    produto = _produto(db, dados.produto_id, dados.empresa_id)
    historico = (dados.historico or "").strip()
    if not historico:
        raise HTTPException(
            400, "Escreva o motivo do acerto — é ele que explica o movimento daqui a "
                 "seis meses (ex.: \"contagem do dia 30\", \"perda por umidade\").")
    try:
        movimento = motor.registrar(
            db, produto, (dados.tipo or "E").upper()[:1], dados.quantidade,
            custo_unitario=dados.custo_unitario, unidade=dados.unidade or "",
            origem="AJUSTE", data_movimento=parse_data(dados.data) or date.today(),
            historico=historico, usuario_id=usuario.id,
        )
    except motor.ErroEstoque as erro:
        raise HTTPException(400, str(erro)) from None
    db.commit()
    db.refresh(produto)
    return {"movimento": serializar(movimento), "produto": motor.ficha_produto(produto)}


@router.post("/saldo-inicial")
def saldo_inicial(dados: SaldoInicialIn, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(acesso_liberado)):
    """O que já existia quando o controle começou.

    Só vale para produto ainda sem movimento: depois que o extrato começou, o
    caminho é o ajuste, que deixa rastro.
    """
    validar_empresa(db, dados.empresa_id, usuario)
    produto = _produto(db, dados.produto_id, dados.empresa_id)
    ja_tem = db.query(MovimentoEstoque).filter(
        MovimentoEstoque.produto_id == produto.id).first()
    if ja_tem:
        raise HTTPException(
            400, f"{produto.nome} já tem movimento de estoque. Para corrigir o saldo, "
                 "use o acerto de inventário — assim fica o rastro do que mudou.")
    try:
        movimento = motor.registrar(
            db, produto, "E", dados.quantidade, custo_unitario=dados.custo_unitario,
            unidade=dados.unidade or "", origem="SALDO_INICIAL",
            data_movimento=parse_data(dados.data) or date.today(),
            historico="Saldo inicial do controle de estoque", usuario_id=usuario.id,
        )
    except motor.ErroEstoque as erro:
        raise HTTPException(400, str(erro)) from None
    db.commit()
    db.refresh(produto)
    return {"movimento": serializar(movimento), "produto": motor.ficha_produto(produto)}
