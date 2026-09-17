"""Painel "Mercado do Café": histórico das bolsas, preços por cidade e notícias do agro.

É a página que abre quando se clica na faixa de cotações do rodapé.

De onde vem cada informação
---------------------------
* Bolsas (NY, Londres, B3) e Indicador Cepea/Esalq ...... Notícias Agrícolas (fechamentos
  dos últimos 10 pregões por página).
* Preços no mercado físico por cidade (tipo 6/7, tipo 6 duro, cereja descascado e conilon)
  ................................................ Notícias Agrícolas (cooperativas: Expocaccer,
  Minasul, Coocacer, Cooxupé...).
* Cotações por cidade da AgnoCafé ..................... quadro "Cotações por Cidades" do site
  agnocafe.com.br (sem data publicada: vale a data em que foi lido). Pode ser desligado em
  Config. do site (``mercado_agnocafe``).
* Dólar Ptax ......................................... Banco Central (API oficial Olinda).
* Notícias ........................................... RSS do Canal Rural e do g1 (Agronegócios,
  Sul de Minas e Triângulo/Alto Paranaíba) e lista de notícias de café do Notícias Agrícolas.
  Só o título, a data e o link: a matéria abre no site de quem publicou.

Como o histórico cresce
-----------------------
Cada atualização grava os fechamentos na tabela ``cotacao_historico`` (uma linha por
série + item + dia). As páginas de origem só mostram 10 dias, mas o banco guarda tudo
o que já foi lido — com o tempo, o filtro por período alcança meses e anos.

Atualização
-----------
Igual à faixa: a primeira visita depois de ``mercado_minutos`` (30) dispara a leitura das
fontes; as outras leem do banco. Notícias: a cada ``noticias_minutos`` (20).
"""
from __future__ import annotations

import json
import logging
import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape

from sqlalchemy.orm import Session

from . import cotacoes
from .models import CacheExterno, CotacaoHistorico

log = logging.getLogger("financeiro")

CHAVE_MERCADO = "mercado_cafe"
CHAVE_NOTICIAS = "noticias_agro"
_trava_mercado = threading.Lock()
_trava_noticias = threading.Lock()

CIDADES_FOCO = ["Patrocínio", "Varginha", "Araguari", "Patos de Minas"]
URL_AGNOCAFE = "http://www.agnocafe.com.br/"


def hoje_brasil() -> date:
    """Data de hoje no horário de Brasília (o servidor roda em UTC)."""
    return (datetime.utcnow() - timedelta(hours=3)).date()


# --------------------------------------------------------------------------- #
# Séries de cotações
# --------------------------------------------------------------------------- #
# chave, título, unidade, página do Notícias Agrícolas, coluna do preço, coluna da
# variação, tipo da variação, categoria ("bolsa" ou "fisico")
SERIES = [
    ("ny", "Bolsa de NY — arábica", "¢/lb", "cafe-bolsa-de-nova-iorque-nybot", 1, 3, "pontos", "bolsa"),
    ("londres", "Bolsa de Londres — robusta", "US$/t", "cafe-bolsa-de-londres-liffe", 1, 2, "pontos", "bolsa"),
    ("b3", "B3 — arábica 4/5", "US$/sc", "cafe-arabica-4-5-b3-prego-regular", 1, 2, "%", "bolsa"),
    ("cepea", "Indicador Cepea/Esalq", "R$/sc", None, 1, 2, "%", "bolsa"),
    ("moedas", "Dólar Ptax (Banco Central)", "R$", None, 0, 0, "valor", "bolsa"),
    ("fisico_6_7", "Arábica tipo 6/7 bica corrida", "R$/sc", "cafe-arabica-mercado-fisico-tipo-6-7", 1, 2, "%", "fisico"),
    ("fisico_6_duro", "Arábica tipo 6 bebida dura", "R$/sc", "cafe-arabica-mercado-fisico-tipo-6-duro", 1, 2, "%", "fisico"),
    ("cereja", "Cereja descascado", "R$/sc", "cafe-cereja-descascado-mercado-fisico", 1, 2, "%", "fisico"),
    ("conilon_es", "Conilon — Espírito Santo", "R$/sc", "cafe-conillon-disponivel-vitoria-es", 1, 2, "%", "fisico"),
    ("agnocafe", "AgnoCafé — cotações por cidade", "R$/sc", None, 1, 0, "", "fisico"),
]
SERIE = {s[0]: s for s in SERIES}
FONTE_SERIE = {
    "ny": "ICE US via Notícias Agrícolas", "londres": "ICE Europe via Notícias Agrícolas",
    "b3": "B3 via Notícias Agrícolas", "cepea": "Cepea/Esalq via Notícias Agrícolas",
    "moedas": "Banco Central (Ptax)", "fisico_6_7": "Cooperativas via Notícias Agrícolas",
    "fisico_6_duro": "Cooperativas via Notícias Agrícolas", "cereja": "Cooperativas via Notícias Agrícolas",
    "conilon_es": "CCCV/Cooabriel via Notícias Agrícolas", "agnocafe": "AgnoCafé (agnocafe.com.br)",
}
PAGINAS_CEPEA = [("Arábica", "indicador-cepea-esalq-cafe-arabica"),
                 ("Conilon", "indicador-cepea-esalq-cafe-conillon")]


