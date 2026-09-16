"""Teste do ciclo de vida do contrato e do relatório de contratos × financeiro.

Percorre a vida inteira de um contrato de assessoria:
  Aberto → Fechado a Receber → Fechado Recebido Parcial → Fechado Recebido Total,
conferindo que o status muda sozinho conforme as baixas entram no caixa, e que o
relatório de contratos reflete comissão, recebido, a receber e vencido.
Testa ainda o cancelamento, a reabertura e o estorno (que volta para Aberto).

Uso:  python testes/teste_status_contrato.py   (com o servidor no ar)
"""
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = "http://127.0.0.1:8000"
falhas = []


def api(metodo, caminho, dados=None, token=None, esperar_erro=False):
    req = urllib.request.Request(
        f"{BASE}{caminho}",
        data=json.dumps(dados).encode() if dados is not None else None,
        method=metodo,
    )
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        corpo = json.loads(e.read() or b"{}")
        if esperar_erro:
            return {"_status": e.code, "_detalhe": corpo.get("detail", "")}
        raise AssertionError(f"{metodo} {caminho} -> HTTP {e.code}: {corpo}") from None


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        falhas.append(descricao)


def brl(v):
    return f"R$ {v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


sufixo = str(int(time.time()))
hoje = date.today()

print("\n=== 1. Preparação ===")
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Corretor Status", "email": f"status{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria Status",
})
t = conta["token"]
eid = conta["empresa"]["id"]
comprador = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "COMPRADOR STATUS LTDA"}, t)
vendedor = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "VENDEDOR STATUS LTDA"}, t)
banco = api("POST", "/api/bancos", {
    "empresa_id": eid, "nome": "Caixa da assessoria", "tipo": "CAIXA",
    "saldo_inicial": 0}, t)
produtos = api("GET", f"/api/produtos?empresa_id={eid}", token=t)
unidades = api("GET", f"/api/unidades?empresa_id={eid}", token=t)
saca = next(u for u in unidades if u["codigo"] == "SC")

base = {
    "empresa_id": eid, "data": hoje.isoformat(),
    "comprador_id": comprador["id"], "vendedor_id": vendedor["id"],
    "produto_id": produtos[0]["id"], "unidade_id": saca["id"],
    "quantidade": 330, "preco_unitario": 1320,
    "comissao_comprador_percentual": 0.5, "comissao_vendedor_percentual": 0.5,
    "data_pagamento": hoje.isoformat(),
}
contrato = api("POST", "/api/contratos", dict(base), t)
checar("contrato nasce Aberto", contrato["status"] == "ABERTO", contrato["status"])
checar("nome do status em português", contrato["status_nome"] == "Aberto",
       contrato["status_nome"])
checar("comissão total de R$ 4.356,00", abs(contrato["comissao_total"] - 4356) < 0.01)
checar("nada gerado ainda", contrato["financeiro"]["gerado"] == 0)
checar("tudo a receber", abs(contrato["comissao_a_receber"] - 4356) < 0.01,
       brl(contrato["comissao_a_receber"]))

print("\n=== 2. Gerou os recebíveis → Fechado a Receber ===")
r = api("POST", f"/api/contratos/{contrato['id']}/gerar-recebiveis", {
    "vencimento": hoje.isoformat(), "num_parcelas": 1,
    "gerar_comprador": True, "gerar_vendedor": True,
}, t)
c = r["contrato"]
checar("status vira Fechado a Receber", c["status"] == "FECHADO_A_RECEBER", c["status"])
checar("rótulo do status", c["status_nome"] == "Fechado a Receber", c["status_nome"])
checar("comissão inteira virou título", abs(c["financeiro"]["gerado"] - 4356) < 0.01,
       brl(c["financeiro"]["gerado"]))
checar("nada recebido ainda", c["financeiro"]["recebido"] == 0)
checar("duas parcelas (uma de cada lado)", c["financeiro"]["parcelas"] == 2,
       str(c["financeiro"]["parcelas"]))

print("\n=== 3. Baixa de um lado → Fechado Recebido Parcial ===")
abertas = api("GET", f"/api/parcelas?empresa_id={eid}&tipo=RECEBER&situacao=TODAS", token=t)
parcelas = abertas["linhas"] if isinstance(abertas, dict) else abertas
checar("duas parcelas na lista de contas a receber", len(parcelas) == 2, str(len(parcelas)))

