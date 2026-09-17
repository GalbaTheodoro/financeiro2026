"""Cotações do café e das moedas para a faixa que passa no rodapé do site.

De onde vem cada número
-----------------------
* Bolsa de NY (café arábica, ICE US) ... Yahoo Finance, contratos KC<mês><ano>.NYB
  (cotação do dia, com poucos minutos de atraso). Se falhar: Notícias Agrícolas.
* Bolsa de Londres (robusta, ICE Europe) ... Notícias Agrícolas (fechamento do dia anterior).
* B3 (café arábica 4/5) ....................... Notícias Agrícolas (fechamento do dia anterior).
* DXY, Dólar e Euro .......................... Yahoo Finance (se falhar: AwesomeAPI).
* Ptax ........................................ Banco Central (API oficial Olinda).

Como fica sempre atualizado sem pesar
-------------------------------------
A primeira pessoa que abre o site depois de 10 minutos dispara a atualização; o
resultado fica guardado no banco (tabela ``cache_externo``) e todas as outras
visitas leem dali. Se uma fonte cair, o grupo dela continua com o último valor bom
(marcado como ``atrasado``), em vez de a faixa sumir.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from html import unescape

from sqlalchemy.orm import Session

from .models import CacheExterno

log = logging.getLogger("financeiro")

CHAVE_CACHE = "cotacoes_cafe"
TEMPO_LIMITE = 7  # segundos por fonte
_trava = threading.Lock()

NAVEGADOR = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
# letra do mês nos contratos futuros de café arábica (ICE US): Mar, Mai, Jul, Set, Dez
MESES_KC = {3: "H", 5: "K", 7: "N", 9: "U", 12: "Z"}

URL_NA = "https://www.noticiasagricolas.com.br/cotacoes/cafe/"
PAGINAS_NA = {
    "ny": "cafe-bolsa-de-nova-iorque-nybot",
    "londres": "cafe-bolsa-de-londres-liffe",
    "b3": "cafe-arabica-4-5-b3-prego-regular",
}


# --------------------------------------------------------------------------- #
# Acesso à internet (trocável nos testes)
# --------------------------------------------------------------------------- #
def _baixar(url: str) -> str:
    pedido = urllib.request.Request(url, headers={
        "User-Agent": NAVEGADOR, "Accept": "application/json,text/html,*/*",
        "Accept-Language": "pt-BR,pt;q=0.9",
    })
    with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
        return resposta.read().decode("utf-8", errors="replace")


baixar = _baixar  # os testes substituem por uma função que devolve arquivos gravados


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _numero_br(texto: str) -> float | None:
    """'3.400,00' -> 3400.0 ; '-2,12' -> -2.12 ; '+5' -> 5.0"""
    texto = (texto or "").strip().replace("\xa0", "").replace(" ", "")
    if not texto or texto in ("-", "—"):
        return None
    texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def contratos_kc(hoje: date, quantidade: int = 3) -> list[tuple[str, str]]:
    """Próximos vencimentos negociados de NY: [('KCZ26.NYB', 'Dezembro/26'), ...].

    O mês corrente de vencimento é pulado (nele o contrato já está em entrega)."""
    saida = []
    ano, mes = hoje.year, hoje.month
    while len(saida) < quantidade:
        mes += 1
        if mes > 12:
            mes, ano = 1, ano + 1
        if mes in MESES_KC:
            saida.append((f"KC{MESES_KC[mes]}{ano % 100:02d}.NYB",
                          f"{MESES[mes - 1]}/{ano % 100:02d}"))
    return saida


# --------------------------------------------------------------------------- #
# Fontes
# --------------------------------------------------------------------------- #
def yahoo(simbolo: str) -> dict:
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(simbolo)}?range=1d&interval=1d")
    dados = json.loads(baixar(url))
    resultado = (dados.get("chart") or {}).get("result")
    if not resultado:
        raise ValueError(f"Yahoo sem dados para {simbolo}")
    meta = resultado[0]["meta"]
    preco = meta.get("regularMarketPrice")
    anterior = meta.get("chartPreviousClose") or meta.get("previousClose")
    if preco is None:
        raise ValueError(f"Yahoo sem preço para {simbolo}")
    variacao = meta.get("fulldayChange")
    if variacao is None and anterior:
        variacao = preco - anterior
    percentual = meta.get("regularMarketChangePercent")
    if percentual is None and anterior:
        percentual = (preco - anterior) / anterior * 100
    return {
        "preco": float(preco),
        "variacao": round(float(variacao or 0), 4),
        "percentual": round(float(percentual or 0), 2),
        "momento": datetime.utcfromtimestamp(meta.get("regularMarketTime") or 0).isoformat() + "Z",
    }


def tabela_na(html: str) -> tuple[list[list[str]], str]:
    """Primeira tabela 'cot-fisicas' da página do Notícias Agrícolas + data de fechamento."""
    bloco = re.search(r'<table[^>]*class="[^"]*cot-fisicas[^"]*"[^>]*>(.*?)</table>', html, re.S)
    if not bloco:
        raise ValueError("tabela de cotação não encontrada")
    corpo = re.search(r"<tbody[^>]*>(.*?)</tbody>", bloco.group(1), re.S)
    linhas = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", corpo.group(1) if corpo else bloco.group(1), re.S):
        celulas = [unescape(re.sub(r"<[^>]+>", "", td)).strip()
                   for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if celulas:
            linhas.append(celulas)
    fechamento = re.search(r"Fechamento:\s*([0-9]{2}/[0-9]{2}/[0-9]{4})", html)
    return linhas, fechamento.group(1) if fechamento else ""


def _vencimento(rotulo: str) -> tuple[int, int] | None:
    """'Novembro/26' -> (2026, 11)"""
    m = re.match(r"\s*([A-Za-zçÇãÃéÉ]+)\s*/\s*(\d{2,4})", rotulo or "")
    if not m:
        return None
    nome = m.group(1).lower()
    for i, mes in enumerate(MESES, start=1):
        if mes.lower().startswith(nome[:3]):
            ano = int(m.group(2))
            return (ano + 2000 if ano < 100 else ano, i)
    return None


def _mes_curto(rotulo: str) -> str:
    """'Setembro/2027' -> 'Setembro/27'"""
    m = re.match(r"\s*([A-Za-zçÇãÃéÉ]+)\s*/\s*(\d{2,4})", rotulo or "")
    if not m:
        return rotulo
    return f"{m.group(1).capitalize()}/{m.group(2)[-2:]}"


def grupo_na(chave: str, colunas: tuple[int, int], limite: int = 3,
             tipo_variacao: str = "pontos") -> dict:
    linhas, fechamento = tabela_na(baixar(URL_NA + PAGINAS_NA[chave]))
    itens = []
    hoje = date.today()
    for linha in linhas:
        if len(linha) <= max(colunas) or not re.search(r"/\d{2}", linha[0]):
            continue  # pula linhas como "Dólar: 5,15"
        vencimento = _vencimento(linha[0])
        if vencimento and vencimento <= (hoje.year, hoje.month):
            continue  # contrato do mês corrente já está em entrega
        preco = _numero_br(linha[colunas[0]])
        if preco is None:
            continue
        itens.append({
            "contrato": _mes_curto(linha[0]),
            "cotacao": preco,
            "variacao": _numero_br(linha[colunas[1]]) or 0.0,
            "tipo_variacao": tipo_variacao,
        })
    return {"itens": itens[:limite],
            "referencia": f"fechamento {fechamento}" if fechamento else "fechamento"}


def grupo_ny(hoje: date) -> dict:
    itens = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        consultas = [(rotulo, pool.submit(yahoo, simbolo)) for simbolo, rotulo in contratos_kc(hoje)]
        for rotulo, futuro in consultas:
            try:
                c = futuro.result()
            except Exception as erro:  # noqa: BLE001
                log.info("Cotação NY %s indisponível no Yahoo: %s", rotulo, erro)
                continue
            itens.append({"contrato": rotulo, "cotacao": round(c["preco"], 2),
                          "variacao": round(c["variacao"], 2), "tipo_variacao": "pontos"})
    if len(itens) >= 2:
        return {"itens": itens, "referencia": "tempo real (atraso de ~10 min)"}
    return grupo_na("ny", (1, 3))  # plano B


def ptax() -> dict:
    fim = date.today()
    inicio = fim - timedelta(days=12)
    url = (
        "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
        "CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
        f"?@dataInicial='{inicio:%m-%d-%Y}'&@dataFinalCotacao='{fim:%m-%d-%Y}'"
        "&$format=json&$select=cotacaoVenda,dataHoraCotacao"
    )
    valores = json.loads(baixar(url)).get("value") or []
    if not valores:
        raise ValueError("Ptax sem dados")
    atual = valores[-1]
    anterior = valores[-2] if len(valores) > 1 else atual
    return {"cotacao": float(atual["cotacaoVenda"]),
            "variacao": round(float(atual["cotacaoVenda"]) - float(anterior["cotacaoVenda"]), 4),
            "data": atual["dataHoraCotacao"][:10]}


def awesome(par: str) -> dict:
    dados = json.loads(baixar(f"https://economia.awesomeapi.com.br/json/last/{par}"))
    item = dados[par.replace("-", "")]
    return {"preco": float(item["bid"]), "variacao": float(item.get("varBid") or 0)}


def grupo_moedas() -> dict:
    itens = []

    def moeda(rotulo, simbolo, par=None, casas=4):
        try:
            c = yahoo(simbolo)
        except Exception as erro:  # noqa: BLE001
            if not par:
                raise
            log.info("%s pelo Yahoo falhou (%s); usando AwesomeAPI", rotulo, erro)
            c = awesome(par)
        return {"contrato": rotulo, "cotacao": round(c["preco"], casas),
                "variacao": round(c["variacao"], casas), "tipo_variacao": "valor"}

    tarefas = [("DXY", "DX-Y.NYB", None, 2), ("Dólar", "BRL=X", "USD-BRL", 4),
               ("Euro", "EURBRL=X", "EUR-BRL", 4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futuros = [pool.submit(moeda, *t) for t in tarefas]
        futuro_ptax = pool.submit(ptax)
        for t, futuro in zip(tarefas, futuros):
            try:
                itens.append(futuro.result())
            except Exception as erro:  # noqa: BLE001
                log.info("Cotação %s indisponível: %s", t[0], erro)
        try:
            p = futuro_ptax.result()
            itens.append({"contrato": "Ptax", "cotacao": round(p["cotacao"], 4),
                          "variacao": round(p["variacao"], 4), "tipo_variacao": "valor"})
        except Exception as erro:  # noqa: BLE001
            log.info("Ptax indisponível: %s", erro)
    if not itens:
        raise ValueError("nenhuma moeda disponível")
    return {"itens": itens, "referencia": "tempo real; Ptax do Banco Central"}


GRUPOS = [
    ("ny", "Bolsa de NY", "¢/lb", "ICE US via Yahoo Finance"),
    ("londres", "Bolsa de Londres", "US$/t", "ICE Europe via Notícias Agrícolas"),
    ("b3", "Bolsa B3", "US$/sc", "B3 via Notícias Agrícolas"),
    ("moedas", "Moedas", "", "Yahoo Finance e Banco Central"),
]


def _buscar_grupo(chave: str, hoje: date) -> dict:
    if chave == "ny":
        return grupo_ny(hoje)
    if chave == "londres":
        return grupo_na("londres", (1, 2))
    if chave == "b3":
        return grupo_na("b3", (1, 2), tipo_variacao="%")
    return grupo_moedas()


# --------------------------------------------------------------------------- #
# Cache e montagem da resposta
# --------------------------------------------------------------------------- #
def _ler_cache(db: Session) -> dict | None:
    registro = db.get(CacheExterno, CHAVE_CACHE)
    if not registro or not registro.conteudo:
        return None
    try:
        return json.loads(registro.conteudo)
    except ValueError:
        return None


def _gravar_cache(db: Session, dados: dict) -> None:
    registro = db.get(CacheExterno, CHAVE_CACHE)
    if registro is None:
        registro = CacheExterno(chave=CHAVE_CACHE)
        db.add(registro)
    registro.conteudo = json.dumps(dados, ensure_ascii=False)
    registro.atualizado_em = datetime.utcnow()
    db.commit()


def atualizar(db: Session, anterior: dict | None = None) -> dict:
    """Consulta todas as fontes. O grupo que falhar herda o último valor bom."""
    hoje = date.today()
    antigos = {g["chave"]: g for g in (anterior or {}).get("grupos", [])}
    grupos = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futuros = {chave: pool.submit(_buscar_grupo, chave, hoje) for chave, *_ in GRUPOS}
        for chave, titulo, unidade, fonte in GRUPOS:
            try:
                dados = futuros[chave].result()
                if not dados["itens"]:
                    raise ValueError("sem itens")
                grupos.append({"chave": chave, "titulo": titulo, "unidade": unidade,
                               "fonte": fonte, "atrasado": False, **dados})
            except Exception as erro:  # noqa: BLE001
                log.warning("Cotações de %s indisponíveis: %s", titulo, erro)
                if chave in antigos:
                    grupos.append({**antigos[chave], "atrasado": True})
    resultado = {"atualizado_em": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                 "grupos": grupos}
    if grupos:
        _gravar_cache(db, resultado)
    return resultado


def obter(db: Session, minutos: int = 10) -> dict:
    """Cotações para a faixa: do cache se estiverem frescas; senão atualiza."""
    cache = _ler_cache(db)
    registro = db.get(CacheExterno, CHAVE_CACHE)
    fresco = (registro is not None and registro.atualizado_em
              and datetime.utcnow() - registro.atualizado_em < timedelta(minutes=max(minutos, 2)))
    if cache and fresco:
        return cache
    # só uma atualização por vez nesta cópia do sistema
    if not _trava.acquire(blocking=False):
        return cache or {"atualizado_em": None, "grupos": []}
    try:
        return atualizar(db, cache)
    except Exception as erro:  # noqa: BLE001
        log.warning("Falha ao atualizar cotações: %s", erro)
        return cache or {"atualizado_em": None, "grupos": []}
    finally:
        _trava.release()
