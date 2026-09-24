"""Teste da GTA — Guia de Trânsito Animal.

O que se confere
----------------
  * as tabelas (espécies, faixas de idade, finalidades, portais) chegam à tela;
  * a **conferência** aponta, antes do portal, o que o portal vai cobrar:
    propriedade, inscrição estadual, categorias, placa, veterinário;
  * escolher o produtor no cadastro **traz os dados sozinho**, e o que foi
    digitado à mão manda sobre o cadastro;
  * a quantidade total é a **soma das categorias** — e a divergência é apontada;
  * faixa de idade que não é a da espécie é recusada na conferência;
  * trânsito para outro estado cobra veterinário e CRMV;
  * marcar como emitida exige número e validade, e utilizada exige ter sido
    emitida antes;
  * a validade vira aviso e, passando da data, a guia aparece como **vencida**
    sem ninguém marcar nada;
  * o resumo conta válidas, vencendo, vencidas, em preparo e com pendência;
  * a **ficha de preparo** sai com o portal certo do estado (MG → SIAPEC/IMA),
    na ordem das telas, e marca em vermelho o que está em branco;
  * apagar guia já emitida no portal é barrado, com o porquê;
  * o PDF anexado volta inteiro e não trafega na listagem.

Uso:  python testes/teste_gta.py   (com o servidor no ar)
"""
import base64
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

BASE = "http://127.0.0.1:8000"
erros = []


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
    except urllib.error.HTTPError as erro:
        if not esperar_erro:
            raise
        corpo = json.loads(erro.read() or b"{}")
        corpo["_status"] = erro.code
        return corpo


def baixar(caminho, token):
    req = urllib.request.Request(f"{BASE}{caminho}")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as r:
        return r.read()


def checar(descricao, condicao, extra=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {descricao} {extra}")
    if not condicao:
        erros.append(descricao)


def tem(faltas, trecho):
    return any(trecho.lower() in f.lower() for f in faltas)


HOJE = date.today()


def dia(mais):
    return (HOJE + timedelta(days=mais)).isoformat()


# =========================================================================== #
print("=== 1. Conta, empresa e produtores ===")
sufixo = str(int(time.time()))
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Galba", "email": f"gta{sufixo}@teste.com", "senha": "123456",
    "empresa": "Assessoria AgroDock",
    # a GTA só existe nos planos que a incluem
    "plano": "P3_SEMESTRAL"})
t, eid = conta["token"], conta["empresa"]["id"]
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "ASSESSORIA AGRODOCK LTDA", "cnpj": "98765432000198",
    "cidade": "Patrocínio", "uf": "MG", "cep": "38740108",
    "codigo_municipio": "3148004", "crt": "1"}, t)

fazenda = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "AMBOS", "pessoa": "F", "nome": "JOSE DA SILVA",
    "cpf_cnpj": "12345678909", "rg_ie": "0011223344556",
    "cidade": "Patrocínio", "uf": "MG"}, t)
comprador = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "pessoa": "J", "nome": "FRIGORIFICO BOI BOM LTDA",
    "cpf_cnpj": "11222333000181", "rg_ie": "9988776655443",
    "cidade": "Uberlândia", "uf": "MG"}, t)
checar("produtores cadastrados", bool(fazenda.get("id") and comprador.get("id")))

tabelas = api("GET", "/api/gta/tabelas", None, t)
checar("a tela recebe as espécies com as faixas de idade",
       "BOVINO" in tabelas["especies"] and
       "13 a 24 meses" in tabelas["especies"]["BOVINO"],
       str(tabelas["especies"].get("BOVINO"))[:60])
checar("e as finalidades e os portais dos estados",
       "ABATE" in tabelas["finalidades"] and
       tabelas["portais"]["MG"]["sistema"] == "SIAPEC",
       tabelas["portais"]["MG"]["orgao"])

