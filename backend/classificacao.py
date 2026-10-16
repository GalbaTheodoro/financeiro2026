"""Classificação do café — física (tipo, peneiras) e sensorial (bebida e prova).

Tudo aqui é cálculo puro, sem banco: recebe as contagens e notas que o
classificador digitou e devolve o resultado do laudo. A tela chama
``calcular`` a cada mudança (rota ``/api/amostras/calcular``) e o servidor
chama de novo ao salvar — o número gravado é sempre o do servidor.

Fontes
------
* **Instrução Normativa MAPA nº 8/2003** (Regulamento Técnico do café beneficiado
  grão cru): equivalência de defeitos, tipos de 2 a 8, peneiras, bebida e cor.
* **Protocolo de prova da SCA** (Specialty Coffee Association): dez atributos de
  0 a 10, menos os defeitos de xícara; 80 pontos ou mais é café especial.

Tipo intermediário
------------------
A IN 8/2003 dá o limite de cada tipo inteiro (2 = 4 defeitos, 3 = 12, 4 = 26,
5 = 46, 6 = 86, 7 = 160, 8 = 360) e divide o intervalo entre dois tipos em
passos de 5 pontos (2-5, 2-10 ... 2-45). Aqui o intermediário é **calculado por
interpolação** entre os dois limites e arredondado para cima no passo de 5 —
quem usa a tabela impressa do seu armazém pode corrigir o tipo à mão na
amostra (campo "tipo corrigido"), e o laudo mostra o que foi digitado.
"""
from __future__ import annotations

import json
import math

# --------------------------------------------------------------------------- #
# Defeitos — quantos grãos (ou impurezas) valem 1 defeito, e quanto vale cada um
# --------------------------------------------------------------------------- #
# (chave, rótulo, grupo, unidades por defeito, defeitos por unidade)
DEFEITOS = [
    ("preto", "Grão preto", "Grãos", 1, 1),
    ("ardido", "Grão ardido", "Grãos", 2, 1),
    ("preto_verde", "Grão preto-verde", "Grãos", 2, 1),
    ("verde", "Grão verde", "Grãos", 5, 1),
    ("concha", "Concha", "Grãos", 3, 1),
    ("quebrado", "Quebrado", "Grãos", 5, 1),
    ("brocado", "Brocado", "Grãos", 5, 1),
    ("mal_granado", "Mal granado / chocho", "Grãos", 5, 1),
    ("coco", "Coco", "Impurezas", 1, 1),
    ("marinheiro", "Marinheiro", "Impurezas", 2, 1),
    ("pau_pedra_grande", "Pau, pedra ou torrão grande", "Impurezas", 1, 5),
    ("pau_pedra_regular", "Pau, pedra ou torrão regular", "Impurezas", 1, 2),
    ("pau_pedra_pequeno", "Pau, pedra ou torrão pequeno", "Impurezas", 1, 1),
    ("casca_grande", "Casca grande", "Impurezas", 1, 1),
    ("casca_pequena", "Casca pequena", "Impurezas", 3, 1),
]
CHAVES_DEFEITO = [d[0] for d in DEFEITOS]

# Limite de defeitos (em 300 g) de cada tipo inteiro
TIPOS = [(2, 4), (3, 12), (4, 26), (5, 46), (6, 86), (7, 160), (8, 360)]
FORA_DE_TIPO = "Fora de tipo"
# Também é fora de tipo, qualquer que seja a soma (IN 8/2003)
LIMITES_FORA = {"preto": 50, "ardido": 100, "preto_verde": 100}

# --------------------------------------------------------------------------- #
# Peneiras (100 g)
# --------------------------------------------------------------------------- #
# (chave, rótulo, formato, número)
PENEIRAS = [
    ("C19", "19", "Chato", 19), ("C18", "18", "Chato", 18), ("C17", "17", "Chato", 17),
    ("C16", "16", "Chato", 16), ("C15", "15", "Chato", 15), ("C14", "14", "Chato", 14),
    ("C13", "13", "Chato", 13), ("C12", "12 e menor", "Chato", 12),
    ("M13", "13", "Moca", 13), ("M12", "12", "Moca", 12), ("M11", "11", "Moca", 11),
    ("M10", "10", "Moca", 10), ("M9", "9 e menor", "Moca", 9),
    ("FUNDO", "Fundo", "Fundo", 0),
]
CHAVES_PENEIRA = [p[0] for p in PENEIRAS]

