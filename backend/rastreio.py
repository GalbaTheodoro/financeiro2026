"""Rastreabilidade do lote do armazém — ida e volta.

Um lote nasce de três jeitos e pode seguir por quatro caminhos::

    nasce:   guia de ENTRADA   (lote de origem: "15/1")
             TRANSFERÊNCIA     (lote novo do outro dono: "15/1T", todo ele vindo de um lote)
             SERVIÇO           (lote resultado: "S3/1", feito do café despejado na guia)

    segue:   transferência, despejo em guia de serviço, saída — ou fica no saldo

**Para onde foi (ida).** Parte-se do lote com todas as sacas que entraram nele
e segue-se cada saída de café: o que foi transferido vira o lote novo; o que
foi despejado num serviço vira, na proporção, os lotes resultado (o que não
virou resultado é a quebra); o que saiu por guia de saída é um destino final;
o que sobrou é o saldo de hoje. As contas são proporcionais: se um lote com
1/3 de café deste lote é despejado, 1/3 de cada resultado é "deste lote".

**De que é feito (volta).** O caminho contrário: a composição do lote em
lotes de ENTRADA. Transferência herda a composição do lote de origem; o
resultado de um serviço é a mistura dos despejos, cada um pesando as sacas
que despejou. A soma das frações dá 100%.

Só contam guias FECHADAS — rascunho e cancelada não movimentam o armazém.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from .models import (
    GuiaEntrada,
    GuiaRemocao,
    GuiaSaida,
    GuiaSaidaItem,
    GuiaServico,
    GuiaServicoDespejo,
    GuiaTransferencia,
    GuiaTransferenciaItem,
    LoteArmazem,
)
from .routers.wms import _somar_saldos

PROFUNDIDADE_MAXIMA = 40
MINIMO = 0.005


def _r(v: float) -> float:
    return round(float(v or 0), 2)


class Rastreio:
    """Carrega uma vez os movimentos fechados da empresa e responde ida e volta."""

    def __init__(self, db: Session, empresa_id: int):
        self.db = db
        self.empresa_id = empresa_id
        self.lotes: dict[int, LoteArmazem] = {
            l.id: l for l in db.query(LoteArmazem).filter(LoteArmazem.empresa_id == empresa_id)}

        # saídas de café de cada lote, por guia fechada
        self.transferencias: dict[int, list] = defaultdict(list)
        for item, guia in (db.query(GuiaTransferenciaItem, GuiaTransferencia)
                           .join(GuiaTransferencia, GuiaTransferenciaItem.guia_id == GuiaTransferencia.id)
                           .filter(GuiaTransferencia.empresa_id == empresa_id,
                                   GuiaTransferencia.status == "FECHADA")):
            self.transferencias[item.lote_id].append((item, guia))
        self.despejos: dict[int, list] = defaultdict(list)
        self.despejos_da_guia: dict[int, list] = defaultdict(list)
        self.guias_servico: dict[int, GuiaServico] = {}
        for d, guia in (db.query(GuiaServicoDespejo, GuiaServico)
                        .join(GuiaServico, GuiaServicoDespejo.guia_id == GuiaServico.id)
                        .filter(GuiaServico.empresa_id == empresa_id, GuiaServico.status == "FECHADA")):
            self.despejos[d.lote_id].append((d, guia))
            self.despejos_da_guia[guia.id].append(d)
            self.guias_servico[guia.id] = guia
        self.saidas: dict[int, list] = defaultdict(list)
        for item, guia in (db.query(GuiaSaidaItem, GuiaSaida)
                           .join(GuiaSaida, GuiaSaidaItem.guia_id == GuiaSaida.id)
                           .filter(GuiaSaida.empresa_id == empresa_id, GuiaSaida.status == "FECHADA")):
            self.saidas[item.lote_id].append((item, guia))
        self.remocoes: dict[int, list] = defaultdict(list)
        for r in db.query(GuiaRemocao).filter(GuiaRemocao.empresa_id == empresa_id,
                                              GuiaRemocao.status == "ATIVA"):
            self.remocoes[r.lote_id].append(r)
        self.guias_entrada = {g.id: g for g in db.query(GuiaEntrada).filter(
            GuiaEntrada.empresa_id == empresa_id)}

        # saldo de hoje de cada lote (somando todos os armazéns)
        saldos = _somar_saldos(db, empresa_id)
        por_chave: dict[tuple, float] = defaultdict(float)
        for (_a, dep, prod, cod), v in saldos.items():
            por_chave[(dep, prod, cod)] += v["sacas"]
        self.saldo = {l.id: max(0.0, por_chave.get((l.depositante_id, l.produto_id, l.codigo.upper()), 0.0))
                      for l in self.lotes.values()}

    # ----------------------------------------------------------------- dados
    def ficha(self, lote: LoteArmazem) -> dict:
        if lote.lote_origem_id:
            nasceu, guia = "TRANSFERENCIA", self._numero_transferencia(lote)
        elif lote.guia_servico_id:
            g = self.guias_servico.get(lote.guia_servico_id)
            nasceu, guia = "SERVICO", g.numero if g else None
        else:
            g = self.guias_entrada.get(lote.guia_id)
            nasceu, guia = "ENTRADA", g.numero if g else None
        return {
            "id": lote.id, "codigo": lote.codigo,
            "data": lote.data_entrada.isoformat() if lote.data_entrada else None,
            "cliente": lote.depositante.nome if lote.depositante else "-",
            "armazem": lote.armazem.nome if lote.armazem else "-",
            "safra": lote.safra or "", "peneira": lote.peneira or "", "padrao": lote.padrao or "",
            "sacas_entrada": _r(lote.sacas), "saldo": _r(self.saldo.get(lote.id, 0.0)),
            "nasceu": nasceu, "guia": guia,
        }

    def _numero_transferencia(self, lote: LoteArmazem):
        if lote.guia_transferencia_id:
            g = self.db.get(GuiaTransferencia, lote.guia_transferencia_id)
            return g.numero if g else None
        return None

    # ------------------------------------------------------------- volta
    def composicao(self, lote_id: int, profundidade: int = 0, caminho: frozenset = frozenset()) -> dict[int, float]:
        """{id do lote de entrada: fração} — a soma dá 1."""
        lote = self.lotes.get(lote_id)
        if lote is None or profundidade > PROFUNDIDADE_MAXIMA or lote_id in caminho:
            return {lote_id: 1.0}
        caminho = caminho | {lote_id}
        if lote.lote_origem_id and lote.lote_origem_id in self.lotes:
            return self.composicao(lote.lote_origem_id, profundidade + 1, caminho)
        if lote.guia_servico_id:
            despejos = self.despejos_da_guia.get(lote.guia_servico_id, [])
            total = sum(float(d.sacas or 0) for d in despejos)
            if total > 0:
                mistura: dict[int, float] = defaultdict(float)
                for d in despejos:
                    peso = float(d.sacas or 0) / total
                    for origem, fracao in self.composicao(d.lote_id, profundidade + 1, caminho).items():
                        mistura[origem] += peso * fracao
                return dict(mistura)
        return {lote_id: 1.0}

    def arvore_origem(self, lote_id: int, fracao: float = 1.0, profundidade: int = 0,
                      caminho: frozenset = frozenset()) -> dict:
        """A árvore "de onde veio": cada lote com os lotes que o formaram."""
        lote = self.lotes[lote_id]
        no = dict(self.ficha(lote), fracao=round(fracao, 6), pais=[])
        if profundidade > PROFUNDIDADE_MAXIMA or lote_id in caminho:
            return no
        caminho = caminho | {lote_id}
        if lote.lote_origem_id and lote.lote_origem_id in self.lotes:
            no["pais"].append(self.arvore_origem(lote.lote_origem_id, fracao, profundidade + 1, caminho))
        elif lote.guia_servico_id:
            despejos = self.despejos_da_guia.get(lote.guia_servico_id, [])
            total = sum(float(d.sacas or 0) for d in despejos)
            por_lote: dict[int, float] = defaultdict(float)
            for d in despejos:
                por_lote[d.lote_id] += float(d.sacas or 0)
            g = self.guias_servico.get(lote.guia_servico_id)
            no["servico"] = g.servico if g else ""
            for origem_id, sacas in por_lote.items():
                if origem_id in self.lotes and total > 0:
                    pai = self.arvore_origem(origem_id, fracao * sacas / total, profundidade + 1, caminho)
                    pai["sacas_despejadas"] = _r(sacas)
                    no["pais"].append(pai)
        return no

    # --------------------------------------------------------------- ida
    def arvore_destino(self, lote_id: int, rastreadas: float, profundidade: int = 0,
                       caminho: frozenset = frozenset()) -> dict:
        """A árvore "para onde foi": ``rastreadas`` são as sacas deste lote que
        vieram do lote de partida (no lote de partida, todas)."""
        lote = self.lotes[lote_id]
        entrada = float(lote.sacas or 0)
        rho = (rastreadas / entrada) if entrada > 0 else 0.0
        no = dict(self.ficha(lote), rastreadas=_r(rastreadas),
                  saldo_rastreado=_r(self.saldo.get(lote_id, 0.0) * rho), eventos=[])
        if profundidade > PROFUNDIDADE_MAXIMA or lote_id in caminho:
            return no
        caminho = caminho | {lote_id}
        eventos = []

        # transferências: agrupadas por guia (uma guia gera um lote novo por lote de origem)
        por_guia: dict[int, dict] = {}
        for item, guia in self.transferencias.get(lote_id, []):
            e = por_guia.setdefault(guia.id, {"guia": guia, "sacas": 0.0, "lote_novo_id": item.lote_novo_id})
            e["sacas"] += float(item.sacas or 0)
            e["lote_novo_id"] = e["lote_novo_id"] or item.lote_novo_id
        for e in por_guia.values():
            g = e["guia"]
            ev = {"tipo": "TRANSFERENCIA", "data": g.data.isoformat() if g.data else None, "guia": g.numero,
                  "sacas": _r(e["sacas"] * rho), "para": g.cliente_novo.nome if g.cliente_novo else "-",
                  "filho": None}
            if e["lote_novo_id"] in self.lotes:
                ev["filho"] = self.arvore_destino(e["lote_novo_id"], e["sacas"] * rho, profundidade + 1, caminho)
            eventos.append(ev)

        # despejos em guias de serviço
        por_servico: dict[int, float] = defaultdict(float)
        for d, guia in self.despejos.get(lote_id, []):
            por_servico[guia.id] += float(d.sacas or 0)
        for guia_id, sacas in por_servico.items():
            g = self.guias_servico[guia_id]
            total = sum(float(x.sacas or 0) for x in self.despejos_da_guia.get(guia_id, []))
            parte = (sacas / total) if total > 0 else 0.0
            filhos, virou = [], 0.0
            for r in g.resultados:
                vindo = float(r.sacas or 0) * parte * rho
                virou += vindo
                if r.lote_gerado_id in self.lotes and vindo > MINIMO:
                    filho = self.arvore_destino(r.lote_gerado_id, vindo, profundidade + 1, caminho)
                    filho["parte_do_resultado"] = round(parte * rho, 6)
                    filhos.append(filho)
            eventos.append({
                "tipo": "SERVICO", "data": g.data.isoformat() if g.data else None, "guia": g.numero,
                "servico": g.servico or "", "sacas": _r(sacas * rho),
                "quebra": _r(sacas * rho - virou), "parte": round(parte, 6), "filhos": filhos,
            })

        # saídas
        for item, guia in self.saidas.get(lote_id, []):
            eventos.append({
                "tipo": "SAIDA", "data": guia.data.isoformat() if guia.data else None, "guia": guia.numero,
                "sacas": _r(float(item.sacas or 0) * rho),
                "para": " · ".join(x for x in (
                    guia.destinatario.nome if getattr(guia, "destinatario", None) else "",
                    guia.destino or "") if x) or "-",
                "contrato": guia.contrato.numero if guia.contrato else None,
            })

        # remoções (mudança de lugar, não de dono)
        for r in self.remocoes.get(lote_id, []):
            eventos.append({"tipo": "REMOCAO", "data": r.data.isoformat() if r.data else None,
                            "guia": r.numero, "sacas": None,
                            "para": r.armazem_destino.nome if getattr(r, "armazem_destino", None) else ""})
        eventos.sort(key=lambda e: (e["data"] or "", e["tipo"]))
        no["eventos"] = eventos
        return no


def destinos_finais(no: dict) -> dict:
    """Achata a árvore de ida: o que saiu, o que está em saldo e a quebra."""
    saidas, saldos, quebra = [], [], 0.0

    def andar(n):
        nonlocal quebra
        if n["saldo_rastreado"] > MINIMO:
            saldos.append({"codigo": n["codigo"], "cliente": n["cliente"], "armazem": n["armazem"],
                           "sacas": n["saldo_rastreado"], "id": n["id"]})
        for e in n["eventos"]:
            if e["tipo"] == "SAIDA" and e["sacas"] > MINIMO:
                saidas.append({"lote": n["codigo"], "cliente": n["cliente"], "data": e["data"],
                               "guia": e["guia"], "para": e["para"], "contrato": e.get("contrato"),
                               "sacas": e["sacas"]})
            elif e["tipo"] == "SERVICO":
                quebra += e["quebra"]
                for f in e["filhos"]:
                    andar(f)
            elif e["tipo"] == "TRANSFERENCIA" and e.get("filho"):
                andar(e["filho"])

    andar(no)
    return {"saidas": saidas, "saldos": saldos, "quebra": _r(quebra),
            "total_saidas": _r(sum(s["sacas"] for s in saidas)),
            "total_saldo": _r(sum(s["sacas"] for s in saldos))}


def rastrear(db: Session, empresa_id: int, lote_id: int) -> dict:
    r = Rastreio(db, empresa_id)
    lote = r.lotes.get(lote_id)
    if lote is None:
        return {}
    comp = r.composicao(lote_id)
    entrada = float(lote.sacas or 0)
    saldo = r.saldo.get(lote_id, 0.0)
    composicao = []
    for origem_id, fracao in sorted(comp.items(), key=lambda x: -x[1]):
        o = r.lotes.get(origem_id)
        if o is None:
            continue
        ficha = r.ficha(o)
        composicao.append(dict(ficha, fracao=round(fracao, 6), pct=round(fracao * 100, 2),
                               sacas_no_lote=_r(fracao * entrada), sacas_no_saldo=_r(fracao * saldo)))
    ida = r.arvore_destino(lote_id, entrada)
    return {
        "lote": r.ficha(lote),
        "composicao": composicao,
        "origem": r.arvore_origem(lote_id),
        "destino": ida,
        "finais": destinos_finais(ida),
    }


def lotes_para_escolher(db: Session, empresa_id: int, busca: str | None = None, limite: int = 60) -> list[dict]:
    r_q = db.query(LoteArmazem).filter(LoteArmazem.empresa_id == empresa_id)
    texto = (busca or "").strip()
    if texto:
        r_q = r_q.filter(LoteArmazem.codigo.ilike(f"%{texto}%"))
    return [{"id": l.id, "codigo": l.codigo, "cliente": l.depositante.nome if l.depositante else "-",
             "data": l.data_entrada.isoformat() if l.data_entrada else None, "safra": l.safra or "",
             "padrao": l.padrao or "", "peneira": l.peneira or ""}
            for l in r_q.order_by(LoteArmazem.data_entrada.desc(), LoteArmazem.id.desc()).limit(limite)]
