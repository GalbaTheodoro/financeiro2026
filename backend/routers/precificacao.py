"""Formação do preço de venda: calcular, conferir e gravar.

Três rotas, e a divisão entre elas é de propósito:

``GET  /api/precificacao``   abre a tela com o que está gravado no produto,
                             já calculado — ninguém precisa clicar em nada para
                             ver a situação atual;
``POST /api/precificacao``   recalcula com o que a tela mandou e **não grava
                             nada**. É o que responde enquanto a pessoa mexe nos
                             números;
``PUT  /api/precificacao``   grava. Só aqui o preço do produto muda, e só com o
                             que veio na chamada.

A conta mora em ``backend/precificacao.py`` e é a **única**: a tela não
recalcula por conta própria, justamente para o número da tela e o número
gravado nunca divergirem.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import precificacao as regras
from ..database import get_db
from ..deps import acesso_liberado, exigir_modulo, validar_empresa
from ..models import Empresa, Produto, Usuario
from ..utils import moeda_br

# Formar preço é da tela de balcão e do cadastro do produto: mesmo módulo da
# nota fiscal, que é onde o produto e o estoque vivem.
router = APIRouter(
    prefix="/api/precificacao", tags=["precificacao"],
    dependencies=[Depends(exigir_modulo("NFE"))],
)


class PrecoIn(BaseModel):
    """O que a tela manda. Tudo opcional: o que faltar vem do produto."""

    empresa_id: int
    produto_id: int
    custo_compra: float | None = None
    outros_custos: float | None = None
    markup: float | None = None           # preenchido = manda na conta
    preco_atual: float | None = None      # para comparar com o que já se pratica
    perc_icms: float | None = None
    perc_pis: float | None = None
    perc_cofins: float | None = None
    perc_ipi: float | None = None
    perc_simples: float | None = None
    perc_despesas: float | None = None
    perc_comissao: float | None = None
    perc_cartao: float | None = None
    perc_frete: float | None = None
    perc_lucro: float | None = None


class GravarPrecoIn(PrecoIn):
    """Grava. `preco_venda` em branco deixa o preço como está."""

    preco_venda: float | None = None


def _produto(db: Session, empresa_id: int, produto_id: int,
             usuario: Usuario) -> tuple[Produto, Empresa]:
    empresa = validar_empresa(db, empresa_id, usuario)
    produto = db.get(Produto, produto_id)
    if produto is None or produto.empresa_id != empresa_id:
        raise HTTPException(404, "Produto não encontrado nesta empresa.")
    return produto, empresa


def _montar(produto: Produto, empresa: Empresa, dados: PrecoIn | None) -> dict:
    """Junta o que está gravado com o que a tela mandou por cima."""
    estado = regras.estado_do_produto(produto, empresa)
    if dados is None:
        return estado
    # só os campos de cálculo: empresa_id, produto_id e preco_venda não entram
    enviados = dados.model_dump(exclude_none=True)
    for campo in list(estado):
        if campo in enviados:
            estado[campo] = enviados[campo]
    return estado


def _resposta(produto: Produto, empresa: Empresa, estado: dict) -> dict:
    calculo = regras.calcular(estado)
    if regras.empresa_do_simples(empresa) and not estado.get("perc_simples"):
        calculo["avisos"].append(
            "A empresa é do Simples Nacional e a alíquota do DAS está zerada. Sem ela o "
            "preço sai sem imposto nenhum — informe o percentual que a empresa paga "
            "(está na guia do DAS ou com o contador).")
    return {"estado": estado, "calculo": calculo,
            "rotulos": dict(regras.PERCENTUAIS)}


@router.get("")
def abrir(empresa_id: int, produto_id: int, db: Session = Depends(get_db),
          usuario: Usuario = Depends(acesso_liberado)):
    """Abre a formação do preço do produto, já calculada com o que está gravado."""
    produto, empresa = _produto(db, empresa_id, produto_id, usuario)
    return _resposta(produto, empresa, _montar(produto, empresa, None))


@router.post("")
def calcular(dados: PrecoIn, db: Session = Depends(get_db),
             usuario: Usuario = Depends(acesso_liberado)):
    """Recalcula com os números da tela. Não grava nada."""
    produto, empresa = _produto(db, dados.empresa_id, dados.produto_id, usuario)
    return _resposta(produto, empresa, _montar(produto, empresa, dados))


@router.put("")
def gravar(dados: GravarPrecoIn, db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    """Grava os percentuais no produto — e o preço, quando a tela mandar um.

    O preço só muda se vier preenchido: salvar os percentuais para continuar
    estudando o preço é uma coisa, mudar o que o balcão vai cobrar é outra.
    """
    produto, empresa = _produto(db, dados.empresa_id, dados.produto_id, usuario)
    estado = _montar(produto, empresa, dados)
    calculo = regras.calcular(estado)

    for campo in regras.CAMPOS_DO_PRODUTO:
        if campo in estado:
            setattr(produto, campo, max(float(estado[campo] or 0), 0.0))
    # a empresa do Simples não usa os impostos do cadastro fiscal; a de regime
    # normal não usa o DAS. Guardar o que não vale só confundiria depois.
    if not regras.empresa_do_simples(empresa):
        produto.perc_simples = 0

    mensagem = "Formação do preço salva."
    if dados.preco_venda is not None and float(dados.preco_venda) > 0:
        produto.preco_venda = float(dados.preco_venda)
        # o markup gravado passa a ser o do preço que vale de verdade
        custo = calculo["custo"]["custo_total"]
        if custo > 0:
            produto.markup = round(float(dados.preco_venda) / custo, 4)
        mensagem = (f"Preço de venda atualizado para "
                    f"{moeda_br(produto.preco_venda)}.")
    db.commit()
    db.refresh(produto)

    estado = regras.estado_do_produto(produto, empresa)
    resposta = _resposta(produto, empresa, estado)
    resposta["mensagem"] = mensagem
    return resposta