api("POST", f"/api/parcelas/{parcelas[0]['id']}/baixar", {
    "banco_id": banco["id"], "data": hoje.isoformat(), "valor": parcelas[0]["valor"],
}, t)
c = api("GET", f"/api/contratos/{contrato['id']}", token=t)
checar("status vira Fechado Recebido Parcial", c["status"] == "RECEBIDO_PARCIAL", c["status"])
checar("rótulo do status", c["status_nome"] == "Fechado Recebido Parcial", c["status_nome"])
checar("metade recebida", abs(c["financeiro"]["recebido"] - 2178) < 0.01,
       brl(c["financeiro"]["recebido"]))
checar("metade em aberto", abs(c["financeiro"]["saldo"] - 2178) < 0.01,
       brl(c["financeiro"]["saldo"]))
checar("percentual recebido de 50%", abs(c["financeiro"]["recebido_percentual"] - 50) < 0.1,
       f"{c['financeiro']['recebido_percentual']}%")

print("\n=== 4. Baixa parcial da segunda parcela continua Parcial ===")
api("POST", f"/api/parcelas/{parcelas[1]['id']}/baixar", {
    "banco_id": banco["id"], "data": hoje.isoformat(), "valor": 1000,
}, t)
c = api("GET", f"/api/contratos/{contrato['id']}", token=t)
checar("ainda Recebido Parcial", c["status"] == "RECEBIDO_PARCIAL", c["status"])
checar("recebido acumulado", abs(c["financeiro"]["recebido"] - 3178) < 0.01,
       brl(c["financeiro"]["recebido"]))
checar("falta o resto", abs(c["financeiro"]["saldo"] - 1178) < 0.01,
       brl(c["financeiro"]["saldo"]))

print("\n=== 5. Quitou tudo → Fechado Recebido Total ===")
api("POST", f"/api/parcelas/{parcelas[1]['id']}/baixar", {
    "banco_id": banco["id"], "data": hoje.isoformat(), "valor": 1178,
}, t)
c = api("GET", f"/api/contratos/{contrato['id']}", token=t)
checar("status vira Fechado Recebido Total", c["status"] == "RECEBIDO_TOTAL", c["status"])
checar("rótulo do status", c["status_nome"] == "Fechado Recebido Total", c["status_nome"])
checar("comissão inteira recebida", abs(c["financeiro"]["recebido"] - 4356) < 0.01,
       brl(c["financeiro"]["recebido"]))
checar("saldo zerado", c["financeiro"]["saldo"] == 0)
checar("nada a receber", c["comissao_a_receber"] == 0)
checar("as duas parcelas pagas", c["financeiro"]["parcelas_pagas"] == 2)

print("\n=== 6. Contrato vencido aparece em atraso ===")
vencido = api("POST", "/api/contratos", dict(
    base, numero="", data_pagamento=(hoje - timedelta(days=20)).isoformat()), t)
api("POST", f"/api/contratos/{vencido['id']}/gerar-recebiveis", {
    "vencimento": (hoje - timedelta(days=20)).isoformat(), "num_parcelas": 1,
    "gerar_comprador": True, "gerar_vendedor": False,
}, t)
v = api("GET", f"/api/contratos/{vencido['id']}", token=t)
checar("comissão vencida destacada", abs(v["comissao_vencida"] - 2178) < 0.01,
       brl(v["comissao_vencida"]))
checar("dias de atraso contados", v["financeiro"]["dias_atraso"] == 20,
       str(v["financeiro"]["dias_atraso"]))
checar("sobra comissão do vendedor sem título",
       abs(v["financeiro"]["a_gerar"] - 2178) < 0.01, brl(v["financeiro"]["a_gerar"]))

print("\n=== 7. Cancelamento e reabertura ===")
cancelado = api("POST", "/api/contratos", dict(base, numero=""), t)
cancelado = api("POST", f"/api/contratos/{cancelado['id']}/cancelar", None, t)
checar("contrato cancelado", cancelado["status"] == "CANCELADO", cancelado["status"])
bloqueado = api("POST", f"/api/contratos/{cancelado['id']}/gerar-recebiveis", {}, t,
                esperar_erro=True)
checar("cancelado não gera recebíveis", bloqueado.get("_status") == 400,
       str(bloqueado.get("_detalhe", ""))[:45])
reaberto = api("POST", f"/api/contratos/{cancelado['id']}/reabrir", None, t)
checar("contrato reaberto volta para Aberto", reaberto["status"] == "ABERTO",
       reaberto["status"])

print("\n=== 8. Estorno devolve o contrato para Aberto ===")
estorno = api("POST", "/api/contratos", dict(base, numero=""), t)
api("POST", f"/api/contratos/{estorno['id']}/gerar-recebiveis", {
    "vencimento": hoje.isoformat(), "gerar_comprador": True, "gerar_vendedor": True}, t)