# =========================================================================== #
print("\n=== 2. A conferência: o que o portal vai cobrar ===")
crua = api("POST", "/api/gta", {"empresa_id": eid}, t)["guia"]
faltas = crua["faltas"]
checar("guia vazia nasce em preparo", crua["situacao"] == "PREPARO")
checar("e a conferência cobra a espécie", tem(faltas, "espécie"))
checar("cobra a finalidade", tem(faltas, "finalidade"))
checar("cobra a propriedade (o portal procura a fazenda)", tem(faltas, "propriedade"))
checar("cobra a inscrição estadual", tem(faltas, "inscrição estadual"))
checar("cobra as categorias de animais", tem(faltas, "sexo e idade"))
checar("cobra a placa do caminhão", tem(faltas, "placa"))
checar("e a guia não está pronta", crua["pronta"] is False)

# ------------------------------------------------- o cadastro preenche sozinho
basica = {
    "empresa_id": eid, "especie": "BOVINO", "finalidade": "ABATE",
    "produtor_id": fazenda["id"], "destino_id": comprador["id"],
    "origem_propriedade": "FAZENDA BOA ESPERANCA",
    "destino_propriedade": "UNIDADE INDUSTRIAL I",
    "placa": "hmz 1a23", "meio_transporte": "RODOVIARIO",
    "categorias": [
        {"sexo": "M", "faixa": "13 a 24 meses", "quantidade": 18},
        {"sexo": "F", "faixa": "25 a 36 meses", "quantidade": 7},
    ],
}
guia = api("POST", "/api/gta", basica, t)["guia"]
checar("escolher o produtor traz nome, documento, IE e município",
       guia["origem_nome"] == "JOSE DA SILVA" and
       guia["origem_documento"] == "12345678909" and
       guia["origem_inscricao"] == "0011223344556" and
       guia["origem_municipio"] == "Patrocínio" and guia["origem_uf"] == "MG")
checar("o destino também", guia["destino_nome"] == "FRIGORIFICO BOI BOM LTDA")
checar("a quantidade é a soma das categorias", guia["quantidade"] == 25,
       str(guia["quantidade"]))
checar("a placa é guardada sem espaço e em maiúscula", guia["placa"] == "HMZ1A23",
       guia["placa"])
checar("com tudo preenchido, a guia fica pronta", guia["pronta"] is True,
       str(guia["faltas"])[:90])

digitado = api("POST", "/api/gta", {
    **basica, "origem_nome": "JOSE DA SILVA FILHO",
    "origem_propriedade": "FAZENDA SANTA RITA"}, t)["guia"]
checar("o que foi digitado à mão manda sobre o cadastro",
       digitado["origem_nome"] == "JOSE DA SILVA FILHO", digitado["origem_nome"])

# ------------------------------------------------------ faixa que não é da espécie
torta = api("POST", "/api/gta", {
    **basica, "categorias": [{"sexo": "M", "faixa": "4 a 8 meses", "quantidade": 3}]},
    t)["guia"]
checar("faixa de idade que não é a da espécie é apontada",
       tem(torta["faltas"], "não é uma das que o portal usa"),
       str(torta["faltas"])[:90])

# ------------------------------------------------------------- interestadual
fora = api("POST", "/api/gta", {**basica, "destino_uf": "SP",
                                "destino_municipio": "Barretos"}, t)["guia"]
checar("trânsito para outro estado avisa que é interestadual",
       tem(fora["faltas"], "interestadual"), str(fora["faltas"])[:90])
checar("e cobra o veterinário com CRMV", tem(fora["faltas"], "CRMV"))
com_vet = api("PUT", f"/api/gta/{fora['id']}", {
    **basica, "destino_uf": "SP", "destino_municipio": "Barretos",
    "veterinario": "DRA. ANA PAULA MOREIRA", "crmv": "MG-12345"}, t)["guia"]
checar("com o veterinário, só sobra o aviso de interestadual",
       len(com_vet["faltas"]) == 1 and tem(com_vet["faltas"], "interestadual"),
       str(com_vet["faltas"])[:90])

# =========================================================================== #
print("\n=== 3. Emitir no portal e anotar aqui ===")
sem_numero = api("POST", f"/api/gta/{guia['id']}/situacao",
                 {"empresa_id": eid, "situacao": "EMITIDA"}, t, esperar_erro=True)
checar("marcar emitida sem número é recusado",
       sem_numero.get("_status") == 400 and "número" in str(sem_numero.get("detail")),
       str(sem_numero.get("detail"))[:70])
