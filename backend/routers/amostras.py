"""Amostras de café — cadastro, classificação e laudo.

Rotas
-----
GET    /api/amostras/tabelas     defeitos, peneiras, bebidas, atributos da prova...
POST   /api/amostras/calcular    o resultado do que está na tela, sem gravar
GET    /api/amostras             a lista, com filtros
POST   /api/amostras             cria (o número sai sozinho, em sequência por empresa)
GET    /api/amostras/{id}        abre, já com o resultado calculado
PUT    /api/amostras/{id}        salva
DELETE /api/amostras/{id}        apaga
GET    /api/amostras/{id}/laudo  tudo o que o laudo impresso precisa

O cálculo mora em ``backend/classificacao.py``. Classificar café é o dia a dia de
quem trabalha com contrato de café, então a tela é do módulo de contratos —
está em todos os planos.
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import classificacao as regras
from ..database import get_db
from ..deps import exigir_modulo, validar_empresa
from ..models import AmostraCafe, Contrato, Empresa, Parceiro, Usuario
from ..utils import parse_data, serializar

router = APIRouter(prefix="/api/amostras", tags=["amostras de café"])
_do_plano = exigir_modulo("CONTRATOS")

SITUACOES = ("RECEBIDA", "CLASSIFICADA")


class AmostraIn(BaseModel):
    empresa_id: int
    situacao: str | None = "RECEBIDA"
    data_recebimento: str | None = None
    data_classificacao: str | None = None
    parceiro_id: int | None = None
    produtor_nome: str | None = None
    fazenda: str | None = None
    municipio: str | None = None
    uf: str | None = None
    contrato_id: int | None = None
    lote: str | None = None
    sacas: float | None = 0
    armazem: str | None = None
    safra: str | None = None
    especie: str | None = "ARABICA"
    variedade: str | None = None
    preparo: str | None = None
    altitude: int | None = None

    peso_amostra: float | None = 300
    peso_peneiras: float | None = 100
    umidade: float | None = None
    catacao: float | None = None
    impurezas: float | None = None
    cor: str | None = None
    aspecto: str | None = None
    torracao: str | None = None
    defeitos: dict = {}
    peneiras: dict = {}

    bebida: str | None = None
    gostos_estranhos: str | None = None
    sensorial: dict = {}
    sensorial_defeitos: float | None = 0
    descritores: str | None = None

    tipo: str | None = None
    tipo_manual: bool = False
    padrao: str | None = None
    classificador: str | None = None
    registro_classificador: str | None = None
    observacao: str | None = None


class CalcularIn(BaseModel):
    peso_amostra: float | None = 300
    peso_peneiras: float | None = 100
    impurezas: float | None = None
    especie: str | None = None
    defeitos: dict = {}
    peneiras: dict = {}
    bebida: str | None = None
    sensorial: dict = {}
    sensorial_defeitos: float | None = 0
    tipo: str | None = None
    tipo_manual: bool = False
    padrao: str | None = None


# --------------------------------------------------------------------------- #
# Ajudantes
# --------------------------------------------------------------------------- #
def _amostra(db: Session, amostra_id: int, usuario: Usuario) -> AmostraCafe:
    amostra = db.get(AmostraCafe, amostra_id)
    if not amostra:
        raise HTTPException(404, "Amostra não encontrada.")
    validar_empresa(db, amostra.empresa_id, usuario)
    return amostra


def _dados_de_calculo(a: AmostraCafe) -> dict:
    return {
        "peso_amostra": a.peso_amostra, "peso_peneiras": a.peso_peneiras,
        "impurezas": a.impurezas, "especie": a.especie,
        "defeitos": regras.ler_json(a.defeitos), "peneiras": regras.ler_json(a.peneiras),
        "bebida": a.bebida, "sensorial": regras.ler_json(a.sensorial),
        "sensorial_defeitos": a.sensorial_defeitos, "tipo": a.tipo,
        "tipo_manual": a.tipo_manual, "padrao": a.padrao,
    }


def _ficha(a: AmostraCafe, resultado: dict | None = None) -> dict:
    resultado = resultado or regras.calcular(_dados_de_calculo(a))
    return serializar(a, extras={
        "defeitos": regras.ler_json(a.defeitos),
        "peneiras": regras.ler_json(a.peneiras),
        "sensorial": regras.ler_json(a.sensorial),
        "parceiro_nome": a.parceiro.nome if a.parceiro else None,
        "contrato_numero": a.contrato.numero if a.contrato else None,
        "resultado": resultado,
    })


def _texto(valor, tamanho: int) -> str | None:
    valor = (valor or "").strip() if isinstance(valor, str) else valor
    return valor[:tamanho] if valor else None


def _aplicar(db: Session, a: AmostraCafe, dados: AmostraIn) -> dict:
    """Copia a tela para a amostra, recalcula e grava o resultado."""
    if dados.parceiro_id:
        parceiro = db.get(Parceiro, dados.parceiro_id)
        if not parceiro or parceiro.empresa_id != a.empresa_id:
            raise HTTPException(400, "Produtor/cliente não encontrado nesta empresa.")
        a.parceiro_id = parceiro.id
        # o que a tela não preencheu vem do cadastro
        dados.produtor_nome = dados.produtor_nome or parceiro.nome
        dados.municipio = dados.municipio or parceiro.cidade
        dados.uf = dados.uf or parceiro.uf
    else:
        a.parceiro_id = None
    if dados.contrato_id:
        contrato = db.get(Contrato, dados.contrato_id)
        if not contrato or contrato.empresa_id != a.empresa_id:
            raise HTTPException(400, "Contrato não encontrado nesta empresa.")
        a.contrato_id = contrato.id
    else:
        a.contrato_id = None

    situacao = (dados.situacao or "RECEBIDA").upper()
    if situacao not in SITUACOES:
        raise HTTPException(400, "Situação inválida.")
    especie = (dados.especie or "ARABICA").upper()
    if especie not in regras.ESPECIES:
        raise HTTPException(400, "Espécie inválida.")
    preparo = (dados.preparo or "").upper() or None
    if preparo and preparo not in regras.PREPAROS:
        raise HTTPException(400, "Preparo inválido.")
    for nome, valor, maximo in (("umidade", dados.umidade, 100), ("catação", dados.catacao, 100),
                                ("impurezas", dados.impurezas, 100)):
        if valor is not None and not 0 <= valor <= maximo:
            raise HTTPException(400, f"A {nome} vai de 0 a {maximo}%.")
    for nome, valor in (("peso da amostra", dados.peso_amostra),
                        ("peso das peneiras", dados.peso_peneiras)):
        if valor is not None and valor <= 0:
            raise HTTPException(400, f"O {nome} tem de ser maior que zero.")
    try:
        recebimento = parse_data(dados.data_recebimento, a.data_recebimento or date.today())
        classificacao = parse_data(dados.data_classificacao)
    except ValueError:
        raise HTTPException(400, "Data inválida.") from None

    a.situacao = situacao
    a.data_recebimento = recebimento
    a.data_classificacao = classificacao
    a.produtor_nome = _texto(dados.produtor_nome, 160)
    a.fazenda = _texto(dados.fazenda, 160)
    a.municipio = _texto(dados.municipio, 80)
    a.uf = (_texto(dados.uf, 2) or "").upper() or None
    a.lote = _texto(dados.lote, 40)
    a.sacas = max(float(dados.sacas or 0), 0)
    a.armazem = _texto(dados.armazem, 120)
    a.safra = _texto(dados.safra, 9)
    a.especie = especie
    a.variedade = _texto(dados.variedade, 60)
    a.preparo = preparo
    a.altitude = dados.altitude if dados.altitude and dados.altitude > 0 else None
    a.peso_amostra = dados.peso_amostra or 300
    a.peso_peneiras = dados.peso_peneiras or 100
    a.umidade = dados.umidade
    a.catacao = dados.catacao
    a.impurezas = dados.impurezas
    a.cor = _texto(dados.cor, 30)
    a.aspecto = _texto(dados.aspecto, 15)
    a.torracao = _texto(dados.torracao, 15)
    a.defeitos = json.dumps(regras.limpar(dados.defeitos, regras.CHAVES_DEFEITO))
    a.peneiras = json.dumps(regras.limpar(dados.peneiras, regras.CHAVES_PENEIRA))
    a.bebida = _texto(dados.bebida, 20)
    a.gostos_estranhos = _texto(dados.gostos_estranhos, 200)
    a.sensorial = json.dumps(regras.provar(dados.sensorial)["notas"])
    a.sensorial_defeitos = max(float(dados.sensorial_defeitos or 0), 0)
    a.descritores = _texto(dados.descritores, 300)
    a.tipo_manual = bool(dados.tipo_manual and (dados.tipo or "").strip())
    a.tipo = _texto(dados.tipo, 15) if a.tipo_manual else None
    a.padrao = _texto(dados.padrao, 120)
    a.classificador = _texto(dados.classificador, 120)
    a.registro_classificador = _texto(dados.registro_classificador, 40)
    a.observacao = dados.observacao or None

    resultado = regras.calcular(_dados_de_calculo(a))
    a.total_defeitos = resultado["defeitos"]["total_300g"]
    a.tipo = resultado["tipo"] or None
    a.pontuacao = resultado["sensorial"]["pontuacao"]
    if a.situacao == "CLASSIFICADA" and not a.data_classificacao:
        a.data_classificacao = date.today()
    return resultado


# --------------------------------------------------------------------------- #
# Rotas
# --------------------------------------------------------------------------- #
@router.get("/tabelas")
def tabelas(usuario: Usuario = Depends(_do_plano)):
    return regras.tabelas()


@router.post("/calcular")
def calcular(dados: CalcularIn, usuario: Usuario = Depends(_do_plano)):
    return regras.calcular(dados.model_dump())


@router.get("")
def listar(
    empresa_id: int,
    de: str | None = None,
    ate: str | None = None,
    parceiro_id: int | None = None,
    situacao: str | None = None,
    busca: str | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(_do_plano),
):
    validar_empresa(db, empresa_id, usuario)
    consulta = db.query(AmostraCafe).filter(AmostraCafe.empresa_id == empresa_id)
    try:
        inicio, fim = parse_data(de), parse_data(ate)
    except ValueError:
        raise HTTPException(400, "Data inválida.") from None
    if inicio:
        consulta = consulta.filter(AmostraCafe.data_recebimento >= inicio)
    if fim:
        consulta = consulta.filter(AmostraCafe.data_recebimento <= fim)
    if parceiro_id:
        consulta = consulta.filter(AmostraCafe.parceiro_id == parceiro_id)
    if situacao:
        consulta = consulta.filter(AmostraCafe.situacao == situacao.upper())
    if busca:
        alvo = f"%{busca.strip()}%"
        filtro = (AmostraCafe.produtor_nome.ilike(alvo) | AmostraCafe.fazenda.ilike(alvo)
                  | AmostraCafe.lote.ilike(alvo) | AmostraCafe.padrao.ilike(alvo))
        if busca.strip().isdigit():
            filtro = filtro | (AmostraCafe.numero == int(busca.strip()))
        consulta = consulta.filter(filtro)
    amostras = consulta.order_by(AmostraCafe.numero.desc()).limit(500).all()
    linhas = [serializar(a, exclude={"defeitos", "peneiras", "sensorial", "observacao"},
                         extras={"parceiro_nome": a.parceiro.nome if a.parceiro else None})
              for a in amostras]
    pontuadas = [x["pontuacao"] for x in linhas if x["pontuacao"]]
    return {
        "amostras": linhas,
        "resumo": {
            "total": len(linhas),
            "recebidas": sum(1 for x in linhas if x["situacao"] == "RECEBIDA"),
            "classificadas": sum(1 for x in linhas if x["situacao"] == "CLASSIFICADA"),
            "sacas": round(sum(float(x["sacas"] or 0) for x in linhas), 2),
            "especiais": sum(1 for p in pontuadas if p >= 80),
            "media_pontos": round(sum(pontuadas) / len(pontuadas), 2) if pontuadas else None,
        },
    }


@router.post("")
def criar(dados: AmostraIn, db: Session = Depends(get_db),
          usuario: Usuario = Depends(_do_plano)):
    validar_empresa(db, dados.empresa_id, usuario)
    ultimo = (db.query(func.max(AmostraCafe.numero))
              .filter(AmostraCafe.empresa_id == dados.empresa_id).scalar()) or 0
    amostra = AmostraCafe(empresa_id=dados.empresa_id, numero=ultimo + 1)
    resultado = _aplicar(db, amostra, dados)
    db.add(amostra)
    db.commit()
    db.refresh(amostra)
    return _ficha(amostra, resultado)


@router.get("/{amostra_id}")
def abrir(amostra_id: int, db: Session = Depends(get_db),
          usuario: Usuario = Depends(_do_plano)):
    return _ficha(_amostra(db, amostra_id, usuario))


@router.put("/{amostra_id}")
def salvar(amostra_id: int, dados: AmostraIn, db: Session = Depends(get_db),
           usuario: Usuario = Depends(_do_plano)):
    amostra = _amostra(db, amostra_id, usuario)
    if dados.empresa_id != amostra.empresa_id:
        raise HTTPException(400, "A amostra é de outra empresa.")
    resultado = _aplicar(db, amostra, dados)
    db.commit()
    db.refresh(amostra)
    return _ficha(amostra, resultado)


@router.delete("/{amostra_id}")
def apagar(amostra_id: int, db: Session = Depends(get_db),
           usuario: Usuario = Depends(_do_plano)):
    amostra = _amostra(db, amostra_id, usuario)
    db.delete(amostra)
    db.commit()
    return {"ok": True}


@router.get("/{amostra_id}/laudo")
def laudo(amostra_id: int, db: Session = Depends(get_db),
          usuario: Usuario = Depends(_do_plano)):
    amostra = _amostra(db, amostra_id, usuario)
    empresa = db.get(Empresa, amostra.empresa_id)
    endereco = ", ".join(x for x in (
        empresa.logradouro, empresa.numero, empresa.bairro) if x) if empresa else ""
    return {
        "amostra": _ficha(amostra),
        "empresa": {
            "razao_social": empresa.razao_social if empresa else "",
            "nome_fantasia": empresa.nome_fantasia if empresa else "",
            "cnpj": empresa.cnpj if empresa else "",
            "endereco": endereco,
            "cidade": empresa.cidade if empresa else "",
            "uf": empresa.uf if empresa else "",
            "telefone": empresa.telefone if empresa else "",
            "email": empresa.email if empresa else "",
            "logo": empresa.logo if empresa else None,
        },
        "preparos": regras.PREPAROS,
        "especies": regras.ESPECIES,
    }
