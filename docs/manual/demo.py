import json, urllib.request, urllib.error
from datetime import date, timedelta
B="http://127.0.0.1:8000"
def api(m,c,d=None,t=None,token=None):
    t=t or token
    r=urllib.request.Request(B+c,data=json.dumps(d).encode() if d is not None else None,method=m)
    r.add_header("Content-Type","application/json")
    if t: r.add_header("Authorization","Bearer "+t)
    try: return json.loads(urllib.request.urlopen(r).read() or b"{}")
    except urllib.error.HTTPError as e: raise SystemExit(f"{m} {c} {e.code} {e.read()[:300]}")
hoje=date.today()
# dono do site
api("POST","/api/publico/cadastro",{"nome":"Galba Theodoro","email":"dono@agrodock.com.br","senha":"123456","empresa":"AgroDock"})
tm=api("POST","/api/auth/login",{"email":"dono@agrodock.com.br","senha":"123456"})["token"]
api("PUT","/api/admin/configuracoes",{"valores":{"pix_chave":"34991868583","pix_titular":"Galba Theodoro","pix_cidade":"UBERLANDIA","contato_whatsapp":"(34) 99186-8583","contato_email":"contato@agrodock.com.br"}},tm)
# cliente assinante
c=api("POST","/api/publico/cadastro",{"nome":"Marcos Ribeiro","email":"marcos@brascafe.com.br","senha":"123456","empresa":"Brascafé Assessoria","documento":"12.345.678/0001-90","cidade":"Patrocínio","uf":"MG","telefone":"(34) 99999-1234"})
t=c["token"]; eid=c["empresa"]["id"]
for n,e in (("Ana Paula","ana@brascafe.com.br"),("Rafael Souza","rafael@brascafe.com.br")):
    api("POST","/api/usuarios",{"nome":n,"email":e,"senha":"123456","perfil":"OPERADOR","empresa_id":eid},t)
for nome,em in (("Cafeeira Sul de Minas","financeiro@cafeeira.com.br"),("João Batista","joao@gmail.com")):
    api("POST","/api/publico/cadastro",{"nome":nome,"email":em,"senha":"123456","empresa":nome})
