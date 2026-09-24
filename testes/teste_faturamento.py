"""Teste da tela Notas Fiscais: faturar e desfaturar.

Confere:
  * lista, filtros (faturadas / a faturar, entrada / saída) e os totais;
  * ficha completa: itens, cliente/fornecedor, pagamentos e o título gerado;
  * faturar uma nota de entrada -> conta a PAGAR com uma parcela por duplicata;
  * não fatura duas vezes; não fatura nota cancelada;
  * desfaturar apaga o título, estorna a contabilidade e libera a nota;
  * título com baixa não deixa desfaturar;
  * trocar o cliente/fornecedor só enquanto não está faturada;
  * faturamento em lote, com o que falhou listado à parte;
  * outra conta não enxerga nada.

Uso (com o servidor em http://127.0.0.1:8000):  python testes/teste_faturamento.py
"""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "testes" / "dados_dfe"
BASE = os.getenv("FIN_BASE", "http://127.0.0.1:8000")
falhas = []


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        falhas.append(descricao)


def baixar(caminho, token=None) -> str:
    """Pega um arquivo (não é JSON): o XML da nota, por exemplo."""
    req = urllib.request.Request(f"{BASE}{caminho}")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as r:
        return r.read().decode("utf-8", "replace")


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
        corpo = e.read()
        if esperar_erro:
            try:
                return {"_status": e.code, "_detalhe": json.loads(corpo or b"{}").get("detail", "")}
            except json.JSONDecodeError:
                return {"_status": e.code, "_detalhe": corpo.decode("utf-8", "replace")[:200]}
        raise AssertionError(f"{metodo} {caminho} -> HTTP {e.code}: {corpo[:300]}") from None


def enviar_xml(empresa_id, nome, conteudo, token):
    limite = "----agrodock" + str(int(time.time() * 1000))
    partes = [
        f'--{limite}\r\nContent-Disposition: form-data; name="empresa_id"\r\n\r\n{empresa_id}\r\n'
        .encode(),
        f'--{limite}\r\nContent-Disposition: form-data; name="arquivo"; filename="{nome}"\r\n'
        f"Content-Type: application/xml\r\n\r\n".encode() + conteudo + b"\r\n",
        f"--{limite}--\r\n".encode(),
    ]
    req = urllib.request.Request(f"{BASE}/api/dfe/enviar-xml", data=b"".join(partes), method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={limite}")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read() or b"{}")


def nota_de_exemplo(numero, cnpj, nome, valor, dia, chave_extra="0"):
    """Um resumo de nota (resNFe), que é o que a SEFAZ entrega antes da ciência."""
    chave = ("31" + dia[2:4] + dia[5:7] + cnpj + "55" + "001" + numero.zfill(9) + "1"
             + f"8765432{chave_extra}" + "0")
    return chave, f"""<?xml version="1.0" encoding="UTF-8"?>
<resNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
<chNFe>{chave}</chNFe><CNPJ>{cnpj}</CNPJ><xNome>{nome}</xNome><IE>0011223344009</IE>
<dhEmi>{dia}T09:30:00-03:00</dhEmi><tpNF>1</tpNF><vNF>{valor}</vNF>
<digVal>x</digVal><dhRecbto>{dia}T09:31:00-03:00</dhRecbto><nProt>131260099{numero}</nProt>
<cSitNFe>1</cSitNFe></resNFe>""".encode()


sufixo = str(int(time.time()))
CNPJ_EMPRESA = "98765432000198"

print("\n=== 1. Preparação ===")
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Faturamento", "email": f"fatura{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria AgroDock",
})
t, eid = conta["token"], conta["empresa"]["id"]
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "ASSESSORIA AGRODOCK LTDA", "cnpj": CNPJ_EMPRESA,
    "cidade": "Patrocínio", "uf": "MG",
}, t)

nfe = (DADOS / "nfe_completa.xml").read_bytes()
enviar_xml(eid, "completa.xml", nfe, t)
for i, (num, cnpj, nome, valor, dia) in enumerate([
        ("004512", "20770566000100", "COOXUPE COOP DE CAFEICULTORES", "18420.00", "2026-09-16"),
        ("019887", "07028528000894", "OLAM AGRICOLA LTDA", "254300.75", "2026-09-14")]):
    _c, xml = nota_de_exemplo(num, cnpj, nome, valor, dia, str(i + 1))
    enviar_xml(eid, f"{num}.xml", xml, t)

lista = api("GET", f"/api/notas?empresa_id={eid}", None, t)
checar("lista traz as 3 notas com os totais", lista["totais"]["quantidade"] == 3
       and lista["totais"]["a_faturar"] == 3 and lista["totais"]["faturadas"] == 0,
       str(lista["totais"]["valor"]))
completa = next(n for n in lista["linhas"] if not n["resumo"])
somente_resumo = [n for n in lista["linhas"] if n["resumo"]]
checar("a nota do fornecedor é ENTRADA e o título sugerido é a pagar",
       completa["sentido"] == "Entrada" and completa["tipo_titulo_sugerido"] == "PAGAR")
