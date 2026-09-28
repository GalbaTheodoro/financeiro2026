"""Vendas e margens: os relatórios comerciais.

Uma chamada por pergunta, e todas partem das mesmas linhas de venda
(``backend/vendas.py``) — assim o total da aba Clientes é sempre o mesmo total
da aba Produtos, o que não aconteceria se cada relatório montasse a sua consulta.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import vendas as regras
from ..database import get_db
from ..deps import acesso_liberado, exigir_modulo, validar_empresa
from ..models import Usuario
from ..utils import parse_data

router = APIRouter(
    prefix="/api/vendas", tags=["vendas"],
    dependencies=[Depends(exigir_modulo("NFE"))],
)


def _periodo(de: str | None, ate: str | None) -> tuple[date, date]:
    hoje = date.today()
    inicio = parse_data(de, date(hoje.year, hoje.month, 1))
    fim = parse_data(ate, hoje)
    if inicio > fim:
        raise HTTPException(400, "Data inicial maior que a data final.")
    return inicio, fim


def _linhas(db: Session, empresa_id: int, usuario: Usuario,
            de: str | None, ate: str | None):
    validar_empresa(db, empresa_id, usuario)
    inicio, fim = _periodo(de, ate)
    return regras.linhas_de_venda(db, empresa_id, inicio, fim), inicio, fim


def _cabecalho(linhas, inicio: date, fim: date) -> dict:
    return {
        "de": inicio.isoformat(),
        "ate": fim.isoformat(),
        "totais": regras.totais(linhas),
    }


@router.get("/resumo")
def resumo(empresa_id: int, de: str | None = None, ate: str | None = None,
           db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    """A visão geral: os números do período, a evolução e os dez primeiros."""
    linhas, inicio, fim = _linhas(db, empresa_id, usuario, de, ate)
    return {
        **_cabecalho(linhas, inicio, fim),
        "evolucao": regras.evolucao(linhas, inicio, fim),
        "clientes": regras.agrupar(linhas, "cliente")[:10],
        "produtos": regras.agrupar(linhas, "produto", ("codigo", "unidade"))[:10],
        "categorias": regras.agrupar(linhas, "categoria"),
        "tipos": regras.agrupar(linhas, "tipo"),
    }


@router.get("/clientes")
def clientes(empresa_id: int, de: str | None = None, ate: str | None = None,
             db: Session = Depends(get_db),
             usuario: Usuario = Depends(acesso_liberado)):
    """Ranking de clientes por faturamento, com margem e ticket médio."""
    linhas, inicio, fim = _linhas(db, empresa_id, usuario, de, ate)
    return {**_cabecalho(linhas, inicio, fim),
            "linhas": regras.agrupar(linhas, "cliente")}


@router.get("/produtos")
def produtos(empresa_id: int, de: str | None = None, ate: str | None = None,
             ordem: str = "receita", db: Session = Depends(get_db),
             usuario: Usuario = Depends(acesso_liberado)):
    """Ranking de produtos. `ordem`: receita | quantidade | margem | margem_percentual.

    É a mesma tabela para "mais vendidos" e "melhor margem" — o que muda é por
    onde ela é ordenada. Duas telas com os mesmos números ordenados diferente só
    dariam chance de os dois números divergirem.
    """
    linhas, inicio, fim = _linhas(db, empresa_id, usuario, de, ate)
    lista = regras.agrupar(linhas, "produto", ("codigo", "unidade", "categoria", "marca"))
    campos = ("receita", "quantidade", "margem", "margem_percentual")
    chave = ordem if ordem in campos else "receita"
    if chave == "margem_percentual":
        # margem % de quem vendeu quase nada não é informação, é ruído: fica no
        # fim da lista em vez de liderar o ranking
        relevante = max((l["receita"] for l in lista), default=0) * 0.01
        lista.sort(key=lambda l: (l["receita"] >= relevante, l[chave]), reverse=True)
    else:
        lista.sort(key=lambda l: l[chave], reverse=True)
    return {**_cabecalho(linhas, inicio, fim), "ordem": chave, "linhas": lista}


@router.get("/custos")
def custos(empresa_id: int, de: str | None = None, ate: str | None = None,
           db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    """O custo da mercadoria vendida, por categoria e por produto."""
    linhas, inicio, fim = _linhas(db, empresa_id, usuario, de, ate)
    por_produto = regras.agrupar(linhas, "produto", ("codigo", "categoria"))
    por_produto.sort(key=lambda l: l["custo"], reverse=True)
    por_categoria = regras.agrupar(linhas, "categoria")
    por_categoria.sort(key=lambda l: l["custo"], reverse=True)
    sem_custo = [l for l in por_produto if l["sem_custo"]]
    return {
        **_cabecalho(linhas, inicio, fim),
        "categorias": por_categoria,
        "produtos": por_produto,
        "sem_custo": sem_custo,
        "origens": regras.ORIGENS_DO_CUSTO,
    }


@router.get("/parados")
def parados(empresa_id: int, dias: int = regras.DIAS_PARADO,
            db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    """Produtos com saldo que não saem há mais de N dias."""
    validar_empresa(db, empresa_id, usuario)
    if dias < 0 or dias > 3650:
        raise HTTPException(400, "Informe de 0 a 3650 dias.")
    return regras.parados(db, empresa_id, dias)


@router.get("/linhas")
def detalhe(empresa_id: int, de: str | None = None, ate: str | None = None,
            db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    """Item por item, para conferir de onde saiu qualquer número acima."""
    linhas, inicio, fim = _linhas(db, empresa_id, usuario, de, ate)
    return {**_cabecalho(linhas, inicio, fim), "linhas": linhas}