meio = api("GET", f"/api/contratos/{estorno['id']}", token=t)
checar("antes do estorno estava Fechado a Receber",
       meio["status"] == "FECHADO_A_RECEBER", meio["status"])
depois = api("POST", f"/api/contratos/{estorno['id']}/estornar-recebiveis", None, t)
checar("depois do estorno volta para Aberto",
       depois["contrato"]["status"] == "ABERTO", depois["contrato"]["status"])
checar("volta a não ter nada gerado", depois["contrato"]["financeiro"]["gerado"] == 0)

print("\n=== 9. Lista de contratos com contagem por situação ===")
lista = api("GET", f"/api/contratos?empresa_id={eid}", token=t)
por_status = lista["totais"]["por_status"]
checar("um contrato Recebido Total", por_status["RECEBIDO_TOTAL"] == 1, str(por_status))
checar("um contrato Fechado a Receber", por_status["FECHADO_A_RECEBER"] == 1, str(por_status))
checar("dois contratos Abertos", por_status["ABERTO"] == 2, str(por_status))
checar("nenhum cancelado (foi reaberto)", por_status["CANCELADO"] == 0, str(por_status))
checar("lista devolve as situações disponíveis", len(lista["status"]) == 5)
checar("total recebido na lista", abs(lista["totais"]["comissao_recebida"] - 4356) < 0.01,
       brl(lista["totais"]["comissao_recebida"]))

filtrada = api("GET", f"/api/contratos?empresa_id={eid}&status=RECEBIDO_TOTAL", token=t)
checar("filtro por situação funciona", filtrada["totais"]["quantidade"] == 1
       and filtrada["linhas"][0]["status"] == "RECEBIDO_TOTAL")

print("\n=== 10. Relatório de contratos × financeiro ===")
primeiro = (hoje.replace(day=1)).isoformat()
rel = api("GET", f"/api/relatorios/contratos?empresa_id={eid}&de={primeiro}"
                 f"&ate={hoje.isoformat()}", token=t)
tot = rel["totais"]
checar("relatório traz os 4 contratos", tot["quantidade"] == 4, str(tot["quantidade"]))
checar("comissão somada", abs(tot["comissao_total"] - 4 * 4356) < 0.01,
       brl(tot["comissao_total"]))
checar("recebido somado", abs(tot["comissao_recebida"] - 4356) < 0.01,
       brl(tot["comissao_recebida"]))
checar("vencido somado", abs(tot["comissao_vencida"] - 2178) < 0.01,
       brl(tot["comissao_vencida"]))
checar("um contrato em atraso", tot["em_atraso"] == 1, str(tot["em_atraso"]))
checar("percentual recebido calculado", abs(tot["recebido_percentual"] - 25) < 0.1,
       f"{tot['recebido_percentual']}%")
checar("peso total somado (4 x 19.800 kg)", abs(tot["peso_total"] - 79200) < 0.01,
       f"{tot['peso_total']} kg")

resumo = {g["codigo"]: g for g in rel["resumo"]}
checar("resumo agrupado por situação", "RECEBIDO_TOTAL" in resumo and "ABERTO" in resumo,
       ", ".join(resumo))
checar("grupo Aberto com 2 contratos", resumo["ABERTO"]["quantidade"] == 2)
checar("resumo na ordem do ciclo do contrato",
       [g["codigo"] for g in rel["resumo"]][0] == "ABERTO",
       " > ".join(g["codigo"] for g in rel["resumo"]))

por_rep = api("GET", f"/api/relatorios/contratos?empresa_id={eid}&de={primeiro}"
                     f"&ate={hoje.isoformat()}&agrupar_por=representante", token=t)
checar("dá para agrupar por representante", len(por_rep["resumo"]) >= 1,
       por_rep["resumo"][0]["nome"] if por_rep["resumo"] else "")

so_total = api("GET", f"/api/relatorios/contratos?empresa_id={eid}&de={primeiro}"
                      f"&ate={hoje.isoformat()}&status=RECEBIDO_TOTAL", token=t)
checar("filtro de situação no relatório", so_total["totais"]["quantidade"] == 1,
       str(so_total["totais"]["quantidade"]))

outro = api("POST", "/api/publico/cadastro", {
    "nome": "Intruso", "email": f"intruso{sufixo}@teste.com", "senha": "123456",
    "empresa": "Outra"})
alheio = api("GET", f"/api/relatorios/contratos?empresa_id={eid}&de={primeiro}"
                    f"&ate={hoje.isoformat()}", token=outro["token"], esperar_erro=True)
checar("outro assinante não vê o relatório", alheio.get("_status") == 403,
       str(alheio.get("_detalhe", ""))[:40])

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("Status dos contratos e relatório financeiro OK.")