# --------------------------------------------------------------------------- #
# Sensorial
# --------------------------------------------------------------------------- #
BEBIDAS = ["Estritamente mole", "Mole", "Apenas mole", "Dura", "Riada", "Rio", "Rio zona"]
BEBIDAS_CONILON = ["Excelente", "Boa", "Regular", "Anormal"]
GOSTOS = ["Fermentado", "Azedo", "Avinagrado", "Mofo", "Terra", "Fumaça", "Verde",
          "Sujo", "Remedio (fenicado)"]

# Protocolo SCA: dez atributos de 0 a 10
ATRIBUTOS = [
    ("fragrancia", "Fragrância/Aroma"),
    ("sabor", "Sabor"),
    ("finalizacao", "Finalização"),
    ("acidez", "Acidez"),
    ("corpo", "Corpo"),
    ("equilibrio", "Equilíbrio"),
    ("docura", "Doçura"),
    ("uniformidade", "Uniformidade"),
    ("xicara_limpa", "Xícara limpa"),
    ("nota_geral", "Nota geral"),
]
CHAVES_ATRIBUTO = [a[0] for a in ATRIBUTOS]

CORES = ["Verde azulado", "Verde cana", "Verde", "Esverdeada", "Amarelada", "Amarela",
         "Marrom", "Chumbada", "Esbranquiçada", "Discrepante"]
ASPECTOS = ["Bom", "Regular", "Mau"]
TORRACOES = ["Fina", "Boa", "Regular", "Má"]
PREPAROS = {
    "NATURAL": "Natural (terreiro)",
    "CEREJA_DESCASCADO": "Cereja descascado",
    "DESPOLPADO": "Despolpado",
    "LAVADO": "Lavado",
    "SEMI_LAVADO": "Semi-lavado",
    "FERMENTADO": "Fermentação controlada",
}
ESPECIES = {"ARABICA": "Arábica", "CONILON": "Conilon / Robusta"}


def tabelas() -> dict:
    """As listas da tela — vêm daqui para não ficarem duplicadas no navegador."""
    return {
        "defeitos": [{"chave": c, "rotulo": r, "grupo": g, "unidades": u, "vale": v}
                     for c, r, g, u, v in DEFEITOS],
        "peneiras": [{"chave": c, "rotulo": r, "formato": f, "numero": n}
                     for c, r, f, n in PENEIRAS],
        "tipos": [{"tipo": t, "limite": lim} for t, lim in TIPOS],
        "bebidas": BEBIDAS,
        "bebidas_conilon": BEBIDAS_CONILON,
        "gostos": GOSTOS,
        "atributos": [{"chave": c, "rotulo": r} for c, r in ATRIBUTOS],
        "cores": CORES,
        "aspectos": ASPECTOS,
        "torracoes": TORRACOES,
        "preparos": PREPAROS,
        "especies": ESPECIES,
    }