def _texto(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html or ""))).strip()


def _data_br(texto: str) -> date | None:
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def blocos_na(html: str) -> list[tuple[date, list[list[str]]]]:
    """Todos os fechamentos de uma página de cotação do Notícias Agrícolas.

    Cada página traz vários quadros "Fechamento: dd/mm/aaaa" + tabela (um por pregão)."""
    saida = []
    partes = re.split(r'<div[^>]*class="[^"]*\bcotacao\b[^"]*"[^>]*>', html)
    for parte in partes[1:]:
        dia = None
        fech = re.search(r"Fechamento:\s*(\d{2}/\d{2}/\d{4})", parte)
        if fech:
            dia = _data_br(fech.group(1))
        tabela = re.search(r"<table[^>]*cot-fisicas[^>]*>(.*?)</table>", parte, re.S)
        if not dia or not tabela:
            continue
        corpo = re.search(r"<tbody[^>]*>(.*?)</tbody>", tabela.group(1), re.S)
        linhas = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", corpo.group(1) if corpo else tabela.group(1), re.S):
            celulas = [_texto(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if celulas:
                linhas.append(celulas)
        saida.append((dia, linhas))
    return saida


def cidade_da_praca(praca: str) -> str:
    """'Patrocínio/MG (Expocaccer)' -> 'Patrocínio' ; 'Oeste da Bahia (AIBA)' -> 'Oeste da Bahia'"""
    nome = re.split(r"/|\(", praca or "")[0].strip()
    return nome


def _linha(grupo, item, dia, valor, variacao, tipo, cidade=None) -> dict:
    return {"grupo": grupo, "item": item[:140], "cidade": cidade, "data": dia,
            "valor": valor, "variacao": variacao, "tipo_variacao": tipo}


def serie_na(chave: str) -> list[dict]:
    """Lê uma página de bolsa ou de mercado físico do Notícias Agrícolas."""
    _, _, _, pagina, col_preco, col_var, tipo, categoria = SERIE[chave]
    linhas = []
    for dia, tabela in blocos_na(cotacoes.baixar(cotacoes.URL_NA + pagina)):
        prefixo = ""
        for celulas in tabela:
            if len(celulas) <= max(col_preco, col_var):
                continue
            if "***" in celulas[col_preco]:  # linha de título (ex.: nome da cooperativa)
                prefixo = celulas[0]
                continue
            valor = cotacoes._numero_br(celulas[col_preco].replace("%", ""))
            if valor is None:
                continue
            variacao = cotacoes._numero_br(celulas[col_var].replace("%", ""))
            if categoria == "bolsa":
                if not re.search(r"/\d{2}", celulas[0]):
                    continue
                item = cotacoes._mes_curto(celulas[0])
                linhas.append(_linha(chave, item, dia, valor, variacao, tipo))
            elif chave == "conilon_es":
                origem = "Vitória (CCCV)" if "Vitória" in prefixo else "São Gabriel (Cooabriel)" if prefixo else ""
                rotulo = re.sub(r"\s*\(.*\)", "", celulas[0]).strip()
                item = f"{origem} · {rotulo}" if origem else rotulo
                cidade = "Vitória" if "Vitória" in prefixo else "São Gabriel da Palha" if prefixo else None
                linhas.append(_linha(chave, item, dia, valor, variacao, tipo, cidade))
            else:
                linhas.append(_linha(chave, celulas[0], dia, valor, variacao, tipo,
                                     cidade_da_praca(celulas[0])))
    if not linhas:
        raise ValueError(f"sem cotações em {pagina}")
    return linhas


def serie_cepea() -> list[dict]:
    linhas = []
    for rotulo, pagina in PAGINAS_CEPEA:
        for dia, tabela in blocos_na(cotacoes.baixar(cotacoes.URL_NA + pagina)):
            for celulas in tabela:
                if len(celulas) < 3:
                    continue
                valor = cotacoes._numero_br(celulas[1])
                if valor is None:
                    continue
                linhas.append(_linha("cepea", rotulo, _data_br(celulas[0]) or dia, valor,
                                     cotacoes._numero_br(celulas[2].replace("%", "")), "%"))
    if not linhas:
        raise ValueError("Cepea sem dados")
    return linhas


def serie_ptax() -> list[dict]:
    fim = hoje_brasil()
    inicio = fim - timedelta(days=45)
    url = (
        "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
        "CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
        f"?@dataInicial='{inicio:%m-%d-%Y}'&@dataFinalCotacao='{fim:%m-%d-%Y}'"
        "&$format=json&$select=cotacaoVenda,dataHoraCotacao"
    )
    valores = json.loads(cotacoes.baixar(url)).get("value") or []
    linhas, anterior = [], None
    for v in valores:
        dia = date.fromisoformat(v["dataHoraCotacao"][:10])
        valor = float(v["cotacaoVenda"])
        variacao = round(valor - anterior, 4) if anterior is not None else None
        linhas.append(_linha("moedas", "Dólar Ptax", dia, valor, variacao, "valor"))
        anterior = valor
    if not linhas:
        raise ValueError("Ptax sem dados")
    return linhas


def agnocafe(html: str, dia: date) -> list[dict]:
    """Quadro "Cotações por Cidades" da AgnoCafé (lista #tickerbolsas)."""
    lista = re.search(r'<ul[^>]*id="tickerbolsas"[^>]*>(.*?)</ul>', html, re.S)
    if not lista:
        raise ValueError("quadro de cotações por cidade não encontrado na AgnoCafé")
    linhas = []
    for li in re.findall(r"<li[^>]*>(.*?)</li>", lista.group(1), re.S):
        nome = re.search(r"<font[^>]*>(.*?)</font>", li, re.S)
        if not nome:
            continue
        cidade = _texto(nome.group(1))
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", li, re.S):
            celulas = [_texto(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(celulas) != 2 or not celulas[1].startswith("R$"):
                continue
            texto_valor = celulas[1].replace("R$", "").strip()
            # a AgnoCafé escreve "1780,00" (sem ponto de milhar)
            valor = cotacoes._numero_br(texto_valor)
            if valor is None:
                continue
            eh_cidade = cidade.lower() != "indicadores"
            linhas.append(_linha("agnocafe", f"{cidade} · {celulas[0]}", dia, valor, None, "",
                                 cidade if eh_cidade else None))
    if not linhas:
        raise ValueError("AgnoCafé sem cotações por cidade")
    return linhas


def serie_agnocafe() -> list[dict]:
    return agnocafe(cotacoes.baixar(URL_AGNOCAFE), hoje_brasil())


# --------------------------------------------------------------------------- #
# Banco: gravar e ler o histórico
# --------------------------------------------------------------------------- #
def gravar_historico(db: Session, linhas: list[dict]) -> int:
    """Insere ou atualiza (grupo, item, data). Devolve quantas linhas mudaram."""
    if not linhas:
        return 0
    por_grupo: dict[str, list[dict]] = {}
    for linha in linhas:
        por_grupo.setdefault(linha["grupo"], []).append(linha)
    mudou = 0
    for grupo, itens in por_grupo.items():
        datas = [i["data"] for i in itens]
        existentes = {
            (r.item, r.data): r
            for r in db.query(CotacaoHistorico).filter(
                CotacaoHistorico.grupo == grupo,
                CotacaoHistorico.data >= min(datas), CotacaoHistorico.data <= max(datas))
        }
        vistos = set()
        for i in itens:
            chave = (i["item"], i["data"])
            if chave in vistos:
                continue
            vistos.add(chave)
            atual = existentes.get(chave)
            if atual is None:
                db.add(CotacaoHistorico(**i, atualizado_em=datetime.utcnow()))
                mudou += 1
            elif (atual.valor != i["valor"] or atual.variacao != i["variacao"]
                  or atual.cidade != i["cidade"]):
                atual.valor, atual.variacao, atual.cidade = i["valor"], i["variacao"], i["cidade"]
                atual.tipo_variacao = i["tipo_variacao"]
                atual.atualizado_em = datetime.utcnow()
                mudou += 1
    db.commit()
    return mudou


def _cache(db: Session, chave: str) -> tuple[dict | None, datetime | None]:
    registro = db.get(CacheExterno, chave)
    if not registro or not registro.conteudo:
        return None, None
    try:
        return json.loads(registro.conteudo), registro.atualizado_em
    except ValueError:
        return None, registro.atualizado_em


def _gravar_cache(db: Session, chave: str, dados: dict) -> None:
    registro = db.get(CacheExterno, chave)
    if registro is None:
        registro = CacheExterno(chave=chave)
        db.add(registro)
    registro.conteudo = json.dumps(dados, ensure_ascii=False)
    registro.atualizado_em = datetime.utcnow()
    db.commit()


def atualizar_mercado(db: Session, usar_agnocafe: bool = True) -> dict:
    """Lê todas as fontes em paralelo e grava no histórico. Fonte que falhar é só pulada."""
    tarefas = {chave: (lambda c=chave: serie_na(c)) for chave, *_ in SERIES
               if SERIE[chave][3]}
    tarefas["cepea"] = serie_cepea
    tarefas["moedas"] = serie_ptax
    if usar_agnocafe:
        tarefas["agnocafe"] = serie_agnocafe
    situacao = {}
    linhas = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futuros = {chave: pool.submit(funcao) for chave, funcao in tarefas.items()}
        for chave, futuro in futuros.items():
            try:
                resultado = futuro.result()
                linhas.extend(resultado)
                situacao[chave] = "ok"
            except Exception as erro:  # noqa: BLE001
                log.warning("Mercado: fonte %s indisponível: %s", chave, erro)
                situacao[chave] = "indisponível"
    gravar_historico(db, linhas)
    dados = {"atualizado_em": datetime.utcnow().isoformat(timespec="seconds") + "Z",
             "fontes": situacao}
    _gravar_cache(db, CHAVE_MERCADO, dados)
    return dados


def registrar_faixa(db: Session, faixa: dict) -> None:
    """Guarda no histórico o valor do dia do dólar, euro e DXY vistos na faixa."""
    linhas = []
    dia = hoje_brasil()
    for grupo in faixa.get("grupos", []):
        if grupo.get("chave") != "moedas" or grupo.get("atrasado"):
            continue
        for item in grupo.get("itens", []):
            if item["contrato"] in ("Dólar", "Euro", "DXY"):
                nome = {"Dólar": "Dólar comercial", "Euro": "Euro", "DXY": "DXY"}[item["contrato"]]
                linhas.append(_linha("moedas", nome, dia, item["cotacao"], item.get("variacao"), "valor"))
    try:
        gravar_historico(db, linhas)
    except Exception as erro:  # noqa: BLE001 — histórico é extra, nunca derruba a faixa
        db.rollback()
        log.info("Não gravou moedas no histórico: %s", erro)


def garantir_atualizado(db: Session, minutos: int = 30, usar_agnocafe: bool = True) -> dict:
    dados, quando = _cache(db, CHAVE_MERCADO)
    if dados and quando and datetime.utcnow() - quando < timedelta(minutes=max(minutos, 5)):
        return dados
    if not _trava_mercado.acquire(blocking=False):
        return dados or {"atualizado_em": None, "fontes": {}}
    try:
        return atualizar_mercado(db, usar_agnocafe)
    except Exception as erro:  # noqa: BLE001
        db.rollback()
        log.warning("Falha ao atualizar o mercado: %s", erro)
        return dados or {"atualizado_em": None, "fontes": {}}
    finally:
        _trava_mercado.release()


def _registro(r: CotacaoHistorico) -> dict:
    return {"grupo": r.grupo, "item": r.item, "cidade": r.cidade, "data": r.data.isoformat(),
            "valor": r.valor, "variacao": r.variacao, "tipo_variacao": r.tipo_variacao}


def _ordem_item(grupo: str, item: str) -> tuple:
    if SERIE.get(grupo, ("",) * 8)[7] == "bolsa":
        venc = cotacoes._vencimento(item)
        return (0, venc or (9999, 12), item)
    return (1, (0, 0), item)


def resumo(db: Session, meta: dict) -> dict:
    """Último fechamento de cada série + lista de cidades e itens (para os filtros)."""
    grupos = []
    cidades = set()
    for chave, titulo, unidade, _pag, _p, _v, _t, categoria in SERIES:
        ultima = (db.query(CotacaoHistorico.data).filter(CotacaoHistorico.grupo == chave)
                  .order_by(CotacaoHistorico.data.desc()).first())
        if not ultima:
            continue
        registros = (db.query(CotacaoHistorico)
                     .filter(CotacaoHistorico.grupo == chave, CotacaoHistorico.data == ultima[0]).all())
        itens_todos = sorted({r.item for r in db.query(CotacaoHistorico.item)
                              .filter(CotacaoHistorico.grupo == chave).distinct()},
                             key=lambda i: _ordem_item(chave, i))
        for r in db.query(CotacaoHistorico.cidade).filter(
                CotacaoHistorico.grupo == chave, CotacaoHistorico.cidade.isnot(None)).distinct():
            cidades.add(r.cidade)
        grupos.append({
            "chave": chave, "titulo": titulo, "unidade": unidade, "categoria": categoria,
            "fonte": FONTE_SERIE[chave], "data": ultima[0].isoformat(),
            "situacao": (meta.get("fontes") or {}).get(chave, ""),
            "itens": sorted((_registro(r) for r in registros),
                            key=lambda x: _ordem_item(chave, x["item"])),
            "todos_itens": itens_todos,
        })
    foco = [c for c in CIDADES_FOCO]
    outras = sorted((c for c in cidades if c not in CIDADES_FOCO), key=_sem_acento)
    return {"atualizado_em": meta.get("atualizado_em"), "grupos": grupos,
            "cidades": foco + outras, "cidades_foco": CIDADES_FOCO,
            "cidades_com_dados": sorted(cidades, key=_sem_acento)}


def historico(db: Session, grupo: str | None = None, item: str | None = None,
              cidade: str | None = None, de: date | None = None, ate: date | None = None,
              limite: int = 3000) -> list[dict]:
    consulta = db.query(CotacaoHistorico)
    if grupo:
        consulta = consulta.filter(CotacaoHistorico.grupo == grupo)
    if item:
        consulta = consulta.filter(CotacaoHistorico.item == item)
    if cidade:
        consulta = consulta.filter(CotacaoHistorico.cidade == cidade)
    if de:
        consulta = consulta.filter(CotacaoHistorico.data >= de)
    if ate:
        consulta = consulta.filter(CotacaoHistorico.data <= ate)
    registros = (consulta.order_by(CotacaoHistorico.data.desc(), CotacaoHistorico.grupo,
                                   CotacaoHistorico.item).limit(max(1, min(limite, 5000))).all())
    return [_registro(r) for r in registros]


# --------------------------------------------------------------------------- #
# Notícias
# --------------------------------------------------------------------------- #
FONTES_NOTICIAS = [
    {"chave": "na_cafe", "nome": "Notícias Agrícolas", "tipo": "na",
     "url": "https://www.noticiasagricolas.com.br/noticias/cafe/", "cultura": "Café"},
    {"chave": "canal_cafe", "nome": "Canal Rural", "tipo": "rss",
     "url": "https://www.canalrural.com.br/agricultura/cafe/feed/", "cultura": "Café"},
    {"chave": "canal_geral", "nome": "Canal Rural", "tipo": "rss",
     "url": "https://www.canalrural.com.br/feed/"},
    {"chave": "g1_agro", "nome": "g1 Agronegócios", "tipo": "rss",
     "url": "https://g1.globo.com/rss/g1/economia/agronegocios/"},
    {"chave": "g1_sul", "nome": "g1 Sul de Minas", "tipo": "rss", "so_agro": True,
     "url": "https://g1.globo.com/rss/g1/mg/sul-de-minas/", "regiao": "Sul de Minas"},
    {"chave": "g1_triangulo", "nome": "g1 Triângulo e Alto Paranaíba", "tipo": "rss", "so_agro": True,
     "url": "https://g1.globo.com/rss/g1/mg/triangulo-mineiro/", "regiao": "Triângulo e Alto Paranaíba"},
]

CULTURAS = [
    ("Café", r"\bcaf[eé]s?\b|cafeicult|cafezais|ar[aá]bica|conilon|robusta|florada|cooxup[eé]|expocaccer|minasul|cecaf[eé]"),
    ("Soja", r"\bsoja\b"),
    ("Milho", r"\bmilho\b"),
    ("Pecuária", r"\bboi\b|\bbois\b|\bgado\b|pecu[aá]ri|\bleite\b|bovin|su[ií]n|\bporcos?\b|frango|avicult|\barroba\b|\bcarnes?\b|couro"),
    ("Cana e etanol", r"\bcana\b|canavi|etanol|\ba[cç][uú]car\b"),
    ("Outras culturas", r"\bfeij[aã]o|\btrigo\b|algod[aã]o|\blaranja|citr[oi]|hortifr|\barroz\b|\bbatata|tomate|\bfrutas?\b"),
    ("Clima", r"geada|\bchuvas?\b|granizo|\bseca\b|estiagem|frente fria|el ni[nñ]o|la ni[nñ]a|previs[aã]o do tempo|temporal|temporais"),
]
AGRO_GERAL = (r"\bagro|agropecu|produtor(?:es)?\s+rura|\blavouras?\b|\bsafras?\b|colheita|plantio|"
              r"cooperativa|fazenda|\brural\b|agr[ií]col|agrot[oó]xic|fertiliz|defensivo|exporta[cç][aã]o")

REGIOES = [
    ("Patrocínio", r"(?<![Cc]om )(?<![Ss]ob )\bPatroc[ií]nio\b(?!\s+(?:de|do|da|dos|das|a|ao|oficial|master)\b)|"
                   r"Patroc[ií]nio\s*\(MG\)|Patroc[ií]nio,\s*MG"),
    ("Varginha", r"\bVarginha\b"),
    ("Araguari", r"\bAraguari\b"),
    ("Patos de Minas", r"\bPatos de Minas\b"),
    ("Sul de Minas", r"\bSul de Minas\b|Tr[eê]s Pontas|Guaxup[eé]|Tr[eê]s Cora[cç][oõ]es|Campos Gerais|"
                     r"\bAlfenas\b|Po[cç]os de Caldas|\bMachado\b|Carmo de Minas|Santo Ant[oô]nio do Amparo"),
    ("Triângulo e Alto Paranaíba", r"Cerrado Mineiro|Alto Parana[ií]ba|Tri[aâ]ngulo Mineiro|Monte Carmelo|"
                                   r"Carmo do Parana[ií]ba|Coromandel|Uberl[aâ]ndia|Uberaba|S[aã]o Gotardo|Ibi[aá]"),
]
REGIOES_FOCO = {"Patrocínio", "Varginha", "Araguari", "Patos de Minas"}


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn").lower()


def classificar(titulo: str, resumo_txt: str = "", categorias: list[str] | None = None) -> tuple[list[str], list[str], bool]:
    """Devolve (culturas, regiões, é_do_agro)."""
    texto = f"{titulo} {resumo_txt} {' '.join(categorias or [])}"
    culturas = [nome for nome, padrao in CULTURAS if re.search(padrao, texto, re.I)]
    regioes = [nome for nome, padrao in REGIOES if re.search(padrao, f"{titulo} {resumo_txt}")]
    agro_geral = bool(re.search(AGRO_GERAL, texto, re.I))
    eh_agro = bool([c for c in culturas if c != "Clima"]) or agro_geral  # só "chuva" não basta
    return culturas, regioes, eh_agro


def _cdata(texto: str) -> str:
    texto = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", texto or "", flags=re.S)
    return _texto(texto)


def ler_rss(xml: str) -> list[dict]:
    itens = []
    for bloco in re.findall(r"<item\b[^>]*>(.*?)</item>", xml, re.S):
        def tag(nome):
            m = re.search(rf"<{nome}\b[^>]*>(.*?)</{nome}>", bloco, re.S)
            return _cdata(m.group(1)) if m else ""
        titulo = tag("title")
        link = tag("link")
        if not titulo or not link.startswith("http"):
            continue
        quando = None
        try:
            quando = parsedate_to_datetime(tag("pubDate")).astimezone(timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError, IndexError):
            pass
        resumo_txt = tag("atom:subtitle") or tag("description")
        categorias = [_cdata(c) for c in re.findall(r"<category\b[^>]*>(.*?)</category>", bloco, re.S)]
        itens.append({"titulo": titulo, "link": link, "quando": quando,
                      "resumo": resumo_txt[:260], "categorias": categorias})
    return itens


def ler_na_noticias(html: str) -> list[dict]:
    itens = []
    padrao = r'<a\s+href="(/noticias/[a-z\-]+/\d+-[^"]+)"[^>]*>(.*?)</a>'
    for link, miolo in re.findall(padrao, html, re.S):
        hora = re.search(r'class="hora"[^>]*>\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}):(\d{2})', miolo)
        titulo = re.search(r"<h[23][^>]*>(.*?)</h[23]>", miolo, re.S)
        if not titulo:
            continue
        quando = None
        if hora:
            dia = _data_br(hora.group(1))
            if dia:  # horário de Brasília -> UTC
                quando = datetime(dia.year, dia.month, dia.day, int(hora.group(2)), int(hora.group(3))) + timedelta(hours=3)
        itens.append({"titulo": _texto(titulo.group(1)),
                      "link": "https://www.noticiasagricolas.com.br" + link,
                      "quando": quando, "resumo": "", "categorias": []})
    return itens


def _baixar_fonte(fonte: dict) -> list[dict]:
    conteudo = cotacoes.baixar(fonte["url"])
    brutos = ler_na_noticias(conteudo) if fonte["tipo"] == "na" else ler_rss(conteudo)
    saida = []
    for n in brutos:
        culturas, regioes, eh_agro = classificar(n["titulo"], n["resumo"], n["categorias"])
        if fonte.get("so_agro") and not eh_agro:
            continue
        if fonte.get("cultura") and fonte["cultura"] not in culturas:
            culturas.insert(0, fonte["cultura"])
        if fonte.get("regiao") and fonte["regiao"] not in regioes:
            regioes.append(fonte["regiao"])
        if not culturas:
            culturas = ["Geral"]
        saida.append({
            "titulo": n["titulo"], "link": n["link"], "resumo": n["resumo"],
            "fonte": fonte["nome"],
            "quando": n["quando"].isoformat(timespec="minutes") + "Z" if n["quando"] else None,
            "culturas": culturas, "regioes": regioes,
            "foco": bool(REGIOES_FOCO.intersection(regioes)),
        })
    return saida


def _chave_titulo(titulo: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _sem_acento(titulo))[:90]


def atualizar_noticias(db: Session, anterior: dict | None = None, dias_guardar: int = 60) -> dict:
    novas, situacao = [], {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futuros = {f["chave"]: pool.submit(_baixar_fonte, f) for f in FONTES_NOTICIAS}
        for chave, futuro in futuros.items():
            try:
                novas.extend(futuro.result())
                situacao[chave] = "ok"
            except Exception as erro:  # noqa: BLE001
                log.warning("Notícias: fonte %s indisponível: %s", chave, erro)
                situacao[chave] = "indisponível"
    limite = (datetime.utcnow() - timedelta(days=dias_guardar)).isoformat()
    juntas: dict[str, dict] = {}
    # as antigas primeiro; a leitura nova sobrescreve (fica com a classificação atual)
    for n in list((anterior or {}).get("itens", [])) + novas:
        if n.get("quando") and n["quando"] < limite:
            continue
        chave = _chave_titulo(n["titulo"])
        ja = juntas.get(chave)
        if ja and ja["link"] != n["link"]:
            # mesma notícia em dois sites: mantém a primeira e junta as marcações
            ja["culturas"] = list(dict.fromkeys(ja["culturas"] + n["culturas"]))
            ja["regioes"] = list(dict.fromkeys(ja["regioes"] + n["regioes"]))
            ja["foco"] = ja["foco"] or n["foco"]
            continue
        juntas[chave] = n
    itens = sorted(juntas.values(), key=lambda n: n.get("quando") or "", reverse=True)[:600]
    dados = {"atualizado_em": datetime.utcnow().isoformat(timespec="seconds") + "Z",
             "fontes": situacao, "itens": itens}
    if itens:
        _gravar_cache(db, CHAVE_NOTICIAS, dados)
    return dados


def obter_noticias(db: Session, minutos: int = 20) -> dict:
    dados, quando = _cache(db, CHAVE_NOTICIAS)
    if dados and quando and datetime.utcnow() - quando < timedelta(minutes=max(minutos, 5)):
        return dados
    if not _trava_noticias.acquire(blocking=False):
        return dados or {"atualizado_em": None, "fontes": {}, "itens": []}
    try:
        return atualizar_noticias(db, dados)
    except Exception as erro:  # noqa: BLE001
        db.rollback()
        log.warning("Falha ao atualizar notícias: %s", erro)
        return dados or {"atualizado_em": None, "fontes": {}, "itens": []}
    finally:
        _trava_noticias.release()


def filtrar_noticias(itens: list[dict], cultura: str = "", regiao: str = "", busca: str = "",
                     de: date | None = None, ate: date | None = None) -> list[dict]:
    saida = []
    termo = _sem_acento(busca.strip())
    for n in itens:
        if cultura and cultura not in n.get("culturas", []):
            continue
        if regiao == "foco":
            if not n.get("foco"):
                continue
        elif regiao and regiao not in n.get("regioes", []):
            continue
        if termo and termo not in _sem_acento(f"{n['titulo']} {n.get('resumo', '')}"):
            continue
        if (de or ate) and n.get("quando"):
            # data no horário de Brasília
            dia = (datetime.fromisoformat(n["quando"].rstrip("Z")) - timedelta(hours=3)).date()
            if (de and dia < de) or (ate and dia > ate):
                continue
        saida.append(n)
    return saida
