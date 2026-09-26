"""Relatórios gerenciais e contábeis."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import estoque
from ..database import get_db
from ..deps import exigir_modulo
from ..models import (
    Banco,
    CentroCusto,
    Contrato,
    ContaContabil,
    Lancamento,
    MovimentoCaixa,
    Operacao,
    Parcela,
    Parceiro,
    Partida,
)
from ..relatorios_dre import GRUPOS_DRE, ROTULO, SINAL, SUBTOTAIS
from ..utils import dinheiro, parse_data

# O menu deste módulo pode ser tirado de um plano (ou de um cliente) na área
# do administrador. Quem fecha a porta de verdade é a dependência abaixo:
# esconder o botão no menu não impede ninguém de chamar a rota pelo endereço.
router = APIRouter(
    prefix="/api/relatorios", tags=["relatorios"],
    dependencies=[Depends(exigir_modulo("FINANCEIRO"))],
)


def _periodo(de: str | None, ate: str | None):
    hoje = date.today()
    inicio = parse_data(de, date(hoje.year, hoje.month, 1))
    fim = parse_data(ate, hoje)
    if inicio > fim:
        raise HTTPException(400, "Data inicial maior que a data final")
    return inicio, fim


def _faixa_aging(dias: int) -> str:
    if dias <= 0:
        return "A vencer"
    if dias <= 30:
        return "1 a 30 dias"
    if dias <= 60:
        return "31 a 60 dias"
    if dias <= 90:
        return "61 a 90 dias"
    return "Acima de 90 dias"


# --------------------------------------------------------------------------- #
# Contas a receber / a pagar
# --------------------------------------------------------------------------- #
@router.get("/titulos")
def relatorio_titulos(
    empresa_id: int,
    tipo: str,                       # RECEBER | PAGAR
    situacao: str = "ABERTAS",       # ABERTAS | PAGAS | VENCIDAS | TODAS
    de: str | None = None,
    ate: str | None = None,
    base_data: str = "vencimento",   # vencimento | emissao | competencia | pagamento
    parceiro_id: int | None = None,
    centro_custo_id: int | None = None,
    conta_contabil_id: int | None = None,
    operacao_id: int | None = None,
    db: Session = Depends(get_db),
):
    inicio, fim = _periodo(de, ate)
    query = (
        db.query(Parcela)
        .join(Lancamento)
        .options(joinedload(Parcela.lancamento).joinedload(Lancamento.itens))
        .filter(Lancamento.empresa_id == empresa_id, Lancamento.tipo == tipo)
    )
    if base_data == "emissao":
        query = query.filter(Lancamento.data_emissao.between(inicio, fim))
    elif base_data == "competencia":
        query = query.filter(Lancamento.data_competencia.between(inicio, fim))
    elif base_data == "pagamento":
        query = query.filter(Parcela.data_ultima_baixa.between(inicio, fim))
    else:
        query = query.filter(Parcela.data_vencimento.between(inicio, fim))

    if situacao == "ABERTAS":
        query = query.filter(Parcela.status.in_(("ABERTO", "PARCIAL")))
    elif situacao == "PAGAS":
        query = query.filter(Parcela.status == "PAGO")
    elif situacao == "VENCIDAS":
        query = query.filter(
            Parcela.status.in_(("ABERTO", "PARCIAL")), Parcela.data_vencimento < date.today()
        )
    else:
        query = query.filter(Parcela.status != "CANCELADO")

    if parceiro_id:
        query = query.filter(Lancamento.parceiro_id == parceiro_id)
    if operacao_id:
        query = query.filter(Lancamento.operacao_id == operacao_id)

    parcelas = query.order_by(Parcela.data_vencimento, Parcela.id).all()

    hoje = date.today()
    linhas, aging = [], defaultdict(float)
    total = baixado = saldo = 0.0
    for p in parcelas:
        lanc = p.lancamento
        itens = lanc.itens
        if centro_custo_id and not any(i.centro_custo_id == centro_custo_id for i in itens):
            continue
        if conta_contabil_id and not any(i.conta_contabil_id == conta_contabil_id for i in itens):
            continue
        dias = (hoje - p.data_vencimento).days if p.status in ("ABERTO", "PARCIAL") else 0
        linha = {
            "parcela_id": p.id,
            "lancamento_id": lanc.id,
            "documento": lanc.numero_documento,
            "descricao": lanc.descricao,
            "parceiro": lanc.parceiro.nome if lanc.parceiro else "-",
            "operacao": lanc.operacao.nome if lanc.operacao else "-",
            "classificacao": " | ".join(
                f"{i.conta_contabil.codigo} {i.conta_contabil.nome}" for i in itens if i.conta_contabil
            ),
            "centro_custo": " | ".join(sorted({i.centro_custo.nome for i in itens if i.centro_custo})),
            "emissao": lanc.data_emissao.isoformat(),
            "competencia": lanc.data_competencia.isoformat(),
            "vencimento": p.data_vencimento.isoformat(),
            "parcela": f"{p.numero}/{len(lanc.parcelas)}",
            "valor": dinheiro(p.valor),
            "baixado": dinheiro(p.valor_baixado),
            "juros_multa": dinheiro(p.juros_multa),
            "desconto": dinheiro(p.desconto),
            "saldo": p.saldo,
            "status": p.status,
            "dias_atraso": max(dias, 0),
            "ultima_baixa": p.data_ultima_baixa.isoformat() if p.data_ultima_baixa else None,
        }
        linhas.append(linha)
        total += linha["valor"]
        baixado += linha["baixado"]
        saldo += linha["saldo"]
        if p.status in ("ABERTO", "PARCIAL"):
            aging[_faixa_aging(dias)] += linha["saldo"]

    ordem = ["A vencer", "1 a 30 dias", "31 a 60 dias", "61 a 90 dias", "Acima de 90 dias"]
    return {
        "periodo": {"de": inicio.isoformat(), "ate": fim.isoformat(), "base": base_data},
        "tipo": tipo,
        "linhas": linhas,
        "totais": {
            "quantidade": len(linhas),
            "valor": round(total, 2),
            "baixado": round(baixado, 2),
            "saldo": round(saldo, 2),
        },
        "aging": [
            {"faixa": f, "valor": round(aging.get(f, 0), 2)} for f in ordem if aging.get(f)
        ],
    }


# --------------------------------------------------------------------------- #
# Fluxo de caixa
# --------------------------------------------------------------------------- #
@router.get("/fluxo-caixa")
def fluxo_caixa(
    empresa_id: int,
    de: str | None = None,
    ate: str | None = None,
    banco_id: int | None = None,
    agrupar: str = "dia",       # dia | mes
    incluir_previsto: bool = False,
    db: Session = Depends(get_db),
):
    inicio, fim = _periodo(de, ate)
    bancos = db.query(Banco).filter(Banco.empresa_id == empresa_id)
    if banco_id:
        bancos = bancos.filter(Banco.id == banco_id)
    bancos = bancos.all()
    ids = [b.id for b in bancos]
    saldo_anterior = sum(dinheiro(b.saldo_inicial) for b in bancos)

    if ids:
        anteriores = (
            db.query(MovimentoCaixa)
            .filter(MovimentoCaixa.banco_id.in_(ids), MovimentoCaixa.data < inicio)
            .all()
        )
        for m in anteriores:
            saldo_anterior += dinheiro(m.valor) if m.tipo == "E" else -dinheiro(m.valor)

    movimentos = (
        db.query(MovimentoCaixa)
        .filter(
            MovimentoCaixa.banco_id.in_(ids or [0]),
            MovimentoCaixa.data.between(inicio, fim),
        )
        .all()
    )

    def chave(d: date) -> str:
        return d.strftime("%Y-%m") if agrupar == "mes" else d.isoformat()

    grupos = defaultdict(lambda: {"entradas": 0.0, "saidas": 0.0, "prev_entradas": 0.0, "prev_saidas": 0.0})
    for m in movimentos:
        alvo = grupos[chave(m.data)]
        if m.tipo == "E":
            alvo["entradas"] += dinheiro(m.valor)
        else:
            alvo["saidas"] += dinheiro(m.valor)

    if incluir_previsto:
        parcelas = (
            db.query(Parcela)
            .join(Lancamento)
            .filter(
                Lancamento.empresa_id == empresa_id,
                Parcela.status.in_(("ABERTO", "PARCIAL")),
                Parcela.data_vencimento.between(inicio, fim),
            )
            .all()
        )
        for p in parcelas:
            alvo = grupos[chave(p.data_vencimento)]
            if p.lancamento.tipo == "RECEBER":
                alvo["prev_entradas"] += p.saldo
            else:
                alvo["prev_saidas"] += p.saldo

    linhas = []
    saldo = round(saldo_anterior, 2)
    saldo_prev = saldo
    for k in sorted(grupos):
        g = grupos[k]
        resultado = round(g["entradas"] - g["saidas"], 2)
        saldo = round(saldo + resultado, 2)
        prev = round(g["prev_entradas"] - g["prev_saidas"], 2)
        saldo_prev = round(saldo_prev + resultado + prev, 2)
        linhas.append(
            {
                "periodo": k,
                "entradas": round(g["entradas"], 2),
                "saidas": round(g["saidas"], 2),
                "resultado": resultado,
                "saldo": saldo,
                "previsto_entradas": round(g["prev_entradas"], 2),
                "previsto_saidas": round(g["prev_saidas"], 2),
                "saldo_projetado": saldo_prev,
            }
        )

    return {
        "periodo": {"de": inicio.isoformat(), "ate": fim.isoformat()},
        "saldo_anterior": round(saldo_anterior, 2),
        "linhas": linhas,
        "totais": {
            "entradas": round(sum(l["entradas"] for l in linhas), 2),
            "saidas": round(sum(l["saidas"] for l in linhas), 2),
            "resultado": round(sum(l["resultado"] for l in linhas), 2),
            "saldo_final": saldo,
            "saldo_projetado": saldo_prev,
        },
    }


# --------------------------------------------------------------------------- #
# Relatórios analíticos por classificação
# --------------------------------------------------------------------------- #
def _partidas_periodo(db: Session, empresa_id: int, inicio: date, fim: date, regime: str):
    coluna = Partida.competencia if regime == "competencia" else Partida.data
    return (
        db.query(Partida)
        .options(joinedload(Partida.conta_debito), joinedload(Partida.conta_credito))
        .filter(Partida.empresa_id == empresa_id, coluna.between(inicio, fim))
        .all()
    )


def _classificar(partida: Partida):
    """Devolve (conta_resultado, valor_com_sinal) quando a partida envolve
    uma conta de resultado (receita, custo ou despesa)."""
    resultado = []
    for conta, sinal in ((partida.conta_debito, -1), (partida.conta_credito, 1)):
        if conta is None:
            continue
        if conta.tipo in ("RECEITA", "CUSTO", "DESPESA"):
            # Efeito no resultado: crédito aumenta o lucro, débito reduz.
            resultado.append((conta, round(dinheiro(partida.valor) * sinal, 2)))
    return resultado


def _eh_receita(conta: ContaContabil) -> bool:
    """Deduções da receita (tipo RECEITA com natureza devedora) contam como redutoras."""
    return conta.tipo == "RECEITA" and conta.natureza == "C"


@router.get("/por-classificacao")
def por_classificacao(
    empresa_id: int,
    agrupar_por: str = "conta",     # conta | centro_custo | operacao | parceiro
    de: str | None = None,
    ate: str | None = None,
    regime: str = "competencia",    # competencia | caixa
    natureza: str | None = None,    # RECEITA | DESPESA
    db: Session = Depends(get_db),
):
    inicio, fim = _periodo(de, ate)
    partidas = _partidas_periodo(db, empresa_id, inicio, fim, regime)

    centros = {c.id: c for c in db.query(CentroCusto).filter(CentroCusto.empresa_id == empresa_id)}
    operacoes = {o.id: o for o in db.query(Operacao).filter(Operacao.empresa_id == empresa_id)}
    parceiros = {p.id: p for p in db.query(Parceiro).filter(Parceiro.empresa_id == empresa_id)}

    grupos = defaultdict(lambda: {"receitas": 0.0, "despesas": 0.0})
    for partida in partidas:
        for conta, valor in _classificar(partida):
            if agrupar_por == "centro_custo":
                cc = centros.get(partida.centro_custo_id)
                chave = (cc.codigo if cc else "-", cc.nome if cc else "Sem centro de custo")
            elif agrupar_por == "operacao":
                op = operacoes.get(partida.operacao_id)
                chave = (op.codigo if op else "-", op.nome if op else "Sem operação")
            elif agrupar_por == "parceiro":
                pc = parceiros.get(partida.parceiro_id)
                chave = (str(pc.id) if pc else "-", pc.nome if pc else "Sem cliente/fornecedor")
            else:
                chave = (conta.codigo, conta.nome)
            alvo = grupos[chave]
            if _eh_receita(conta):
                alvo["receitas"] += valor
            else:
                alvo["despesas"] += -valor

    linhas = []
    for (codigo, nome), v in sorted(grupos.items()):
        receitas, despesas = round(v["receitas"], 2), round(v["despesas"], 2)
        if natureza == "RECEITA" and not receitas:
            continue
        if natureza == "DESPESA" and not despesas:
            continue
        linhas.append(
            {
                "codigo": codigo,
                "nome": nome,
                "receitas": receitas,
                "despesas": despesas,
                "resultado": round(receitas - despesas, 2),
            }
        )

    total_receitas = round(sum(l["receitas"] for l in linhas), 2)
    total_despesas = round(sum(l["despesas"] for l in linhas), 2)
    for l in linhas:
        base = total_despesas if (l["despesas"] and not l["receitas"]) else total_receitas
        l["percentual"] = round((l["despesas"] or l["receitas"]) / base * 100, 2) if base else 0
    return {
        "periodo": {"de": inicio.isoformat(), "ate": fim.isoformat(), "regime": regime},
        "agrupar_por": agrupar_por,
        "linhas": linhas,
        "totais": {
            "receitas": total_receitas,
            "despesas": total_despesas,
            "resultado": round(total_receitas - total_despesas, 2),
        },
    }


# --------------------------------------------------------------------------- #
# Produtos por categoria e por marca
# --------------------------------------------------------------------------- #
@router.get("/produtos-classificacao")
def produtos_por_classificacao(
    empresa_id: int,
    agrupar_por: str = "categoria",   # categoria | marca
    de: str | None = None,
    ate: str | None = None,
    db: Session = Depends(get_db),
):
    """Quanto saiu e quanto sobrou, somado por categoria (ou por marca).

    Duas leituras diferentes, de propósito, porque respondem a perguntas
    diferentes:

    * **vendido** vem dos itens das notas de **saída autorizadas** no período —
      é faturamento, com o preço que foi cobrado;
    * **estoque** é a foto de **agora**, pelo custo médio. Não tem período: o
      saldo é o que está lá hoje, não o que estava no fim do mês passado.

    Produto sem classificação entra numa linha própria ("Sem categoria"), em vez
    de sumir da soma — o total do relatório tem de bater com o total da empresa.
    """
    from ..models import CategoriaProduto, MarcaProduto, Nota, NotaItem, Produto

    inicio, fim = _periodo(de, ate)
    por_marca = agrupar_por == "marca"
    classificacao = MarcaProduto if por_marca else CategoriaProduto
    campo = Produto.marca_id if por_marca else Produto.categoria_id
    sem = "Sem marca definida" if por_marca else "Sem categoria"

    nomes = {r.id: r.nome for r in db.query(classificacao)
             .filter(classificacao.empresa_id == empresa_id).all()}
    produtos = {p.id: p for p in db.query(Produto)
                .filter(Produto.empresa_id == empresa_id).all()}

    grupos = defaultdict(lambda: {"vendido": 0.0, "quantidade_vendida": 0.0,
                                  "estoque": 0.0, "quantidade_estoque": 0.0,
                                  "produtos": 0})

    # ---- o que saiu no período (notas de saída autorizadas) ----
    itens = (
        db.query(NotaItem, Nota)
        .join(Nota, NotaItem.nota_id == Nota.id)
        .filter(Nota.empresa_id == empresa_id,
                Nota.situacao == "AUTORIZADA",
                Nota.tipo_operacao == "1",
                Nota.data_emissao >= datetime.combine(inicio, time.min),
                Nota.data_emissao <= datetime.combine(fim, time.max))
        .all()
    )
    for item, _nota in itens:
        produto = produtos.get(item.produto_id) if item.produto_id else None
        chave = getattr(produto, "marca_id" if por_marca else "categoria_id", None) if produto else None
        alvo = grupos[chave]
        alvo["vendido"] += float(item.valor_total or 0)
        alvo["quantidade_vendida"] += float(item.quantidade or 0)

    # ---- o que está em estoque hoje ----
    for produto in produtos.values():
        if not produto.controla_estoque:
            continue
        chave = getattr(produto, "marca_id" if por_marca else "categoria_id", None)
        alvo = grupos[chave]
        alvo["estoque"] += estoque.valor_em_estoque(produto)
        alvo["quantidade_estoque"] += estoque.saldo(produto)
        alvo["produtos"] += 1

    linhas = []
    for chave, v in grupos.items():
        linhas.append({
            "id": chave,
            "nome": nomes.get(chave, sem),
            "vendido": dinheiro(v["vendido"]),
            "quantidade_vendida": round(v["quantidade_vendida"], 4),
            "estoque": dinheiro(v["estoque"]),
            "quantidade_estoque": round(v["quantidade_estoque"], 4),
            "produtos": v["produtos"],
        })
    linhas.sort(key=lambda l: (-l["vendido"], l["nome"]))

    total_vendido = dinheiro(sum(l["vendido"] for l in linhas))
    for linha in linhas:
        linha["percentual"] = (round(linha["vendido"] / total_vendido * 100, 2)
                               if total_vendido else 0)
    return {
        "periodo": {"de": inicio.isoformat(), "ate": fim.isoformat()},
        "agrupar_por": "marca" if por_marca else "categoria",
        "linhas": linhas,
        "totais": {
            "vendido": total_vendido,
            "estoque": dinheiro(sum(l["estoque"] for l in linhas)),
            "produtos": sum(l["produtos"] for l in linhas),
        },
    }


# --------------------------------------------------------------------------- #
# Razão contábil
# --------------------------------------------------------------------------- #
@router.get("/razao")
def razao(
    empresa_id: int,
    conta_contabil_id: int,
    de: str | None = None,
    ate: str | None = None,
    db: Session = Depends(get_db),
):
    inicio, fim = _periodo(de, ate)
    conta = db.get(ContaContabil, conta_contabil_id)
    if not conta or conta.empresa_id != empresa_id:
        raise HTTPException(404, "Conta contábil não encontrada")

    anteriores = (
        db.query(Partida)
        .filter(
            Partida.empresa_id == empresa_id,
            Partida.data < inicio,
            (Partida.conta_debito_id == conta.id) | (Partida.conta_credito_id == conta.id),
        )
        .all()
    )
    saldo = 0.0
    for p in anteriores:
        saldo += dinheiro(p.valor) if p.conta_debito_id == conta.id else -dinheiro(p.valor)
    if conta.natureza == "C":
        saldo_anterior = round(-saldo, 2)
    else:
        saldo_anterior = round(saldo, 2)

    partidas = (
        db.query(Partida)
        .options(joinedload(Partida.conta_debito), joinedload(Partida.conta_credito))
        .filter(
            Partida.empresa_id == empresa_id,
            Partida.data.between(inicio, fim),
            (Partida.conta_debito_id == conta.id) | (Partida.conta_credito_id == conta.id),
        )
        .order_by(Partida.data, Partida.id)
        .all()
    )

    linhas, acumulado, debitos, creditos = [], saldo_anterior, 0.0, 0.0
    for p in partidas:
        valor = dinheiro(p.valor)
        eh_debito = p.conta_debito_id == conta.id
        contrapartida = p.conta_credito if eh_debito else p.conta_debito
        efeito = valor if eh_debito else -valor
        if conta.natureza == "C":
            efeito = -efeito
        acumulado = round(acumulado + efeito, 2)
        debitos += valor if eh_debito else 0
        creditos += 0 if eh_debito else valor
        linhas.append(
            {
                "data": p.data.isoformat(),
                "historico": p.historico,
                "contrapartida": f"{contrapartida.codigo} - {contrapartida.nome}"
                if contrapartida
                else "-",
                "debito": valor if eh_debito else 0,
                "credito": 0 if eh_debito else valor,
                "saldo": acumulado,
                "origem": p.origem,
            }
        )

    return {
        "conta": {"id": conta.id, "codigo": conta.codigo, "nome": conta.nome,
                  "natureza": conta.natureza, "tipo": conta.tipo},
        "periodo": {"de": inicio.isoformat(), "ate": fim.isoformat()},
        "saldo_anterior": saldo_anterior,
        "linhas": linhas,
        "totais": {
            "debitos": round(debitos, 2),
            "creditos": round(creditos, 2),
            "saldo_final": acumulado,
        },
    }


# --------------------------------------------------------------------------- #
# Balancete de verificação
# --------------------------------------------------------------------------- #
@router.get("/balancete")
def balancete(
    empresa_id: int,
    de: str | None = None,
    ate: str | None = None,
    incluir_sinteticas: bool = True,
    ocultar_zerados: bool = True,
    db: Session = Depends(get_db),
):
    inicio, fim = _periodo(de, ate)
    contas = (
        db.query(ContaContabil)
        .filter(ContaContabil.empresa_id == empresa_id)
        .order_by(ContaContabil.codigo)
        .all()
    )
    if not contas:
        raise HTTPException(400, "Empresa sem plano de contas cadastrado")

    ant_d = defaultdict(float)
    ant_c = defaultdict(float)
    per_d = defaultdict(float)
    per_c = defaultdict(float)

    for p in db.query(Partida).filter(Partida.empresa_id == empresa_id, Partida.data <= fim).all():
        valor = dinheiro(p.valor)
        if p.data < inicio:
            ant_d[p.conta_debito_id] += valor
            ant_c[p.conta_credito_id] += valor
        else:
            per_d[p.conta_debito_id] += valor
            per_c[p.conta_credito_id] += valor

    # Rateio das analíticas para as sintéticas (soma pelos códigos)
    por_codigo = {c.codigo: c for c in contas}

    def acumular(mapa: dict) -> dict:
        total = defaultdict(float)
        for conta in contas:
            if not conta.analitica:
                continue
            valor = mapa.get(conta.id, 0.0)
            if not valor:
                continue
            partes = conta.codigo.split(".")
            for i in range(1, len(partes) + 1):
                codigo = ".".join(partes[:i])
                alvo = por_codigo.get(codigo)
                if alvo:
                    total[alvo.id] += valor
        return total

    tot_ant_d, tot_ant_c = acumular(ant_d), acumular(ant_c)
    tot_per_d, tot_per_c = acumular(per_d), acumular(per_c)

    linhas = []
    for conta in contas:
        if not incluir_sinteticas and not conta.analitica:
            continue
        if conta.analitica:
            a_d, a_c = ant_d.get(conta.id, 0), ant_c.get(conta.id, 0)
            p_d, p_c = per_d.get(conta.id, 0), per_c.get(conta.id, 0)
        else:
            a_d, a_c = tot_ant_d.get(conta.id, 0), tot_ant_c.get(conta.id, 0)
            p_d, p_c = tot_per_d.get(conta.id, 0), tot_per_c.get(conta.id, 0)

        saldo_ant = a_d - a_c
        saldo_fim = saldo_ant + p_d - p_c
        if ocultar_zerados and not any(round(v, 2) for v in (saldo_ant, p_d, p_c, saldo_fim)):
            continue
        linhas.append(
            {
                "conta_id": conta.id,
                "codigo": conta.codigo,
                "nome": conta.nome,
                "tipo": conta.tipo,
                "natureza": conta.natureza,
                "analitica": conta.analitica,
                "nivel": conta.nivel,
                "saldo_anterior": round(abs(saldo_ant), 2),
                "saldo_anterior_dc": "D" if saldo_ant >= 0 else "C",
                "debitos": round(p_d, 2),
                "creditos": round(p_c, 2),
                "saldo_final": round(abs(saldo_fim), 2),
                "saldo_final_dc": "D" if saldo_fim >= 0 else "C",
            }
        )

    total_debitos = round(sum(per_d.values()), 2)
    total_creditos = round(sum(per_c.values()), 2)
    return {
        "periodo": {"de": inicio.isoformat(), "ate": fim.isoformat()},
        "linhas": linhas,
        "totais": {
            "debitos": total_debitos,
            "creditos": total_creditos,
            "diferenca": round(total_debitos - total_creditos, 2),
            "fecha": abs(total_debitos - total_creditos) < 0.01,
        },
    }


# --------------------------------------------------------------------------- #
# DRE
# --------------------------------------------------------------------------- #
@router.get("/dre")
def dre(
    empresa_id: int,
    de: str | None = None,
    ate: str | None = None,
    regime: str = "competencia",     # competencia | caixa
    centro_custo_id: int | None = None,
    comparar_anterior: bool = False,
    db: Session = Depends(get_db),
):
    inicio, fim = _periodo(de, ate)

    def apurar(ini: date, fi: date) -> dict:
        coluna = Partida.competencia if regime == "competencia" else Partida.data
        query = (
            db.query(Partida)
            .options(joinedload(Partida.conta_debito), joinedload(Partida.conta_credito))
            .filter(Partida.empresa_id == empresa_id, coluna.between(ini, fi))
        )
        if centro_custo_id:
            query = query.filter(Partida.centro_custo_id == centro_custo_id)
        # efeito no resultado: receitas positivas, custos/despesas negativos
        saldos = defaultdict(float)
        for partida in query.all():
            for conta, valor in _classificar(partida):
                if not conta.grupo_dre:
                    continue
                saldos[(conta.grupo_dre, conta.id, conta.codigo, conta.nome)] += valor
        return saldos

    saldos = apurar(inicio, fim)
    dias = (fim - inicio).days + 1
    saldos_ant = (
        apurar(inicio - timedelta(days=dias), inicio - timedelta(days=1))
        if comparar_anterior
        else {}
    )

    por_grupo = defaultdict(float)
    por_grupo_ant = defaultdict(float)
    contas_grupo = defaultdict(list)
    for (grupo, cid, codigo, nome), valor in saldos.items():
        valor = round(valor, 2)
        por_grupo[grupo] += valor
        if valor:
            contas_grupo[grupo].append(
                {"conta_id": cid, "codigo": codigo, "nome": nome, "valor": valor}
            )
    for (grupo, _cid, _c, _n), valor in saldos_ant.items():
        por_grupo_ant[grupo] += round(valor, 2)

    receita_bruta = round(por_grupo.get("RECEITA_BRUTA", 0), 2)

    def pct(valor: float) -> float:
        return round(abs(valor) / receita_bruta * 100, 2) if receita_bruta else 0

    linhas = []
    ja_emitidos = set()
    for indice, (chave, rotulo, _sinal) in enumerate(GRUPOS_DRE):
        valor = round(por_grupo.get(chave, 0), 2)
        if valor or por_grupo_ant.get(chave):
            linhas.append(
                {
                    "tipo": "grupo",
                    "chave": chave,
                    "descricao": rotulo,
                    "valor": valor,
                    "valor_anterior": round(por_grupo_ant.get(chave, 0), 2),
                    "percentual": pct(valor),
                    "contas": sorted(contas_grupo.get(chave, []), key=lambda c: c["codigo"]),
                }
            )
        # subtotais são emitidos assim que o último grupo que os compõe é ultrapassado
        for rotulo_sub, grupos in SUBTOTAIS:
            if rotulo_sub in ja_emitidos:
                continue
            ultimo = max(
                (i for i, (g, _, _) in enumerate(GRUPOS_DRE) if g in grupos), default=-1
            )
            if indice >= ultimo:
                total = round(sum(por_grupo.get(g, 0) for g in grupos), 2)
                total_ant = round(sum(por_grupo_ant.get(g, 0) for g in grupos), 2)
                linhas.append(
                    {
                        "tipo": "subtotal",
                        "chave": rotulo_sub,
                        "descricao": rotulo_sub,
                        "valor": total,
                        "valor_anterior": total_ant,
                        "percentual": pct(total),
                        "contas": [],
                    }
                )
                ja_emitidos.add(rotulo_sub)

    resultado = round(sum(por_grupo.get(g, 0) for g, _, _ in GRUPOS_DRE), 2)
    return {
        "periodo": {"de": inicio.isoformat(), "ate": fim.isoformat(), "regime": regime},
        "linhas": linhas,
        "receita_bruta": receita_bruta,
        "resultado_liquido": resultado,
        "margem": round(resultado / receita_bruta * 100, 2) if receita_bruta else 0,
    }


# --------------------------------------------------------------------------- #
# Contratos de assessoria × financeiro
#
# Mostra em que pé está cada contrato: quanto de comissão foi combinado, quanto
# virou conta a receber, quanto já entrou no caixa, quanto falta e o que venceu.
# --------------------------------------------------------------------------- #
@router.get("/contratos")
def relatorio_contratos(
    empresa_id: int,
    de: str | None = None,
    ate: str | None = None,
    status: str | None = None,
    parceiro_id: int | None = None,
    representante_id: int | None = None,
    agrupar_por: str = "status",      # status | parceiro | representante | produto | mes
    db: Session = Depends(get_db),
):
    from .contratos import STATUS_CONTRATO, contrato_dict

    inicio, fim = _periodo(de, ate)
    query = (
        db.query(Contrato)
        .options(joinedload(Contrato.comprador), joinedload(Contrato.vendedor))
        .filter(
            Contrato.empresa_id == empresa_id,
            Contrato.data >= inicio,
            Contrato.data <= fim,
        )
    )
    if parceiro_id:
        query = query.filter(
            (Contrato.comprador_id == parceiro_id) | (Contrato.vendedor_id == parceiro_id)
        )
    if representante_id:
        query = query.filter(Contrato.representante_id == representante_id)

    contratos = query.order_by(Contrato.data, Contrato.numero).all()
    linhas = [contrato_dict(db, c) for c in contratos]
    db.commit()   # o contrato_dict recalcula o status; grava de uma vez
    if status:
        linhas = [l for l in linhas if l["status"] == status]

    meses = ["jan", "fev", "mar", "abr", "mai", "jun",
             "jul", "ago", "set", "out", "nov", "dez"]

    def chave(l: dict) -> tuple[str, str]:
        if agrupar_por == "parceiro":
            return (l["comprador_nome"], l["comprador_nome"])
        if agrupar_por == "representante":
            nome = l.get("representante_nome") or "Sem representante"
            return (nome, nome)
        if agrupar_por == "produto":
            nome = l.get("produto_nome") or l.get("produto") or "Sem produto"
            return (nome, nome)
        if agrupar_por == "mes":
            d = l["data"][:7]
            return (d, f"{meses[int(d[5:7]) - 1]}/{d[:4]}")
        return (l["status"], l["status_nome"])

    campos = ("valor_total", "comissao_total", "comissao_recebida",
              "comissao_a_receber", "comissao_vencida")
    grupos: dict[str, dict] = {}
    for l in linhas:
        codigo, nome = chave(l)
        g = grupos.setdefault(
            codigo, dict({"codigo": codigo, "nome": nome, "quantidade": 0},
                         **{c: 0.0 for c in campos})
        )
        g["quantidade"] += 1
        for c in campos:
            g[c] += l[c]

    # na visão por status a ordem é a do ciclo do contrato, não alfabética
    ordem = list(STATUS_CONTRATO)
    resumo = sorted(
        ({**g, **{c: round(g[c], 2) for c in campos}} for g in grupos.values()),
        key=lambda g: (ordem.index(g["codigo"]) if g["codigo"] in ordem else 0)
        if agrupar_por == "status" else g["nome"],
    )

    totais = {c: round(sum(l[c] for l in linhas), 2) for c in campos}
    totais["quantidade"] = len(linhas)
    totais["peso_total"] = round(sum(l.get("peso_total") or 0 for l in linhas), 3)
    totais["recebido_percentual"] = round(
        totais["comissao_recebida"] / totais["comissao_total"] * 100, 2
    ) if totais["comissao_total"] else 0.0
    totais["em_atraso"] = sum(1 for l in linhas if l["comissao_vencida"] > 0)

    return {
        "periodo": {"de": inicio.isoformat(), "ate": fim.isoformat()},
        "agrupar_por": agrupar_por,
        "linhas": linhas,
        "resumo": resumo,
        "totais": totais,
        "status": [{"codigo": c, "nome": n} for c, n in STATUS_CONTRATO.items()],
    }


# --------------------------------------------------------------------------- #
# Painel
# --------------------------------------------------------------------------- #
@router.get("/dashboard")
def dashboard(empresa_id: int, db: Session = Depends(get_db)):
    hoje = date.today()
    inicio_mes = date(hoje.year, hoje.month, 1)
    fim_mes = (date(hoje.year + (hoje.month == 12), (hoje.month % 12) + 1, 1)) - timedelta(days=1)

    bancos = db.query(Banco).filter(Banco.empresa_id == empresa_id, Banco.ativo.is_(True)).all()
    saldo_total = sum(dinheiro(b.saldo_inicial) for b in bancos)
    ids = [b.id for b in bancos]
    if ids:
        for m in db.query(MovimentoCaixa).filter(
            MovimentoCaixa.banco_id.in_(ids), MovimentoCaixa.data <= hoje
        ):
            saldo_total += dinheiro(m.valor) if m.tipo == "E" else -dinheiro(m.valor)

    parcelas = (
        db.query(Parcela)
        .join(Lancamento)
        .filter(
            Lancamento.empresa_id == empresa_id, Parcela.status.in_(("ABERTO", "PARCIAL"))
        )
        .all()
    )
    resumo = {
        "receber_vencido": 0.0, "receber_hoje": 0.0, "receber_mes": 0.0, "receber_total": 0.0,
        "pagar_vencido": 0.0, "pagar_hoje": 0.0, "pagar_mes": 0.0, "pagar_total": 0.0,
    }
    for p in parcelas:
        pre = "receber" if p.lancamento.tipo == "RECEBER" else "pagar"
        resumo[f"{pre}_total"] += p.saldo
        if p.data_vencimento < hoje:
            resumo[f"{pre}_vencido"] += p.saldo
        elif p.data_vencimento == hoje:
            resumo[f"{pre}_hoje"] += p.saldo
        if inicio_mes <= p.data_vencimento <= fim_mes:
            resumo[f"{pre}_mes"] += p.saldo
    resumo = {k: round(v, 2) for k, v in resumo.items()}

    movimentos_mes = (
        db.query(MovimentoCaixa)
        .filter(
            MovimentoCaixa.empresa_id == empresa_id,
            MovimentoCaixa.data.between(inicio_mes, fim_mes),
        )
        .all()
    )
    entradas = round(sum(dinheiro(m.valor) for m in movimentos_mes if m.tipo == "E"), 2)
    saidas = round(sum(dinheiro(m.valor) for m in movimentos_mes if m.tipo == "S"), 2)

    resultado_mes = dre(
        empresa_id, inicio_mes.isoformat(), fim_mes.isoformat(), "competencia", None, False, db
    )

    # Evolução dos últimos 6 meses (caixa realizado)
    evolucao = []
    ref = date(hoje.year, hoje.month, 1)
    for i in range(5, -1, -1):
        ano = ref.year + (ref.month - 1 - i) // 12
        mes = (ref.month - 1 - i) % 12 + 1
        ini = date(ano, mes, 1)
        fi = date(ano + (mes == 12), (mes % 12) + 1, 1) - timedelta(days=1)
        movs = [m for m in db.query(MovimentoCaixa).filter(
            MovimentoCaixa.empresa_id == empresa_id, MovimentoCaixa.data.between(ini, fi)
        ).all()]
        evolucao.append(
            {
                "periodo": ini.strftime("%m/%Y"),
                "entradas": round(sum(dinheiro(m.valor) for m in movs if m.tipo == "E"), 2),
                "saidas": round(sum(dinheiro(m.valor) for m in movs if m.tipo == "S"), 2),
            }
        )

    return {
        "data": hoje.isoformat(),
        "saldo_disponivel": round(saldo_total, 2),
        "contas": [
            {"nome": b.nome, "tipo": b.tipo, "saldo": round(
                dinheiro(b.saldo_inicial)
                + sum(
                    dinheiro(m.valor) if m.tipo == "E" else -dinheiro(m.valor)
                    for m in db.query(MovimentoCaixa).filter(
                        MovimentoCaixa.banco_id == b.id, MovimentoCaixa.data <= hoje
                    )
                ),
                2,
            )}
            for b in bancos
        ],
        "titulos": resumo,
        "mes": {
            "entradas": entradas,
            "saidas": saidas,
            "resultado_caixa": round(entradas - saidas, 2),
            "receita_competencia": resultado_mes["receita_bruta"],
            "resultado_competencia": resultado_mes["resultado_liquido"],
        },
        "evolucao": evolucao,
    }