sem_validade = api("POST", f"/api/gta/{guia['id']}/situacao",
                   {"empresa_id": eid, "situacao": "EMITIDA", "numero": "0012345678"},
                   t, esperar_erro=True)
checar("e sem validade também",
       sem_validade.get("_status") == 400 and "vale" in str(sem_validade.get("detail")),
       str(sem_validade.get("detail"))[:70])

usada_cedo = api("POST", f"/api/gta/{guia['id']}/situacao",
                 {"empresa_id": eid, "situacao": "UTILIZADA"}, t, esperar_erro=True)
checar("guia em preparo não pode virar utilizada",
       usada_cedo.get("_status") == 400, str(usada_cedo.get("detail"))[:70])

emitida = api("POST", f"/api/gta/{guia['id']}/situacao", {
    "empresa_id": eid, "situacao": "EMITIDA", "numero": "0012345678",
    "serie": "1", "data_emissao": dia(0), "data_validade": dia(5)}, t)["guia"]
checar("com número e validade, a guia fica emitida",
       emitida["situacao"] == "EMITIDA" and emitida["numero"] == "0012345678")
checar("e ainda não avisa nada (faltam 5 dias)", emitida["aviso"] == "",
       emitida["aviso"])

# ----------------------------------------------------------------- a validade
vencendo = api("POST", "/api/gta", {**basica, "numero": "0022222222",
                                    "situacao": "EMITIDA", "data_emissao": dia(0),
                                    "data_validade": dia(2)}, t)["guia"]
checar("guia que vence em 2 dias acende o aviso",
       "2 dias" in vencendo["aviso"], vencendo["aviso"])
hoje_mesmo = api("POST", "/api/gta", {**basica, "numero": "0033333333",
                                      "situacao": "EMITIDA", "data_emissao": dia(-1),
                                      "data_validade": dia(0)}, t)["guia"]
checar("e a que vence hoje diz que a carga tem de sair hoje",
       "hoje" in hoje_mesmo["aviso"], hoje_mesmo["aviso"])
venceu = api("POST", "/api/gta", {**basica, "numero": "0044444444",
                                  "situacao": "EMITIDA", "data_emissao": dia(-10),
                                  "data_validade": dia(-3)}, t)["guia"]
checar("passando da data, a guia aparece como vencida sem ninguém marcar",
       venceu["situacao"] == "EMITIDA" and venceu["situacao_mostrada"] == "VENCIDA",
       f'{venceu["situacao"]} → {venceu["situacao_mostrada"]}')
checar("e o aviso diz há quantos dias venceu",
       "venceu há 3 dias" in venceu["aviso"], venceu["aviso"])

# =========================================================================== #
print("\n=== 4. A lista e o resumo ===")
lista = api("GET", f"/api/gta?empresa_id={eid}", None, t)
resumo = lista["resumo"]
checar("o resumo conta as válidas", resumo["validas"] == 3, str(resumo["validas"]))
checar("conta as que estão vencendo", resumo["vencendo"] == 2, str(resumo["vencendo"]))
checar("conta as vencidas", resumo["vencidas"] == 1, str(resumo["vencidas"]))
checar("conta as com pendência", resumo["com_pendencia"] >= 3,
       str(resumo["com_pendencia"]))
checar("e soma os animais", resumo["animais"] > 0, str(resumo["animais"]))

so_vencidas = api("GET", f"/api/gta?empresa_id={eid}&situacao=VENCIDA", None, t)
checar("o filtro por vencida usa a data, não só o que foi marcado",
       len(so_vencidas["guias"]) == 1 and
       so_vencidas["guias"][0]["numero"] == "0044444444",
       str([g["numero"] for g in so_vencidas["guias"]]))

por_produtor = api("GET", f"/api/gta?empresa_id={eid}&produtor_id={fazenda['id']}", None, t)
checar("o filtro por produtor funciona", len(por_produtor["guias"]) >= 5)
por_busca = api("GET", f"/api/gta?empresa_id={eid}&busca=SANTA%20RITA", None, t)
checar("a busca acha pela fazenda", len(por_busca["guias"]) == 1,
       str([g["origem_propriedade"] for g in por_busca["guias"]]))