# --------------------------------------------------------------------------- #
# Ajudantes
# --------------------------------------------------------------------------- #
def ler_json(texto) -> dict:
    if isinstance(texto, dict):
        return texto
    if not texto:
        return {}
    try:
        dados = json.loads(texto)
    except (TypeError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _numero(valor) -> float:
    try:
        n = float(str(valor).replace(",", ".")) if valor not in (None, "") else 0.0
    except ValueError:
        return 0.0
    return n if math.isfinite(n) and n > 0 else 0.0


def limpar(dados: dict, chaves: list[str]) -> dict:
    """Só as chaves conhecidas, só números positivos — o resto é descartado."""
    dados = ler_json(dados)
    return {c: _numero(dados.get(c)) for c in chaves if _numero(dados.get(c))}


# --------------------------------------------------------------------------- #
# Física: defeitos e tipo
# --------------------------------------------------------------------------- #
def contar_defeitos(contagem: dict, peso_amostra: float = 300) -> dict:
    """Converte as contagens em defeitos e leva a soma para a base de 300 g."""
    contagem = limpar(contagem, CHAVES_DEFEITO)
    linhas = []
    soma = 0.0
    for chave, rotulo, grupo, unidades, vale in DEFEITOS:
        qtd = contagem.get(chave, 0.0)
        defeitos = round(qtd / unidades * vale, 2)
        soma += defeitos
        linhas.append({"chave": chave, "rotulo": rotulo, "grupo": grupo,
                       "quantidade": qtd, "defeitos": defeitos})
    peso = _numero(peso_amostra) or 300
    fator = 300 / peso
    total = round(soma * fator, 2)
    return {
        "linhas": linhas,
        "soma": round(soma, 2),
        "total_300g": total,
        "fator": round(fator, 4),
        "graos": round(sum(contagem.get(c, 0) for c, *_ in DEFEITOS[:8]) * fator, 2),
        "pva": round(sum(contagem.get(c, 0) for c in ("preto", "verde", "ardido")) * fator, 2),
        "contagem_300g": {c: round(v * fator, 2) for c, v in contagem.items()},
    }


def tipo_pelos_defeitos(total: float, contagem_300g: dict | None = None) -> dict:
    """O tipo da COB para um total de defeitos em 300 g.

    Devolve ``tipo`` (texto, ex.: "6", "4-25", "Fora de tipo"), o tipo inteiro
    de referência e o motivo quando é fora de tipo.
    """
    contagem_300g = contagem_300g or {}
    for chave, limite in LIMITES_FORA.items():
        if contagem_300g.get(chave, 0) > limite:
            rotulo = dict((d[0], d[1].lower()) for d in DEFEITOS)[chave]
            return {"tipo": FORA_DE_TIPO, "inteiro": None,
                    "motivo": f"mais de {limite} ({rotulo}) em 300 g"}
    total = max(float(total or 0), 0.0)
    if total <= TIPOS[0][1]:
        return {"tipo": "2", "inteiro": 2, "motivo": ""}
    for (t, lim), (t2, lim2) in zip(TIPOS, TIPOS[1:]):
        if total <= lim2:
            fracao = (total - lim) / (lim2 - lim)
            pontos = int(math.ceil(fracao * 50 / 5 - 1e-9) * 5)
            if total >= lim2:
                return {"tipo": str(t2), "inteiro": t2, "motivo": ""}
            pontos = min(max(pontos, 5), 45)   # abaixo do limite nunca vira o tipo de cima
            return {"tipo": f"{t}-{pontos}" if pontos else str(t), "inteiro": t, "motivo": ""}
    return {"tipo": FORA_DE_TIPO, "inteiro": None,
            "motivo": f"mais de {TIPOS[-1][1]} defeitos em 300 g"}


# --------------------------------------------------------------------------- #
# Física: peneiras
# --------------------------------------------------------------------------- #
def peneirar(gramas: dict, peso_peneiras: float = 100) -> dict:
    gramas = limpar(gramas, CHAVES_PENEIRA)
    soma = round(sum(gramas.values()), 2)
    base = soma or (_numero(peso_peneiras) or 100)
    linhas = []
    for chave, rotulo, formato, numero in PENEIRAS:
        g = gramas.get(chave, 0.0)
        linhas.append({"chave": chave, "rotulo": rotulo, "formato": formato,
                       "numero": numero, "gramas": g,
                       "percentual": round(g / base * 100, 2) if base else 0.0})

    def pct(cond) -> float:
        return round(sum(x["percentual"] for x in linhas if cond(x)), 2)

    chato = lambda x: x["formato"] == "Chato"         # noqa: E731
    moca = lambda x: x["formato"] == "Moca"           # noqa: E731
    grupos = {
        "chato_graudo": pct(lambda x: chato(x) and x["numero"] >= 17),
        "chato_medio": pct(lambda x: chato(x) and x["numero"] in (15, 16)),
        "chato_miudo": pct(lambda x: chato(x) and x["numero"] <= 14),
        "moca_graudo": pct(lambda x: moca(x) and x["numero"] >= 11),
        "moca_medio": pct(lambda x: moca(x) and x["numero"] == 10),
        "moca_miudo": pct(lambda x: moca(x) and x["numero"] <= 9),
        "fundo": pct(lambda x: x["formato"] == "Fundo"),
        "moca_total": pct(moca),
        "acima_17": pct(lambda x: chato(x) and x["numero"] >= 17),
        "acima_16": pct(lambda x: chato(x) and x["numero"] >= 16),
    }
    # a peneira "de leitura": a maior peneira de chato que, somada às maiores,
    # retém metade da amostra ou mais — é como o mercado fala ("peneira 17/18")
    leitura = ""
    acumulado = 0.0
    for x in linhas:
        if x["formato"] != "Chato":
            continue
        acumulado += x["percentual"]
        if acumulado >= 50:
            leitura = f"{x['numero']} acima" if x["numero"] < 19 else "19"
            break
    diferenca = round(soma - (_numero(peso_peneiras) or 100), 2) if soma else 0.0
    return {"linhas": linhas, "soma": soma, "grupos": grupos, "leitura": leitura,
            "diferenca": diferenca}


# --------------------------------------------------------------------------- #
# Sensorial
# --------------------------------------------------------------------------- #
def categoria_sca(pontos: float | None) -> str:
    if pontos is None:
        return ""
    if pontos >= 90:
        return "Excepcional"
    if pontos >= 85:
        return "Excelente"
    if pontos >= 80:
        return "Muito bom — café especial"
    return "Abaixo de especial"


def provar(notas: dict, defeitos_xicara: float = 0) -> dict:
    notas = ler_json(notas)
    limpas = {}
    for chave in CHAVES_ATRIBUTO:
        n = _numero(notas.get(chave))
        if n:
            limpas[chave] = round(min(n, 10.0), 2)
    completa = len(limpas) == len(CHAVES_ATRIBUTO)
    total = None
    if limpas:
        total = round(sum(limpas.values()) - _numero(defeitos_xicara), 2)
    return {
        "notas": limpas,
        "completa": completa,
        "pontuacao": total if completa else None,
        "parcial": total,
        "categoria": categoria_sca(total) if completa else "",
        "atributos": [{"chave": c, "rotulo": r, "nota": limpas.get(c)} for c, r in ATRIBUTOS],
    }


# --------------------------------------------------------------------------- #
# Tudo junto
# --------------------------------------------------------------------------- #
def padrao_sugerido(tipo: str, bebida: str | None, peneira: str, especie: str | None) -> str:
    partes = []
    if tipo:
        partes.append(tipo if tipo == FORA_DE_TIPO else f"Tipo {tipo}")
    if bebida:
        partes.append(f"bebida {bebida.lower()}")
    if peneira:
        partes.append(f"peneira {peneira}")
    if especie == "CONILON" and partes:
        partes.insert(0, "Conilon")
    return " · ".join(partes)


def calcular(dados: dict) -> dict:
    """O resultado completo do laudo a partir do que foi digitado."""
    defeitos = contar_defeitos(dados.get("defeitos"), dados.get("peso_amostra") or 300)
    tipo = tipo_pelos_defeitos(defeitos["total_300g"], defeitos["contagem_300g"])
    peneiras = peneirar(dados.get("peneiras"), dados.get("peso_peneiras") or 100)
    prova = provar(dados.get("sensorial"), dados.get("sensorial_defeitos") or 0)

    tipo_final = tipo["tipo"]
    manual = bool(dados.get("tipo_manual")) and bool((dados.get("tipo") or "").strip())
    if manual:
        tipo_final = dados["tipo"].strip()
    tem_defeito = any(x["quantidade"] for x in defeitos["linhas"])
    sugestao = padrao_sugerido(tipo_final if (tem_defeito or manual) else "",
                               dados.get("bebida"), peneiras["leitura"], dados.get("especie"))
    avisos = []
    if peneiras["soma"] and abs(peneiras["diferenca"]) > 1:
        avisos.append(f"As peneiras somam {peneiras['soma']:g} g — a amostra de peneira é "
                      f"de {_numero(dados.get('peso_peneiras')) or 100:g} g.")
    if tipo["motivo"]:
        avisos.append(f"Fora de tipo: {tipo['motivo']}.")
    if prova["notas"] and not prova["completa"]:
        avisos.append("A prova de xícara está incompleta: a pontuação só sai com as dez notas.")
    if _numero(dados.get("impurezas")) > 1:
        avisos.append("Impurezas acima de 1%: pela IN 8/2003 o lote fica desclassificado "
                      "até ser rebeneficiado.")

    return {
        "defeitos": defeitos,
        "tipo_calculado": tipo["tipo"],
        "tipo": tipo_final if (tem_defeito or manual) else "",
        "tipo_manual": manual,
        "fora_de_tipo": tipo_final == FORA_DE_TIPO,
        "peneiras": peneiras,
        "sensorial": prova,
        "padrao_sugerido": sugestao,
        "padrao": (dados.get("padrao") or "").strip() or sugestao,
        "avisos": avisos,
    }