lista=api("GET","/api/admin/empresas",token=tm)["linhas"]
bras=next(l for l in lista if l["usuario_email"]=="marcos@brascafe.com.br")
api("POST",f"/api/admin/empresas/{bras['id']}/acesso",{"acao":"LIBERAR","ate":(hoje+timedelta(days=182)).isoformat(),"observacao":"Pix semestral recebido"},tm)
caf=next(l for l in lista if l["usuario_email"]=="financeiro@cafeeira.com.br")
api("POST",f"/api/admin/empresas/{caf['id']}/acesso",{"acao":"LIBERAR","ate":(hoje+timedelta(days=9)).isoformat()},tm)
contas=api("GET",f"/api/contas-contabeis?empresa_id={eid}",token=t); pc={x["codigo"]:x for x in contas}
banco=api("POST","/api/bancos",{"empresa_id":eid,"codigo":"001","nome":"Sicoob C/C","codigo_banco":"756","agencia":"3170","conta":"12345-6","tipo":"CORRENTE","conta_contabil_id":pc["1.1.01.002"]["id"],"saldo_inicial":25000,"data_saldo_inicial":(hoje-timedelta(days=30)).isoformat()},t)
comp=api("POST","/api/parceiros",{"empresa_id":eid,"tipo":"CLIENTE","nome":"OLAM AGRÍCOLA LTDA","cpf_cnpj":"07.028.528/0008-94","cidade":"Alfenas","uf":"MG","email":"compras@olam.com"},t)
comp2=api("POST","/api/parceiros",{"empresa_id":eid,"tipo":"CLIENTE","nome":"COOXUPÉ","cpf_cnpj":"20.770.566/0001-00","cidade":"Guaxupé","uf":"MG"},t)
vend=api("POST","/api/parceiros",{"empresa_id":eid,"tipo":"CLIENTE","pessoa":"F","nome":"ROSALINA SILVEIRA FARIA","cpf_cnpj":"030.374.749-80","cidade":"Indianópolis","uf":"MG"},t)
vend2=api("POST","/api/parceiros",{"empresa_id":eid,"tipo":"CLIENTE","pessoa":"F","nome":"FAZENDA SANTA LUZIA","cpf_cnpj":"111.222.333-44","cidade":"Patrocínio","uf":"MG"},t)
comp3=api("POST","/api/parceiros",{"empresa_id":eid,"tipo":"CLIENTE","nome":"TORREFAÇÃO PAULISTA LTDA","cpf_cnpj":"33.444.555/0001-66","cidade":"Santos","uf":"SP"},t)
# tabela de ICMS: interestaduais de referência saindo de MG + uma linha só para o café
api("POST","/api/icms/gerar-padrao",{"empresa_id":eid,"uf_origem":"MG"},t)
forn=api("POST","/api/parceiros",{"empresa_id":eid,"tipo":"FORNECEDOR","nome":"Imobiliária Central Ltda","cpf_cnpj":"22.333.444/0001-55","cidade":"Patrocínio","uf":"MG"},t)
api("POST",f"/api/parceiros/{vend['id']}/formas-pagamento",{"tipo":"PIX","pix_tipo":"CPF","pix_chave":"03037474980","apelido":"Pix pessoal"},t)
api("POST",f"/api/parceiros/{vend['id']}/formas-pagamento",{"tipo":"DEPOSITO","banco_codigo":"001","banco_nome":"Banco do Brasil","agencia":"1234","conta":"56789-0","tipo_conta":"CORRENTE"},t)
usuarios=api("GET","/api/usuarios",token=t); rep=usuarios[0]["id"]
prods=api("GET",f"/api/produtos?empresa_id={eid}",token=t); mods=api("GET",f"/api/modalidades?empresa_id={eid}",token=t); unis=api("GET",f"/api/unidades?empresa_id={eid}",token=t)
sc=next(u for u in unis if u["codigo"]=="SC")
def contrato(comprador,vendedor,q,p,dias,**kw):
    d=dict(empresa_id=eid,comprador_id=comprador["id"] if comprador else None,
           vendedor_id=vendedor["id"] if vendedor else None,representante_id=rep,produto_id=prods[0]["id"],modalidade_id=mods[0]["id"],unidade_id=sc["id"],embalagem="A GRANEL",quantidade=q,preco_unitario=p,data=(hoje-timedelta(days=dias)).isoformat(),data_pagamento=(hoje+timedelta(days=10-dias)).isoformat(),data_embarque=(hoje+timedelta(days=5)).isoformat(),comissao_comprador_percentual=0.5,comissao_vendedor_percentual=0.5,local_coleta="Armazém Brascafé",local_descarga="Armazém do comprador")
    d.update(kw); return api("POST","/api/contratos",d,t)
