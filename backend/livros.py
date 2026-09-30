"""Livros fiscais — os relatórios que o contador e o fiscal pedem.

Menu **Fiscal → Relatórios Fiscais** (``#/livros``). Cinco livros, todos
montados do que já está no sistema — nada é digitado de novo:

* **Registro de Entradas** (modelo P1) — as notas recebidas;
* **Registro de Saídas** (modelo P2) — as NF-e e os cupons emitidos;
* **Resumo por CFOP** — entradas e saídas somadas por código de operação;
* **Resumo por Estado** — entradas por UF de origem, saídas por UF de destino;
* **Livro de estoque** — por produto: saldo inicial, entradas, saídas e saldo
  final do período, em quantidade e em valor (custo médio). O saldo final é o
  inventário na data final.

De onde vêm as notas
--------------------
A mesma seleção do SPED Fiscal (``sped.notas_do_periodo``): nota emitida aqui é
saída; nota importada cujo emitente é a própria empresa também é saída; o resto
é entrada. Rascunho e nota rejeitada não são documento fiscal e ficam de fora;
a cópia do DF-e de uma nota que a empresa emitiu não entra duas vezes. Assim o
livro e o SPED do mesmo mês **batem**.

Uma linha por documento **e** por CFOP + alíquota — é assim que o livro de papel
é escriturado. O valor contábil da nota (que inclui frete, IPI e desconto) é
repartido entre as linhas na proporção do valor dos itens, e a última linha
leva o arredondamento: a soma das linhas é sempre o total da nota.

Tributada, isenta ou outras
---------------------------
Pelo CST do ICMS (o CSOSN do Simples passa antes pelo de/para do SPED):

* com base de cálculo: base, alíquota e imposto; o que sobra do valor contábil
  vai para **isentas/não tributadas** quando é redução de base (CST 20 e 70) e
  para **outras** no resto (frete, IPI, diferimento parcial...);
* sem base: CST 30, 40 e 41 → **isentas/não tributadas**; o resto (50
  suspensão, 51 diferimento — o caso do café —, 60 ST, 90) → **outras**.

Nota cancelada ou denegada aparece no livro, com valores zerados e a
observação — é o que manda a escrituração.

O que o livro não faz
---------------------
Não substitui a escrituração do contador: não faz ajuste de apuração, não
conhece ST nem DIFAL, e nota de entrada que ficou só com o resumo da SEFAZ
(sem itens) entra pelos totais do cabeçalho — a tela avisa quantas são.
"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import sped
from .models import Empresa, MovimentoEstoque, Nota, Produto
from .utils import dinheiro, so_numeros

LIVROS = {
    "entradas": "Registro de Entradas",
    "saidas": "Registro de Saídas",
    "cfop": "Resumo por CFOP",
    "uf": "Resumo por Estado",
    "estoque": "Livro de estoque",
}

# O primeiro dígito do CFOP diz o sentido e a origem/destino da operação
GRUPOS_CFOP = {
    "1": "Entradas de dentro do estado",
    "2": "Entradas de outros estados",
    "3": "Entradas do exterior",
    "5": "Saídas para dentro do estado",
    "6": "Saídas para outros estados",
    "7": "Saídas para o exterior",
}

CST_ISENTAS = ("30", "40", "41")
CST_REDUCAO = ("20", "70")

CAMPOS_VALOR = ("valor_contabil", "base", "icms", "isentas", "outras", "ipi")


# --------------------------------------------------------------------------- #
# Ajudantes
# --------------------------------------------------------------------------- #
def _zeros() -> dict:
    return {c: 0.0 for c in CAMPOS_VALOR}


def _somar(alvo: dict, linha: dict) -> None:
    for campo in CAMPOS_VALOR:
        alvo[campo] = dinheiro(alvo[campo] + float(linha.get(campo) or 0))


def _uf_do_xml(xml: str | None, grupo: str) -> str:
    """A UF do emitente (``emit``) ou do destinatário (``dest``) lida do XML."""
    if not xml:
        return ""
    trecho = re.search(rf"<{grupo}\b.*?</{grupo}>", xml, re.S)
    if not trecho:
        return ""
    uf = re.search(r"<UF>([A-Z]{2})</UF>", trecho.group(0))
    return uf.group(1) if uf else ""


def _classificar(cst: str, contabil: float, base: float) -> tuple[float, float]:
    """(isentas, outras) de uma linha do livro, pelo CST do ICMS."""
    final = (cst or "")[-2:]
    if base > 0:
        resto = dinheiro(max(contabil - base, 0))
        return (resto, 0.0) if final in CST_REDUCAO else (0.0, resto)
    if final in CST_ISENTAS:
        return dinheiro(contabil), 0.0
    return 0.0, dinheiro(contabil)


def _especie(nota: Nota) -> str:
    return "NFC-e" if (nota.modelo or "") == "65" else "NF-e"


def _cancelada(nota: Nota) -> bool:
    return nota.situacao in ("CANCELADA", "DENEGADA") or nota.status_emissao == "CANCELADA"


# --------------------------------------------------------------------------- #
# Linhas do livro de entradas e saídas
# --------------------------------------------------------------------------- #
def _participante(nota: Nota, entrada: bool, empresa: Empresa | None) -> dict:
    if entrada:
        uf = (nota.emitente_uf or _uf_do_xml(nota.xml, "emit")).upper()
        return {"nome": nota.emitente_nome or "", "documento": nota.emitente_cnpj or "",
                "ie": nota.emitente_ie or "", "uf": uf}
    if (nota.modelo or "") == "65":
        # cupom: venda presencial ao consumidor — a operação é dentro do estado
        return {"nome": nota.consumidor_nome or "Consumidor final",
                "documento": nota.consumidor_documento or "", "ie": "",
                "uf": ((empresa.uf if empresa else "") or "").upper()}
    parceiro = nota.parceiro
    uf = ((parceiro.uf if parceiro else "") or _uf_do_xml(nota.xml, "dest")).upper()
    return {"nome": nota.destinatario_nome or (parceiro.nome if parceiro else ""),
            "documento": nota.destinatario_cnpj or (parceiro.cpf_cnpj if parceiro else "") or "",
            "ie": (parceiro.rg_ie if parceiro else "") or "", "uf": uf}


def _linhas_da_nota(nota: Nota, entrada: bool, empresa: Empresa | None,
                    depara: dict) -> list[dict]:
    parte = _participante(nota, entrada, empresa)
    cabecalho = {
        "nota_id": nota.id,
        "data": nota.data_emissao.date().isoformat() if nota.data_emissao else None,
        "especie": _especie(nota),
        "serie": nota.serie or "",
        "numero": nota.numero or "",
        "chave": nota.chave or "",
        "participante": parte["nome"],
        "documento": parte["documento"],
        "ie": parte["ie"],
        "uf": parte["uf"],
        "observacao": "",
        "so_resumo": False,
    }

    if _cancelada(nota):
        situacao = "DENEGADA" if nota.situacao == "DENEGADA" else "CANCELADA"
        return [{**cabecalho, **_zeros(), "cfop": so_numeros(nota.cfop)[:4],
                 "aliquota": 0.0, "observacao": situacao}]

    # agrupa os itens por CFOP + CST + alíquota (o CST decide isentas x outras)
    grupos: dict[tuple, dict] = {}
    for item in nota.itens:
        cst = sped._cst_do_sped(item.icms_cst, item.origem_mercadoria, depara)
        chave = (so_numeros(item.cfop)[:4], cst, dinheiro(item.icms_aliquota))
        g = grupos.setdefault(chave, {"peso": 0.0, "base": 0.0, "icms": 0.0, "ipi": 0.0})
        g["peso"] += float(item.valor_total or 0)
        g["base"] = dinheiro(g["base"] + float(item.icms_base or 0))
        g["icms"] = dinheiro(g["icms"] + float(item.icms_valor or 0))
        g["ipi"] = dinheiro(g["ipi"] + float(item.ipi_valor or 0))

    total = dinheiro(nota.valor_total)
    if not grupos:
        # nota só com o cabeçalho (resumo da SEFAZ ou XML sem itens gravados)
        base = 0.0
        icms = dinheiro(nota.valor_icms)
        isentas, outras = (0.0, total) if not icms else (0.0, 0.0)
        return [{**cabecalho, "cfop": so_numeros(nota.cfop)[:4], "aliquota": 0.0,
                 "valor_contabil": total, "base": base, "icms": icms,
                 "isentas": isentas, "outras": outras,
                 "ipi": dinheiro(nota.valor_ipi), "so_resumo": True,
                 "observacao": "sem itens — só os totais da nota"}]

    peso_total = sum(g["peso"] for g in grupos.values()) or 1.0
    linhas = []
    distribuido = 0.0
    ordenados = sorted(grupos.items())
    for i, ((cfop, cst, aliquota), g) in enumerate(ordenados):
        if i == len(ordenados) - 1:
            contabil = dinheiro(total - distribuido)     # a última leva o arredondamento
        else:
            contabil = dinheiro(total * g["peso"] / peso_total)
            distribuido = dinheiro(distribuido + contabil)
        isentas, outras = _classificar(cst, contabil, g["base"])
        linhas.append({**cabecalho, "cfop": cfop, "cst": cst, "aliquota": aliquota,
                       "valor_contabil": contabil, "base": g["base"], "icms": g["icms"],
                       "isentas": isentas, "outras": outras, "ipi": g["ipi"]})
    return linhas


def livro_de_notas(db: Session, empresa_id: int, inicio: date, fim: date,
                   sentido: str) -> dict:
    """Registro de Entradas (``sentido='entradas'``) ou de Saídas (``'saidas'``)."""
    entrada = sentido == "entradas"
    empresa = db.get(Empresa, empresa_id)
    depara = sped.ler_depara(sped.config_da_empresa(db, empresa_id).csosn_para_cst)
    notas = sped.notas_do_periodo(db, empresa_id, inicio, fim)["entradas" if entrada else "saidas"]

    linhas: list[dict] = []
    for nota in notas:
        linhas.extend(_linhas_da_nota(nota, entrada, empresa, depara))

    totais = _zeros()
    for linha in linhas:
        _somar(totais, linha)
    return {
        "livro": LIVROS[sentido],
        "linhas": linhas,
        "totais": totais,
        "documentos": len(notas),
        "canceladas": sum(1 for n in notas if _cancelada(n)),
        "so_resumo": sum(1 for x in linhas if x["so_resumo"]),
        "empresa": _empresa(empresa),
        "periodo": {"inicio": inicio.isoformat(), "fim": fim.isoformat()},
    }


# --------------------------------------------------------------------------- #
# Resumos
# --------------------------------------------------------------------------- #
def _agrupar(linhas: list[dict], chave) -> list[dict]:
    grupos: dict[str, dict] = {}
    for linha in linhas:
        if linha.get("observacao") in ("CANCELADA", "DENEGADA"):
            continue
        k = chave(linha)
        g = grupos.setdefault(k, {"chave": k, "documentos": set(), **_zeros()})
        g["documentos"].add(linha["nota_id"])
        _somar(g, linha)
    saida = []
    for g in sorted(grupos.values(), key=lambda x: x["chave"]):
        g["documentos"] = len(g["documentos"])
        saida.append(g)
    return saida


def _total(grupos: list[dict]) -> dict:
    totais = {"documentos": sum(g["documentos"] for g in grupos), **_zeros()}
    for g in grupos:
        _somar(totais, g)
    return totais


def resumo_por_cfop(db: Session, empresa_id: int, inicio: date, fim: date) -> dict:
    entradas = livro_de_notas(db, empresa_id, inicio, fim, "entradas")
    saidas = livro_de_notas(db, empresa_id, inicio, fim, "saidas")

    def montar(livro: dict) -> dict:
        grupos = _agrupar(livro["linhas"], lambda x: x["cfop"] or "sem CFOP")
        for g in grupos:
            g["cfop"] = g.pop("chave")
            g["grupo"] = GRUPOS_CFOP.get(g["cfop"][:1], "CFOP não informado")
        return {"linhas": grupos, "totais": _total(grupos)}

    return {"livro": LIVROS["cfop"], "entradas": montar(entradas), "saidas": montar(saidas),
            "empresa": entradas["empresa"], "periodo": entradas["periodo"]}


def resumo_por_uf(db: Session, empresa_id: int, inicio: date, fim: date) -> dict:
    entradas = livro_de_notas(db, empresa_id, inicio, fim, "entradas")
    saidas = livro_de_notas(db, empresa_id, inicio, fim, "saidas")
    uf_empresa = ((entradas["empresa"] or {}).get("uf") or "").upper()

    def montar(livro: dict) -> dict:
        grupos = _agrupar(livro["linhas"], lambda x: x["uf"] or "??")
        for g in grupos:
            g["uf"] = g.pop("chave")
            g["dentro_do_estado"] = bool(uf_empresa) and g["uf"] == uf_empresa
        return {"linhas": grupos, "totais": _total(grupos)}

    return {"livro": LIVROS["uf"], "entradas": montar(entradas), "saidas": montar(saidas),
            "uf_empresa": uf_empresa, "empresa": entradas["empresa"],
            "periodo": entradas["periodo"]}


# --------------------------------------------------------------------------- #
# Livro de estoque
# --------------------------------------------------------------------------- #
def livro_de_estoque(db: Session, empresa_id: int, inicio: date, fim: date,
                     apenas_com_movimento: bool = False) -> dict:
    """Por produto: saldo inicial, entradas, saídas e saldo final do período.

    O saldo em cada data é a **soma dos movimentos** até ela (entrada soma,
    saída subtrai), em quantidade e em valor — não a última linha gravada. Assim
    um movimento lançado com data retroativa entra no dia certo, e o saldo final
    é o inventário na data final (o que vai no Registro de Inventário).
    """
    produtos = (db.query(Produto)
                .filter(Produto.empresa_id == empresa_id, Produto.controla_estoque.is_(True))
                .order_by(Produto.nome).all())
    ids = [p.id for p in produtos]

    def somas(filtro) -> dict:
        if not ids:
            return {}
        consulta = (db.query(MovimentoEstoque.produto_id, MovimentoEstoque.tipo,
                             func.coalesce(func.sum(MovimentoEstoque.quantidade), 0),
                             func.coalesce(func.sum(MovimentoEstoque.custo_total), 0))
                    .filter(MovimentoEstoque.empresa_id == empresa_id,
                            MovimentoEstoque.produto_id.in_(ids), filtro)
                    .group_by(MovimentoEstoque.produto_id, MovimentoEstoque.tipo))
        resultado: dict = {}
        for produto_id, tipo, quantidade, valor in consulta.all():
            resultado[(produto_id, tipo)] = (float(quantidade or 0), float(valor or 0))
        return resultado

    antes = somas(MovimentoEstoque.data < inicio)
    no_periodo = somas((MovimentoEstoque.data >= inicio) & (MovimentoEstoque.data <= fim))

    def par(tabela, produto_id, tipo):
        return tabela.get((produto_id, tipo), (0.0, 0.0))

    linhas = []
    for p in produtos:
        e0, s0 = par(antes, p.id, "E"), par(antes, p.id, "S")
        e1, s1 = par(no_periodo, p.id, "E"), par(no_periodo, p.id, "S")
        qtd_inicial = round(e0[0] - s0[0], 4)
        valor_inicial = dinheiro(e0[1] - s0[1])
        qtd_final = round(qtd_inicial + e1[0] - s1[0], 4)
        valor_final = dinheiro(valor_inicial + e1[1] - s1[1])
        movimentou = bool(e1[0] or s1[0])
        if apenas_com_movimento and not movimentou:
            continue
        if not movimentou and abs(qtd_inicial) < 1e-9 and abs(qtd_final) < 1e-9:
            continue                    # produto sem nada até a data final
        linhas.append({
            "produto_id": p.id,
            "codigo": p.codigo,
            "produto": p.nome,
            "ncm": p.ncm or "",
            "unidade": p.estoque_unidade or p.unidade_comercial or "",
            "inicial_quantidade": qtd_inicial,
            "inicial_valor": valor_inicial,
            "entradas_quantidade": round(e1[0], 4),
            "entradas_valor": dinheiro(e1[1]),
            "saidas_quantidade": round(s1[0], 4),
            "saidas_valor": dinheiro(s1[1]),
            "final_quantidade": qtd_final,
            "final_valor": valor_final,
            "final_custo_medio": (round(valor_final / qtd_final, 6)
                                  if abs(qtd_final) > 1e-9 else 0.0),
            "negativo": qtd_final < -1e-9,
        })

    campos = ("inicial_valor", "entradas_valor", "saidas_valor", "final_valor")
    totais = {c: dinheiro(sum(x[c] for x in linhas)) for c in campos}
    totais["produtos"] = len(linhas)
    return {
        "livro": LIVROS["estoque"],
        "linhas": linhas,
        "totais": totais,
        "negativos": sum(1 for x in linhas if x["negativo"]),
        "empresa": _empresa(db.get(Empresa, empresa_id)),
        "periodo": {"inicio": inicio.isoformat(), "fim": fim.isoformat()},
    }


def _empresa(empresa: Empresa | None) -> dict:
    if not empresa:
        return {}
    return {"razao_social": empresa.razao_social, "cnpj": empresa.cnpj or "",
            "inscricao_estadual": empresa.inscricao_estadual or "",
            "uf": (empresa.uf or "").upper()}
