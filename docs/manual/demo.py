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