# contratos de compra e de venda da própria empresa, com agente
agente=api("POST","/api/parceiros",{"empresa_id":eid,"tipo":"AMBOS","pessoa":"F","nome":"JOSÉ AGENTE DE CAFÉ","cpf_cnpj":"555.666.777-88","cidade":"Araguari","uf":"MG"},t)
compra=contrato(None,vend2,200,1300,5,tipo="COMPRA",comprador_id=None,agente_id=agente["id"],agente_percentual=1)
api("POST",f"/api/contratos/{compra['id']}/gerar-recebiveis",{"gerar_mercadoria":True,"gerar_agente":True},t)
venda=contrato(comp3,None,200,1450,2,tipo="VENDA",vendedor_id=None,agente_id=agente["id"],agente_valor=1500,agente_percentual=0)
api("POST",f"/api/contratos/{venda['id']}/gerar-recebiveis",{"gerar_mercadoria":True,"gerar_agente":True},t)
c1=contrato(comp3,vend,330,1320,12)
c2=contrato(comp2,vend2,500,1285,8)
c3=contrato(comp,vend2,120,1410,3)
c4=contrato(comp3,vend2,250,1350,1)
api("POST",f"/api/contratos/{c1['id']}/gerar-recebiveis",{"gerar_comprador":True,"gerar_vendedor":True},t)
api("POST",f"/api/contratos/{c2['id']}/gerar-recebiveis",{"gerar_comprador":True,"gerar_vendedor":True},t)
parc=api("GET",f"/api/parcelas?empresa_id={eid}&tipo=RECEBER&situacao=ABERTAS",token=t)
p=next(x for x in parc if x["numero_documento"]==c1["numero"])
api("POST",f"/api/parcelas/{p['id']}/baixar",{"banco_id":banco["id"],"data":hoje.isoformat(),"forma_pagamento":"PIX","historico":"Comissão recebida"},t)
cc=api("GET",f"/api/centros-custo?empresa_id={eid}",token=t)
api("POST","/api/lancamentos",{"empresa_id":eid,"tipo":"PAGAR","modo":"SIMPLES","numero_documento":"ALG-09","parceiro_id":forn["id"],"descricao":"Aluguel do escritório","data_emissao":hoje.isoformat(),"data_competencia":hoje.isoformat(),"valor_total":2800,"itens":[{"conta_contabil_id":pc["4.3.01.001"]["id"],"centro_custo_id":cc[0]["id"],"valor":2800}],"num_parcelas":1,"primeiro_vencimento":(hoje+timedelta(days=5)).isoformat()},t)
api("POST","/api/lancamentos",{"empresa_id":eid,"tipo":"PAGAR","modo":"SIMPLES","numero_documento":"NF-552","parceiro_id":forn["id"],"descricao":"Internet e telefone","data_emissao":hoje.isoformat(),"data_competencia":hoje.isoformat(),"valor_total":349.9,"itens":[{"conta_contabil_id":pc["4.3.01.009"]["id"],"centro_custo_id":cc[0]["id"],"valor":349.9}],"num_parcelas":1,"primeiro_vencimento":hoje.isoformat(),"baixar_agora":True,"banco_id":banco["id"]},t)
print(json.dumps({"eid":eid,"t":t,"tm":tm}))

# ---------------------------------------------------------------- DF-e
# certificado A1 de demonstração (gerado na hora) e notas fiscais de exemplo
import time as _time
from datetime import datetime as _dt, timedelta as _td, timezone as _tz
from pathlib import Path as _P


def _pfx(cnpj, nome, senha):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes as _hh, serialization as _ss
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa
    from cryptography.hazmat.primitives.serialization import pkcs12 as _p12
    from cryptography.x509.oid import NameOID
    k = _rsa.generate_private_key(public_exponent=65537, key_size=2048)
    n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"{nome}:{cnpj}")])
    a = _dt.now(_tz.utc)
    c = (x509.CertificateBuilder().subject_name(n).issuer_name(n).public_key(k.public_key())
         .serial_number(x509.random_serial_number())
         .not_valid_before(a - _td(days=100)).not_valid_after(a + _td(days=265))
         .sign(k, _hh.SHA256()))
    return _p12.serialize_key_and_certificates(
        name=b"demo", key=k, cert=c, cas=None,
        encryption_algorithm=_ss.BestAvailableEncryption(senha.encode()))