# =========================================================================== #
print("\n=== 5. A ficha de preparo ===")
ficha = api("GET", f"/api/gta/{emitida['id']}/preparo", None, t)["preparo"]
checar("a ficha diz o portal do estado (Minas → SIAPEC/IMA)",
       ficha["portal"]["sistema"] == "SIAPEC" and "IMA" in ficha["portal"]["orgao"],
       f'{ficha["portal"]["sistema"]} — {ficha["portal"]["orgao"]}')
titulos = [b["titulo"] for b in ficha["blocos"]]
checar("e vem na ordem das telas do portal",
       titulos[0].startswith("1.") and "Origem" in titulos[0]
       and "Destino" in titulos[1] and titulos[2] == "3. Os animais",
       str(titulos))
animais = next(b for b in ficha["blocos"] if b["titulo"].startswith("3."))
checar("o bloco dos animais traz as categorias com o sexo por extenso",
       len(animais["categorias"]) == 2 and
       animais["categorias"][0]["sexo"] == "Macho" and
       animais["categorias"][0]["quantidade"] == 18,
       str(animais["categorias"])[:90])
linhas = {r: v for bloco in ficha["blocos"] for r, v in bloco["linhas"]}
checar("a ficha leva o município com a UF", linhas["Município/UF"] == "Uberlândia/MG",
       str(linhas.get("Município/UF")))
checar("e o número da guia já emitida", linhas["Número da GTA"] == "0012345678")

em_branco = api("GET", f"/api/gta/{crua['id']}/preparo", None, t)["preparo"]
vazias = [v for bloco in em_branco["blocos"] for _, v in bloco["linhas"] if not v]
checar("na guia incompleta, os campos em branco vão em branco para a folha marcar",
       len(vazias) > 5, f"{len(vazias)} campos")
checar("e a folha leva a lista do que o portal vai cobrar",
       len(em_branco["faltas"]) > 3, f'{len(em_branco["faltas"])} pontos')

# =========================================================================== #
print("\n=== 6. O PDF da guia e o apagar ===")
pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
com_anexo = api("PUT", f"/api/gta/{guia['id']}", {
    **basica, "numero": "0012345678", "situacao": "EMITIDA",
    "data_emissao": dia(0), "data_validade": dia(5),
    "arquivo_nome": "GTA-0012345678.pdf",
    "arquivo": base64.b64encode(pdf).decode()}, t)["guia"]
checar("a guia sabe que tem arquivo", com_anexo["tem_anexo"] is True)
checar("e o PDF não trafega na listagem", "arquivo" not in com_anexo)
volta = baixar(f"/api/gta/{guia['id']}/anexo", t)
checar("o PDF volta inteiro", volta == pdf, f"{len(volta)} bytes")

estragado = api("PUT", f"/api/gta/{digitado['id']}",
                {**basica, "arquivo": "isto-não-é-base64!!"}, t, esperar_erro=True)
checar("arquivo ilegível é recusado com frase clara",
       estragado.get("_status") == 400 and "anexe" in str(estragado.get("detail")).lower(),
       str(estragado.get("detail"))[:70])

barrada = api("DELETE", f"/api/gta/{guia['id']}", None, t, esperar_erro=True)
checar("apagar guia já emitida no portal é barrado, com o porquê",
       barrada.get("_status") == 400 and "portal" in str(barrada.get("detail")),
       str(barrada.get("detail"))[:80])
checar("guia em preparo pode ser apagada",
       api("DELETE", f"/api/gta/{crua['id']}", None, t).get("ok") is True)

# =========================================================================== #
print("\n=== 7. A empresa do vizinho ===")
outra = api("POST", "/api/publico/cadastro", {
    "nome": "Outro", "email": f"gta-outro{sufixo}@teste.com", "senha": "123456",
    "empresa": "Outra Assessoria", "plano": "P3_SEMESTRAL"})
espiada = api("GET", f"/api/gta/{guia['id']}", None, outra["token"], esperar_erro=True)
checar("guia de outra conta não abre", espiada.get("_status") in (403, 404),
       str(espiada.get("_status")))

# =========================================================================== #
print("\n" + "=" * 60)
if erros:
    print(f"{len(erros)} FALHA(S):")
    for e in erros:
        print(f"  - {e}")
    sys.exit(1)
print("GTA OK — controle das guias, conferência e ficha de preparo.")