checar("nenhuma nota nasce faturada", all(not n["faturada"] for n in lista["linhas"]))
# é por este campo que a lista decide mostrar o botão de baixar o XML
checar("a lista diz quais notas têm XML para baixar",
       completa["tem_xml"] is True
       and all(n["tem_xml"] is False for n in somente_resumo),
       f"completa {completa['tem_xml']} / resumos "
       f"{[n['tem_xml'] for n in somente_resumo]}")
baixado = baixar(f"/api/dfe/notas/{completa['id']}/xml", t)
checar("e o XML baixa inteiro, com a NF-e dentro",
       baixado.startswith("<?xml") and "<infNFe" in baixado, baixado[:40])

print("\n=== 2. Ficha da nota ===")
ficha = api("GET", f"/api/notas/{completa['id']}", None, t)
checar("ficha mostra os itens do XML antes mesmo de importar",
       ficha["totais_itens"]["quantidade"] == 2
       and ficha["itens"][0]["descricao"].startswith("CAFE CRU"))
checar("ficha soma produtos e ICMS dos itens",
       ficha["totais_itens"]["produtos"] == 437085.0 and ficha["totais_itens"]["icms"] == 52524.0,
       str(ficha["totais_itens"]))
checar("ficha traz as duplicatas da nota",
       sum(1 for p in ficha["pagamentos"] if p["origem"] == "DUPLICATA") == 2)
checar("ainda sem título", ficha["nota"]["titulo"] is None and ficha["nota"]["faturada"] is False)

print("\n=== 3. Faturar ===")
resultado = api("POST", f"/api/notas/{completa['id']}/faturar", {"empresa_id": eid}, t)
checar("faturou e gerou conta a pagar", resultado["ok"] and resultado["lancamento_id"],
       resultado["mensagem"])
depois = api("GET", f"/api/notas/{completa['id']}", None, t)
titulo = depois["nota"]["titulo"]
checar("título a pagar com o valor da nota",
       titulo["tipo"] == "PAGAR" and titulo["valor_total"] == 438200.0, str(titulo["valor_total"]))
checar("uma parcela para cada duplicata, nos vencimentos da nota",
       titulo["num_parcelas"] == 2
       and [p["data_vencimento"] for p in titulo["parcelas"]] == ["2026-10-10", "2026-11-10"],
       str([p["data_vencimento"] for p in titulo["parcelas"]]))
checar("faturar também importou os itens e ligou o fornecedor",
       depois["nota"]["importada"] is True and depois["parceiro"] is not None
       and depois["parceiro"]["nome"].startswith("FAZENDA SAO JOAQUIM"))
checar("a nota guarda quando foi faturada", bool(depois["nota"]["faturada_em"]))

titulo_id = resultado["lancamento_id"]
no_financeiro = api("GET", f"/api/lancamentos/{titulo_id}", None, t)
checar("o título aparece em Contas a Pagar com a chave na observação",
       no_financeiro["tipo"] == "PAGAR" and "Chave" in (no_financeiro["observacao"] or ""))

balancete = api("GET", f"/api/relatorios/balancete?empresa_id={eid}&inicio=2026-01-01&fim=2026-12-31",
                None, t)
checar("a contabilidade fechou depois de faturar", balancete["totais"]["fecha"],
       f"D {balancete['totais']['debitos']} x C {balancete['totais']['creditos']}")

de_novo = api("POST", f"/api/notas/{completa['id']}/faturar", {"empresa_id": eid}, t,
              esperar_erro=True)
checar("não fatura a mesma nota duas vezes", de_novo.get("_status") == 400,
       de_novo.get("_detalhe", "")[:50])
troca = api("PUT", f"/api/notas/{completa['id']}", {"empresa_id": eid, "parceiro_id": None}, t,
            esperar_erro=True)
checar("não troca o cliente/fornecedor de nota faturada", troca.get("_status") == 400)

print("\n=== 4. Filtros por faturamento ===")
faturadas = api("GET", f"/api/notas?empresa_id={eid}&faturamento=faturadas", None, t)
a_faturar = api("GET", f"/api/notas?empresa_id={eid}&faturamento=a-faturar", None, t)
checar("filtro 'já faturadas' traz só uma", len(faturadas["linhas"]) == 1
       and faturadas["linhas"][0]["id"] == completa["id"])
checar("filtro 'a faturar' traz as outras duas", len(a_faturar["linhas"]) == 2)
entradas = api("GET", f"/api/notas?empresa_id={eid}&sentido=entrada", None, t)
checar("filtro de entrada pega as três (todas de terceiros)", len(entradas["linhas"]) == 3)
resumo = api("GET", f"/api/notas/resumo?empresa_id={eid}", None, t)
checar("resumo do topo bate", resumo["faturadas"] == 1 and resumo["a_faturar"] == 2,
       str(resumo))

