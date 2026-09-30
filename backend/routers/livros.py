"""Livros fiscais — Fiscal → Relatórios Fiscais.

Só leitura: os livros são montados das notas e dos movimentos de estoque que já
estão no sistema (ver ``backend/livros.py``). Vivem do módulo da nota fiscal,
que todo plano tem — como o SPED.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import livros
from ..database import get_db
from ..deps import exigir_modulo, validar_empresa
from ..models import Usuario
from ..utils import parse_data

router = APIRouter(prefix="/api/livros", tags=["livros fiscais"])

# Um livro fiscal não passa de um ano por vez: além disso a tela fica lenta e
# nenhum livro de papel é escriturado assim.
DIAS_MAXIMOS = 366


def _periodo(de: str | None, ate: str | None) -> tuple[date, date]:
    hoje = date.today()
    try:
        inicio = parse_data(de, date(hoje.year, hoje.month, 1))
        fim = parse_data(ate, hoje)
    except ValueError:
        raise HTTPException(400, "Data inválida. Use o formato AAAA-MM-DD.") from None
    if inicio > fim:
        raise HTTPException(400, "A data inicial é maior que a data final.")
    if (fim - inicio).days > DIAS_MAXIMOS:
        raise HTTPException(400, "Escolha um período de até um ano.")
    return inicio, fim


@router.get("/{livro}")
def livro(
    livro: str,
    empresa_id: int,
    de: str | None = None,
    ate: str | None = None,
    apenas_com_movimento: bool = False,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_modulo("NFE")),
):
    if livro not in livros.LIVROS:
        raise HTTPException(404, "Esse livro não existe.")
    validar_empresa(db, empresa_id, usuario)
    inicio, fim = _periodo(de, ate)
    if livro in ("entradas", "saidas"):
        return livros.livro_de_notas(db, empresa_id, inicio, fim, livro)
    if livro == "cfop":
        return livros.resumo_por_cfop(db, empresa_id, inicio, fim)
    if livro == "uf":
        return livros.resumo_por_uf(db, empresa_id, inicio, fim)
    return livros.livro_de_estoque(db, empresa_id, inicio, fim, apenas_com_movimento)
