"""Tipos fiscais e regras fiscais da nota.

Rotas
-----
GET    /api/fiscal/tipos                 lista os tipos (filtra por aplicacao)
POST   /api/fiscal/tipos                 cria um tipo
PUT    /api/fiscal/tipos/{id}            edita
DELETE /api/fiscal/tipos/{id}            apaga (só se ninguém estiver usando)
POST   /api/fiscal/tipos/padrao          cria os tipos sugeridos
GET    /api/fiscal/regras                lista a tabela de regras
POST   /api/fiscal/regras                cria uma regra
PUT    /api/fiscal/regras/{id}           edita
DELETE /api/fiscal/regras/{id}           apaga
POST   /api/fiscal/simular               mostra qual regra ganha para uma situação
POST   /api/fiscal/calcular              faz a conta da base e dos impostos de um valor
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import cclasstrib, fiscal as motor
from ..database import get_db
from ..deps import acesso_liberado, validar_empresa
from ..models import Empresa, Parceiro, Produto, RegraFiscal, TipoFiscal, Usuario
from ..schemas import RegraFiscalIn, TipoFiscalIn
from ..utils import serializar

router = APIRouter(prefix="/api/fiscal", tags=["fiscal"])

APLICACOES = ("CLIENTE", "ITEM")

# Campos da regra que são percentuais: base, redução e alíquota, todos de 0 a 100
_PERCENTUAIS = (
    "icms_base", "icms_reducao", "icms_aliquota",
    "pis_cofins_base", "pis_cofins_reducao", "aliquota_pis", "aliquota_cofins",
    "aliquota_ipi", "ibs_cbs_base", "ibs_cbs_reducao_base",
    "ibs_cbs_reducao_aliquota", "cbs_aliquota",
    "ibs_uf_aliquota", "ibs_mun_aliquota",
)


# --------------------------------------------------------------------------- #
# Tipos fiscais
# --------------------------------------------------------------------------- #
def _aplicacao(valor: str | None) -> str:
    texto = (valor or "ITEM").strip().upper()
    if texto not in APLICACOES:
        raise HTTPException(400, "O tipo fiscal é de CLIENTE ou de ITEM.")
    return texto


@router.get("/tipos")
def listar_tipos(empresa_id: int, aplicacao: str | None = None,
                 db: Session = Depends(get_db),
                 usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    consulta = db.query(TipoFiscal).filter(TipoFiscal.empresa_id == empresa_id)
    if aplicacao:
        consulta = consulta.filter(TipoFiscal.aplicacao == _aplicacao(aplicacao))
    linhas = consulta.order_by(TipoFiscal.aplicacao, TipoFiscal.codigo).all()
    return [serializar(l) for l in linhas]


@router.post("/tipos")
def criar_tipo(dados: TipoFiscalIn, db: Session = Depends(get_db),
               usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, dados.empresa_id, usuario)
    aplicacao = _aplicacao(dados.aplicacao)
    codigo = (dados.codigo or "").strip().upper()
    if not codigo:
        raise HTTPException(400, "Dê um código curto para o tipo fiscal.")
    if not (dados.nome or "").strip():
        raise HTTPException(400, "Dê um nome ao tipo fiscal.")
    repetido = db.query(TipoFiscal).filter(
        TipoFiscal.empresa_id == dados.empresa_id,
        TipoFiscal.aplicacao == aplicacao, TipoFiscal.codigo == codigo).first()
    if repetido:
        raise HTTPException(400, f"Já existe um tipo de {aplicacao.lower()} com o código {codigo}.")
    tipo = TipoFiscal(empresa_id=dados.empresa_id, aplicacao=aplicacao, codigo=codigo,
                      nome=dados.nome.strip(), descricao=(dados.descricao or "").strip() or None,
                      ativo=dados.ativo)
    db.add(tipo)
    db.commit()
    db.refresh(tipo)
    return serializar(tipo)


@router.put("/tipos/{tipo_id}")
def salvar_tipo(tipo_id: int, dados: TipoFiscalIn, db: Session = Depends(get_db),
                usuario: Usuario = Depends(acesso_liberado)):
    tipo = db.get(TipoFiscal, tipo_id)
    if not tipo:
        raise HTTPException(404, "Tipo fiscal não encontrado.")
    validar_empresa(db, tipo.empresa_id, usuario)
    tipo.aplicacao = _aplicacao(dados.aplicacao)
    tipo.codigo = (dados.codigo or "").strip().upper() or tipo.codigo
    tipo.nome = (dados.nome or "").strip() or tipo.nome
    tipo.descricao = (dados.descricao or "").strip() or None
    tipo.ativo = dados.ativo
    db.commit()
    db.refresh(tipo)
    return serializar(tipo)


@router.delete("/tipos/{tipo_id}")
def apagar_tipo(tipo_id: int, db: Session = Depends(get_db),
                usuario: Usuario = Depends(acesso_liberado)):
    tipo = db.get(TipoFiscal, tipo_id)
    if not tipo:
        raise HTTPException(404, "Tipo fiscal não encontrado.")
    validar_empresa(db, tipo.empresa_id, usuario)
    em_uso = (
        db.query(Parceiro).filter(Parceiro.tipo_fiscal_id == tipo_id).first()
        or db.query(Produto).filter(Produto.tipo_fiscal_id == tipo_id).first()
        or db.query(RegraFiscal).filter(
            (RegraFiscal.tipo_cliente_id == tipo_id) | (RegraFiscal.tipo_item_id == tipo_id)
        ).first()
    )
    if em_uso:
        raise HTTPException(
            400, "Este tipo está em uso por um cadastro ou por uma regra. "
                 "Desative-o em vez de apagar.")
    db.delete(tipo)
    db.commit()
    return {"ok": True}


@router.post("/tipos/padrao")
def tipos_padrao(empresa_id: int, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(acesso_liberado)):
    """Cria a lista sugerida de tipos, para não começar de uma tela vazia."""
    validar_empresa(db, empresa_id, usuario)
    criados = motor.criar_tipos_padrao(db, empresa_id)
    db.commit()
    return {"criados": len(criados)}


# --------------------------------------------------------------------------- #
# Regras
# --------------------------------------------------------------------------- #
def _tipo_valido(db: Session, empresa_id: int, tipo_id: int | None,
                 aplicacao: str) -> int | None:
    if not tipo_id:
        return None
    tipo = db.get(TipoFiscal, tipo_id)
    if not tipo or tipo.empresa_id != empresa_id or tipo.aplicacao != aplicacao:
        raise HTTPException(400, f"Tipo fiscal de {aplicacao.lower()} inválido.")
    return tipo_id


def _ficha(db: Session, regra: RegraFiscal) -> dict:
    cliente = db.get(TipoFiscal, regra.tipo_cliente_id) if regra.tipo_cliente_id else None
    item = db.get(TipoFiscal, regra.tipo_item_id) if regra.tipo_item_id else None
    return serializar(regra, extras={
        "tipo_cliente_nome": cliente.nome if cliente else "Qualquer cliente",
        "tipo_item_nome": item.nome if item else "Qualquer item",
        "rota": f"{regra.uf_origem or '**'} → {regra.uf_destino or '**'}",
        "especificidade": sum(
            peso for campo, peso in motor.PESOS.items() if getattr(regra, campo, None)),
    })


@router.get("/regras")
def listar_regras(empresa_id: int, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    linhas = (
        db.query(RegraFiscal)
        .filter(RegraFiscal.empresa_id == empresa_id)
        .order_by(RegraFiscal.prioridade.desc(), RegraFiscal.id)
        .all()
    )
    return [_ficha(db, l) for l in linhas]


def _gravar(db: Session, regra: RegraFiscal, dados: RegraFiscalIn) -> None:
    regra.nome = (dados.nome or "").strip() or None
    regra.tipo_cliente_id = _tipo_valido(db, regra.empresa_id, dados.tipo_cliente_id, "CLIENTE")
    regra.tipo_item_id = _tipo_valido(db, regra.empresa_id, dados.tipo_item_id, "ITEM")
    regra.uf_origem = (dados.uf_origem or "").strip().upper()[:2] or None
    regra.uf_destino = (dados.uf_destino or "").strip().upper()[:2] or None
    operacao = (dados.operacao or "").strip().upper()
    if operacao and operacao not in ("SAIDA", "ENTRADA"):
        raise HTTPException(400, "A operação é SAIDA, ENTRADA ou em branco (as duas).")
    regra.operacao = operacao or None
    for campo in ("cfop", "icms_origem", "icms_cst", "cst_pis", "cst_cofins", "cst_ipi",
                  "ibs_cbs_cst", "ibs_cbs_classe"):
        setattr(regra, campo, (getattr(dados, campo) or "").strip() or None)
    # Os três primeiros números do cClassTrib são o CST do IBS/CBS (000001 é do
    # 000, 400001 é do 400). Par que discorda é recusa da SEFAZ — melhor barrar
    # aqui, com o campo ainda aberto na tela.
    if regra.ibs_cbs_cst and regra.ibs_cbs_classe \
            and regra.ibs_cbs_classe[:3] != regra.ibs_cbs_cst[:3]:
        raise HTTPException(
            400, f"O CST do IBS/CBS ({regra.ibs_cbs_cst}) e o cClassTrib "
                 f"({regra.ibs_cbs_classe}) são de situações diferentes: os três "
                 f"primeiros números do cClassTrib são o CST, então "
                 f"{regra.ibs_cbs_classe} é do CST {regra.ibs_cbs_classe[:3]}.")
    if regra.ibs_cbs_classe and not regra.ibs_cbs_cst:
        regra.ibs_cbs_cst = regra.ibs_cbs_classe[:3]    # o código já diz o CST
    for campo in _PERCENTUAIS:
        valor = getattr(dados, campo)
        valor = float(100 if valor is None and campo.endswith("_base") else (valor or 0))
        if valor < 0 or valor > 100:
            raise HTTPException(400, "Bases, reduções e alíquotas ficam entre 0 e 100%.")
        setattr(regra, campo, valor)
    regra.prioridade = int(dados.prioridade or 0)
    regra.observacao = (dados.observacao or "").strip() or None
    regra.ativo = dados.ativo


@router.post("/regras")
def criar_regra(dados: RegraFiscalIn, db: Session = Depends(get_db),
                usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, dados.empresa_id, usuario)
    regra = RegraFiscal(empresa_id=dados.empresa_id)
    _gravar(db, regra, dados)
    db.add(regra)
    db.commit()
    db.refresh(regra)
    return _ficha(db, regra)


@router.put("/regras/{regra_id}")
def salvar_regra(regra_id: int, dados: RegraFiscalIn, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(acesso_liberado)):
    regra = db.get(RegraFiscal, regra_id)
    if not regra:
        raise HTTPException(404, "Regra não encontrada.")
    validar_empresa(db, regra.empresa_id, usuario)
    _gravar(db, regra, dados)
    db.commit()
    db.refresh(regra)
    return _ficha(db, regra)


@router.delete("/regras/{regra_id}")
def apagar_regra(regra_id: int, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(acesso_liberado)):
    regra = db.get(RegraFiscal, regra_id)
    if not regra:
        raise HTTPException(404, "Regra não encontrada.")
    validar_empresa(db, regra.empresa_id, usuario)
    db.delete(regra)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Simulação: qual regra ganha
# --------------------------------------------------------------------------- #
class SimularIn(BaseModel):
    empresa_id: int
    parceiro_id: int | None = None
    produto_id: int | None = None
    tipo_cliente_id: int | None = None
    tipo_item_id: int | None = None
    cfop: str | None = None
    operacao: str = "SAIDA"
    valor: float = 1000.0          # valor do item usado para demonstrar a conta


@router.post("/simular")
def simular(dados: SimularIn, db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    """Diz qual regra vale para uma situação — usado pela tela da nota e para
    conferir a tabela sem precisar emitir nada."""
    empresa = validar_empresa(db, dados.empresa_id, usuario)
    parceiro = db.get(Parceiro, dados.parceiro_id) if dados.parceiro_id else None
    produto = db.get(Produto, dados.produto_id) if dados.produto_id else None
    if parceiro and parceiro.empresa_id != dados.empresa_id:
        raise HTTPException(400, "Cliente de outra empresa.")
    if produto and produto.empresa_id != dados.empresa_id:
        raise HTTPException(400, "Produto de outra empresa.")
    contexto = motor.montar_contexto(db, empresa, parceiro, produto, dados.operacao,
                                     dados.tipo_cliente_id, dados.tipo_item_id,
                                     cfop=dados.cfop)
    regra = motor.escolher_regra(db, dados.empresa_id, contexto)
    valor = float(dados.valor or 0)
    return {
        "contexto": contexto,
        "regra": motor.explicar(db, regra),
        "valor": valor,
        # a mesma conta que a emissão faz no item, para conferir sem emitir nada
        "calculo": motor.calcular_da_regra(regra, valor) if regra else None,
    }


class CalcularIn(BaseModel):
    """Os percentuais de uma regra — mesmo antes de ela ser salva — e um valor."""
    empresa_id: int
    valor: float = 1000.0
    valores: dict = {}


@router.post("/calcular")
def calcular(dados: CalcularIn, db: Session = Depends(get_db),
             usuario: Usuario = Depends(acesso_liberado)):
    """Mostra a conta de um item com estes percentuais.

    A tela de regras chama isto enquanto a pessoa digita: a base em percentual
    vira base em reais e o imposto sai dela. É a **mesma** função que a emissão
    usa para gravar o item, então o que aparece aqui é o que vai sair na nota.
    """
    validar_empresa(db, dados.empresa_id, usuario)
    limpos = {}
    for campo in motor.CAMPOS_DA_REGRA:
        valor = (dados.valores or {}).get(campo)
        if valor is None or valor == "":
            continue
        if campo in _PERCENTUAIS:
            try:
                numero = float(valor)
            except (TypeError, ValueError):
                raise HTTPException(400, f"O campo {campo} precisa ser um número.")
            if not 0 <= numero <= 100:
                raise HTTPException(400, f"O campo {campo} vai de 0 a 100.")
            limpos[campo] = numero
        else:
            limpos[campo] = str(valor).strip()
    for campo, padrao in (("icms_base", 100.0), ("pis_cofins_base", 100.0),
                          ("ibs_cbs_base", 100.0)):
        limpos.setdefault(campo, padrao)
    return {"valor": float(dados.valor or 0),
            "calculo": motor.calcular(limpos, float(dados.valor or 0))}


# --------------------------------------------------------------------------- #
# Tabela de classificação tributária do IBS/CBS (cClassTrib)
# --------------------------------------------------------------------------- #
@router.get("/cclasstrib")
def tabela_cclasstrib(busca: str = "", cst: str = "",
                      usuario: Usuario = Depends(acesso_liberado)):
    """Procura o código de classificação tributária por número, CST ou palavra."""
    return {
        "linhas": cclasstrib.buscar(busca, cst),
        "cst": [{"codigo": c, "nome": n} for c, n in cclasstrib.CST_IBS_CBS.items()],
        "parcial": True,   # a tabela oficial é maior; o campo aceita digitar à mão
    }


def _empresa_padrao(db: Session, empresa_id: int) -> Empresa | None:
    return db.get(Empresa, empresa_id)