print("\n=== 5. Desfaturar ===")
bancos = api("GET", f"/api/bancos?empresa_id={eid}", None, t)
if not bancos:
    contas = {c["codigo"]: c for c in api("GET", f"/api/contas-contabeis?empresa_id={eid}", None, t)}
    bancos = [api("POST", "/api/bancos", {
        "empresa_id": eid, "codigo": "001", "nome": "Conta teste", "tipo": "CORRENTE",
        "conta_contabil_id": contas["1.1.01.002"]["id"], "saldo_inicial": 500000,
        "data_saldo_inicial": "2026-01-01"}, t)]
parcelas = api("GET", f"/api/parcelas?empresa_id={eid}&tipo=PAGAR&situacao=ABERTAS", None, t)
primeira = next(p for p in parcelas if p["lancamento_id"] == titulo_id)
api("POST", f"/api/parcelas/{primeira['id']}/baixar", {
    "banco_id": bancos[0]["id"], "data": "2026-10-10", "forma_pagamento": "PIX",
    "historico": "Pagamento parcial da nota"}, t)
com_baixa = api("POST", f"/api/notas/{completa['id']}/desfaturar", None, t, esperar_erro=True)
checar("título com baixa não deixa desfaturar", com_baixa.get("_status") == 400
       and "baixa" in com_baixa.get("_detalhe", "").lower(), com_baixa.get("_detalhe", "")[:70])

detalhe_parcela = api("GET", f"/api/parcelas/{primeira['id']}", None, t)
api("DELETE", f"/api/baixas/{detalhe_parcela['baixas'][0]['id']}", None, t)
desfaturou = api("POST", f"/api/notas/{completa['id']}/desfaturar", None, t)
checar("desfaturou depois do estorno", desfaturou["ok"]
       and desfaturou["nota"]["faturada"] is False, desfaturou["mensagem"])
checar("a mensagem deixa claro que a SEFAZ não foi tocada",
       "SEFAZ" in desfaturou["mensagem"])
sumiu = api("GET", f"/api/lancamentos/{titulo_id}", None, t, esperar_erro=True)
checar("o título foi apagado do financeiro", sumiu.get("_status") == 404)
balancete2 = api("GET", f"/api/relatorios/balancete?empresa_id={eid}&inicio=2026-01-01&fim=2026-12-31",
                 None, t)
checar("a contabilidade continua fechando depois de desfaturar", balancete2["totais"]["fecha"],
       f"D {balancete2['totais']['debitos']} x C {balancete2['totais']['creditos']}")
checar("os itens da nota continuam lá",
       api("GET", f"/api/notas/{completa['id']}", None, t)["totais_itens"]["quantidade"] == 2)
outra_vez = api("POST", f"/api/notas/{completa['id']}/desfaturar", None, t, esperar_erro=True)
checar("desfaturar de novo avisa que não está faturada", outra_vez.get("_status") == 400)

print("\n=== 6. Faturar em lote ===")
refaturou = api("POST", f"/api/notas/{completa['id']}/faturar",
                {"empresa_id": eid, "vencimento": "2026-12-05"}, t)
checar("vencimento digitado gera uma parcela só",
       api("GET", f"/api/notas/{completa['id']}", None, t)["nota"]["titulo"]["num_parcelas"] == 1,
       refaturou["mensagem"])

ids_resumo = [n["id"] for n in somente_resumo]
lote = api("POST", "/api/notas/faturar-lote", {"empresa_id": eid, "notas": ids_resumo}, t)
checar("notas só com resumo não são faturadas em lote",
       len(lote["faturadas"]) == 0 and len(lote["recusadas"]) == 2,
       lote["recusadas"][0]["motivo"][:60] if lote["recusadas"] else "")

api("POST", f"/api/notas/{completa['id']}/desfaturar", None, t)
lote2 = api("POST", "/api/notas/faturar-lote",
            {"empresa_id": eid, "notas": [completa["id"]] + ids_resumo}, t)
checar("no lote misto, a nota boa é faturada e as outras ficam de fora",
       len(lote2["faturadas"]) == 1 and len(lote2["recusadas"]) == 2, lote2["mensagem"])
vazio = api("POST", "/api/notas/faturar-lote", {"empresa_id": eid, "notas": []}, t,
            esperar_erro=True)
checar("lote vazio é recusado", vazio.get("_status") == 400)

print("\n=== 7. Segurança ===")
outra = api("POST", "/api/publico/cadastro", {
    "nome": "Outro", "email": f"outro-fat{sufixo}@teste.com", "senha": "123456", "empresa": "Outra"})
alheia = api("GET", f"/api/notas?empresa_id={eid}", None, outra["token"], esperar_erro=True)
checar("outra conta não vê as notas", alheia.get("_status") == 403)
fatura_alheia = api("POST", f"/api/notas/{completa['id']}/faturar", {"empresa_id": eid},
                    outra["token"], esperar_erro=True)
checar("outra conta não fatura nota que não é dela", fatura_alheia.get("_status") == 403)

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print(f"  - {f}")
    raise SystemExit(1)
print("Faturamento OK.")