def _enviar(caminho, campos, arquivo, token):
    limite = "----agrodock" + str(int(_time.time() * 1000))
    partes = [f'--{limite}\r\nContent-Disposition: form-data; name="{n}"\r\n\r\n{v}\r\n'.encode()
              for n, v in campos.items()]
    nome, conteudo, tipo = arquivo
    partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="arquivo"; '
                  f'filename="{nome}"\r\nContent-Type: {tipo}\r\n\r\n'.encode() + conteudo + b"\r\n")
    partes.append(f"--{limite}--\r\n".encode())
    r = urllib.request.Request(B + caminho, data=b"".join(partes), method="POST")
    r.add_header("Content-Type", f"multipart/form-data; boundary={limite}")
    r.add_header("Authorization", "Bearer " + token)
    try:
        return json.loads(urllib.request.urlopen(r).read() or b"{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"POST {caminho} {e.code} {e.read()[:300]}")


CNPJ_DEMO = "12345678000190"
api("PUT", f"/api/empresas/{eid}", {"razao_social": "BRASCAFÉ ASSESSORIA LTDA",
    "nome_fantasia": "Brascafé Assessoria", "cnpj": CNPJ_DEMO, "cidade": "Patrocínio",
    "uf": "MG", "inscricao_estadual": "0011223344001"}, t)
_enviar("/api/dfe/certificado",
        {"empresa_id": eid, "senha": "demo123", "ambiente": "1", "uf_autor": "MG"},
        ("brascafe-a1.pfx", _pfx(CNPJ_DEMO, "BRASCAFÉ ASSESSORIA LTDA", "demo123"),
         "application/x-pkcs12"), t)

_XML = _P('/home/claude/app/testes/dados_dfe/nfe_completa.xml').read_text(encoding='utf-8')
_XML = (_XML.replace("98765432000198", CNPJ_DEMO)
        .replace("ASSESSORIA AGRODOCK LTDA", "BRASCAFE ASSESSORIA LTDA")
        .replace("2026-09-10", (hoje - timedelta(days=6)).isoformat())
        .replace("2026-10-10", (hoje + timedelta(days=24)).isoformat())
        .replace("2026-11-10", (hoje + timedelta(days=54)).isoformat()))
_enviar("/api/dfe/enviar-xml", {"empresa_id": eid}, ("nota.xml", _XML.encode(), "application/xml"), t)

for _i, (_num, _cnpj, _nome, _valor, _dias) in enumerate([
        ("004512", "20770566000100", "COOXUPE COOP REGIONAL DE CAFEICULTORES", "18420.00", 2),
        ("019887", "07028528000894", "OLAM AGRICOLA LTDA", "254300.75", 4),
        ("000733", "22333444000155", "IMOBILIARIA CENTRAL LTDA", "2800.00", 9),
        ("102394", "11223344000186", "TRANSPORTES CERRADO MINEIRO LTDA", "6740.90", 11)]):
    _dia = (hoje - timedelta(days=_dias)).isoformat()
    # chave de acesso: UF(2) AAMM(4) CNPJ(14) mod(2) série(3) número(9) tpEmis(1) código(8) DV(1)
    _ch = "31" + hoje.strftime("%y%m") + _cnpj + "55" + "001" + _num.zfill(9) + "1" + f"8765432{_i}" + "0"
    _res = f'''<?xml version="1.0" encoding="UTF-8"?>
<resNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
<chNFe>{_ch}</chNFe><CNPJ>{_cnpj}</CNPJ><xNome>{_nome}</xNome><IE>0011223344009</IE>
<dhEmi>{_dia}T09:30:00-03:00</dhEmi><tpNF>1</tpNF><vNF>{_valor}</vNF>
<digVal>x</digVal><dhRecbto>{_dia}T09:31:00-03:00</dhRecbto><nProt>1312600998877{_i}</nProt>
<cSitNFe>1</cSitNFe></resNFe>'''
    _enviar("/api/dfe/enviar-xml", {"empresa_id": eid}, (f"{_num}.xml", _res.encode(), "application/xml"), t)

_notas = api("GET", f"/api/dfe/notas?empresa_id={eid}", token=t)
_completa = next(n for n in _notas if not n["resumo"])
api("POST", f"/api/dfe/notas/{_completa['id']}/importar",
    {"empresa_id": eid, "criar_parceiro": True, "atualizar_produtos": True, "gerar_titulo": True}, t)
