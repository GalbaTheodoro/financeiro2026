"""Dados de demonstração do manual da GTA.

Cria uma assessoria no plano completo, os produtores que aparecem nas telas e
seis guias em situações diferentes — é o que faz o manual mostrar o aviso de
validade, a guia vencida e a conferência com pendências.

Rodar com o servidor de demonstração no ar:

    python docs/manual/servidor_demo.py          (numa janela)
    python docs/manual/gta_demo.py               (na outra)
"""
import json
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

B = "http://127.0.0.1:8000"
AQUI = Path(__file__).resolve().parent


def api(metodo, caminho, dados=None, token=None):
    r = urllib.request.Request(
        B + caminho,
        data=json.dumps(dados).encode() if dados is not None else None,
        method=metodo,
    )
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        return json.loads(urllib.request.urlopen(r).read() or b"{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{metodo} {caminho} {e.code} {e.read()[:300]}")


hoje = date.today()


def dia(mais):
    return (hoje + timedelta(days=mais)).isoformat()


# --------------------------------------------------------------- a assessoria
conta = api("POST", "/api/publico/cadastro", {
    "nome": "Marcos Ribeiro", "email": "marcos@brascafe.com.br", "senha": "123456",
    "empresa": "Brascafé Assessoria", "documento": "12.345.678/0001-90",
    "cidade": "Patrocínio", "uf": "MG", "telefone": "(34) 99999-1234",
    # o plano completo é o que libera a GTA junto com o cupom fiscal
    "plano": "P4_ANUAL",
})
t, eid = conta["token"], conta["empresa"]["id"]
api("PUT", f"/api/empresas/{eid}", {
    "razao_social": "BRASCAFÉ ASSESSORIA LTDA", "nome_fantasia": "Brascafé Assessoria",
    "cnpj": "12345678000190", "inscricao_estadual": "0011223344556",
    "logradouro": "AVENIDA FARIA PEREIRA", "numero": "1250", "bairro": "CENTRO",
    "cidade": "Patrocínio", "uf": "MG", "cep": "38740108",
    "codigo_municipio": "3148004", "crt": "3", "telefone": "3439999999"}, t)
api("POST", f"/api/cadastros-contrato/padrao?empresa_id={eid}", None, t)

# ------------------------------------------------------------- os produtores
produtor = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "AMBOS", "pessoa": "F",
    "nome": "ROSALINA SILVEIRA FARIA", "cpf_cnpj": "030.374.749-80",
    "rg_ie": "0011223344556", "cidade": "Indianópolis", "uf": "MG",
    "telefone": "(34) 99777-4455", "email": "rosalina@fazendaboaesperanca.com.br"}, t)
produtor2 = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "AMBOS", "pessoa": "F", "nome": "JOÃO BATISTA MOREIRA",
    "cpf_cnpj": "111.222.333-44", "rg_ie": "0022446688001",
    "cidade": "Patrocínio", "uf": "MG"}, t)
frigorifico = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "nome": "FRIGORÍFICO BOI BOM LTDA",
    "cpf_cnpj": "11.222.333/0001-81", "rg_ie": "9988776655443",
    "cidade": "Uberlândia", "uf": "MG"}, t)
recria = api("POST", "/api/parceiros", {
    "empresa_id": eid, "tipo": "CLIENTE", "pessoa": "F", "nome": "FAZENDA SANTA LUZIA",
    "cpf_cnpj": "222.333.444-55", "rg_ie": "0033557799002",
    "cidade": "Coromandel", "uf": "MG"}, t)

BASE = {
    "empresa_id": eid, "especie": "BOVINO", "meio_transporte": "RODOVIARIO",
    "veterinario": "DRA. ANA PAULA MOREIRA", "crmv": "MG-12345",
}
ORIGEM = {
    "produtor_id": produtor["id"],
    "origem_propriedade": "FAZENDA BOA ESPERANÇA",
    "origem_inscricao": "0011223344556",
}
DESTINO_ABATE = {
    "destino_id": frigorifico["id"],
    "destino_propriedade": "UNIDADE INDUSTRIAL I",
    "destino_inscricao": "9988776655443",
}


def guia(**extras):
    corpo = {**BASE, **extras}
    return api("POST", "/api/gta", corpo, t)["guia"]


# 1. em preparo, ainda faltando dado — é a que mostra a conferência
guia(**ORIGEM, finalidade="ABATE", transportador="TRANSPORTES SÃO JOÃO",
     categorias=[{"sexo": "M", "faixa": "25 a 36 meses", "quantidade": 22}])

# 2. em preparo, completa e pronta para digitar no portal
pronta = guia(**ORIGEM, **DESTINO_ABATE, finalidade="ABATE",
              transportador="TRANSPORTES SÃO JOÃO", placa="HMZ1A23",
              categorias=[{"sexo": "M", "faixa": "25 a 36 meses", "quantidade": 18},
                          {"sexo": "M", "faixa": "acima de 36 meses", "quantidade": 7}])

# 3. emitida e dentro do prazo
guia(**ORIGEM, **DESTINO_ABATE, finalidade="ABATE", transportador="TRANSPORTES SÃO JOÃO",
     placa="RKQ7B88", numero="0032145678", serie="1", situacao="EMITIDA",
     uf_emissora="MG", data_emissao=dia(-1), data_validade=dia(6),
     categorias=[{"sexo": "M", "faixa": "13 a 24 meses", "quantidade": 31}])

# 4. emitida, vencendo em 2 dias — acende o aviso em âmbar
guia(produtor_id=produtor2["id"], origem_propriedade="SÍTIO TRÊS BARRAS",
     origem_inscricao="0022446688001", destino_id=recria["id"],
     destino_propriedade="FAZENDA SANTA LUZIA", destino_inscricao="0033557799002",
     **BASE, finalidade="ENGORDA", transportador="JOSÉ CARLOS TRANSPORTES",
     placa="PUC4D10", numero="0032149911", serie="1", situacao="EMITIDA",
     uf_emissora="MG", data_emissao=dia(-5), data_validade=dia(2),
     categorias=[{"sexo": "F", "faixa": "13 a 24 meses", "quantidade": 14},
                 {"sexo": "F", "faixa": "25 a 36 meses", "quantidade": 9}])

# 5. passou da validade sem ser usada — aparece como vencida sozinha
guia(**ORIGEM, **DESTINO_ABATE, finalidade="ABATE", transportador="TRANSPORTES SÃO JOÃO",
     placa="HMZ1A23", numero="0032140077", serie="1", situacao="EMITIDA",
     uf_emissora="MG", data_emissao=dia(-14), data_validade=dia(-4),
     categorias=[{"sexo": "M", "faixa": "acima de 36 meses", "quantidade": 12}])

# 6. já utilizada: a carga andou
usada = guia(**ORIGEM, **DESTINO_ABATE, finalidade="ABATE",
             transportador="TRANSPORTES SÃO JOÃO", placa="RKQ7B88",
             numero="0032138840", serie="1", situacao="EMITIDA", uf_emissora="MG",
             data_emissao=dia(-20), data_validade=dia(-13),
             categorias=[{"sexo": "M", "faixa": "25 a 36 meses", "quantidade": 26}])
api("POST", f"/api/gta/{usada['id']}/situacao", {"empresa_id": eid, "situacao": "UTILIZADA"}, t)

(AQUI / "tokens-gta.json").write_text(
    json.dumps({"t": t, "eid": eid, "pronta": pronta["id"]}), encoding="utf-8")
print(f"pronto — {api('GET', f'/api/gta?empresa_id={eid}', None, t)['resumo']}")
