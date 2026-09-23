"""Traduz a resposta da SEFAZ para o português de quem usa o sistema.

A SEFAZ devolve um código (cStat) e uma frase curta — "Rejeição: Duplicidade
de NF-e" — que não diz o que fazer. Aqui cada código vira três coisas:

  causa     o que aconteceu, em uma frase;
  corrigir  o que a pessoa precisa fazer para a nota passar;
  onde      em que tela está o conserto (a tela usa isso no botão de atalho).

Quando o código não está na tabela, o texto da própria SEFAZ é lido em busca
de palavras conhecidas (certificado, NCM, CFOP...) — é melhor do que nada e
o código e a frase original continuam sempre à vista.
"""

# Lugares do sistema onde o conserto acontece (a tela sabe abrir cada um).
EMPRESA = "empresa"          # Cadastros → Empresas
CLIENTE = "cliente"          # Cadastros → Parceiros
PRODUTO = "produto"          # Cadastros → Produtos
CERTIFICADO = "certificado"  # DF-e → Certificado
NOTA = "nota"                # etapa 1 da nota
ITENS = "itens"              # etapa 2 da nota
PAGAMENTO = "pagamento"      # etapa 3 da nota
ESPERAR = "esperar"          # não é erro de cadastro: tentar de novo depois
SUPORTE = "suporte"          # falha do próprio sistema

# --------------------------------------------------------------------------- #
# Códigos da SEFAZ (cStat) que aparecem no dia a dia
# --------------------------------------------------------------------------- #
TABELA: dict[str, tuple[str, str, str]] = {
    "108": ("O sistema da SEFAZ está parado por instabilidade.",
            "Não é erro da nota. Espere alguns minutos e transmita de novo — "
            "a nota continua como rascunho e não gastou número.", ESPERAR),
    "109": ("O sistema da SEFAZ está fora do ar, sem previsão de volta.",
            "Não é erro da nota. Tente mais tarde; nada foi perdido.", ESPERAR),
    "110": ("A SEFAZ negou o uso desta nota.",
            "Isso costuma ser pendência fiscal do emitente ou do destinatário. "
            "Confira a situação da empresa e do cliente na Receita/SEFAZ do estado. "
            "Nota denegada não pode ser reaproveitada: faça outra depois de resolver.", EMPRESA),
    "204": ("Já existe uma nota igual a esta autorizada na SEFAZ.",
            "A nota já foi transmitida antes. Procure na lista de notas pelo mesmo número "
            "e série — se ela já está autorizada, apague este rascunho.", NOTA),
    "205": ("Esta nota está denegada na SEFAZ.",
            "Nota denegada não volta atrás. Resolva a pendência fiscal e emita outra.", EMPRESA),
    "206": ("O número desta nota foi inutilizado.",
            "Troque a série ou deixe o sistema pegar o próximo número livre.", NOTA),
    "207": ("O CNPJ da sua empresa não foi aceito.",
            "Confira o CNPJ no cadastro da empresa: precisa ser o mesmo do certificado "
            "digital e estar ativo na Receita.", EMPRESA),
    "209": ("A inscrição estadual da sua empresa não foi aceita.",
            "Confira a inscrição estadual no cadastro da empresa — sem pontos, "
            "barras ou espaços, e a mesma que consta na SEFAZ do seu estado.", EMPRESA),
    "210": ("A inscrição estadual do cliente não foi aceita.",
            "Abra o cadastro do cliente e confira a inscrição estadual e a UF. "
            "Se ele é isento, marque como isento em vez de digitar um número.", CLIENTE),
    "211": ("A inscrição estadual do substituto tributário não foi aceita.",
            "Confira a inscrição estadual de substituto tributário no cadastro.", CLIENTE),
    "213": ("O CNPJ da empresa é diferente do CNPJ do certificado digital.",
            "Ou o CNPJ do cadastro da empresa está errado, ou o certificado cadastrado "
            "é de outra empresa. Os dois precisam ter a mesma raiz de CNPJ.", CERTIFICADO),
    "215": ("A SEFAZ recusou o formato do arquivo da nota.",
            "Quase sempre é um campo com caractere estranho ou tamanho maior que o "
            "permitido — olhe descrição do produto, natureza da operação e o texto "
            "complementar. Se continuar, avise o suporte com o código e a frase abaixo.", ITENS),
    "217": ("A SEFAZ não encontrou esta nota na base dela.",
            "A nota não chegou a ser autorizada. Transmita de novo.", NOTA),
    "225": ("A SEFAZ recusou o formato do arquivo da nota.",
            "Confira campos com acento estranho, símbolo ou texto muito longo "
            "(descrição do produto, natureza da operação, informações complementares).", ITENS),
    "226": ("A UF da sua empresa não bate com a SEFAZ que recebeu a nota.",
            "Confira o estado (UF) no cadastro da empresa.", EMPRESA),
    "228": ("A data de emissão está atrasada demais para a SEFAZ.",
            "Ajuste a data de emissão na primeira etapa da nota — use a data de hoje.", NOTA),
    "229": ("A inscrição estadual da sua empresa não foi informada.",
            "Preencha a inscrição estadual no cadastro da empresa.", EMPRESA),
    "233": ("A inscrição estadual do cliente não foi informada.",
            "Preencha a inscrição estadual no cadastro do cliente, ou marque como isento.",
            CLIENTE),
    "236": ("A chave de acesso da nota saiu inconsistente.",
            "Costuma ser CNPJ, UF, série ou número fora do padrão. Confira o cadastro da "
            "empresa e a série da nota; se continuar, avise o suporte.", EMPRESA),
    "238": ("A versão do arquivo é mais nova do que a SEFAZ aceita.", "Avise o suporte.",
            SUPORTE),
    "239": ("A SEFAZ não aceita a versão do arquivo enviada.", "Avise o suporte.", SUPORTE),
    "241": ("Este número de nota já foi usado nesta série.",
            "Ajuste o próximo número da série (tela de séries) para um número ainda livre.",
            NOTA),
    "243": ("O arquivo chegou quebrado na SEFAZ.",
            "Transmita de novo. Se repetir, avise o suporte com o código abaixo.", SUPORTE),
    "252": ("O ambiente da nota não é o mesmo do endereço para onde ela foi.",
            "Na primeira etapa da nota, confira se está em Homologação ou Produção — "
            "e se o certificado cadastrado é do mesmo ambiente.", NOTA),
    "253": ("O dígito verificador da chave de acesso está errado.",
            "Confira o CNPJ da empresa e a série da nota. Se continuar, avise o suporte.",
            EMPRESA),
    "266": ("A série usada não é permitida.",
            "Use uma série dentro da faixa que a SEFAZ do seu estado libera "
            "(normalmente de 1 a 889).", NOTA),
    "280": ("O certificado digital não foi aceito pela SEFAZ.",
            "Cadastre de novo o certificado A1 na aba Certificado do DF-e.", CERTIFICADO),
    "281": ("O certificado digital está fora da validade.",
            "Compre/renove o certificado A1 e cadastre o arquivo novo na aba "
            "Certificado do DF-e.", CERTIFICADO),
    "282": ("O certificado digital não tem CNPJ.",
            "O certificado precisa ser e-CNPJ da empresa (A1). Cadastre o certificado certo.",
            CERTIFICADO),
    "283": ("A cadeia do certificado digital não foi reconhecida.",
            "Cadastre de novo o arquivo .pfx completo, do jeito que a certificadora entregou.",
            CERTIFICADO),
    "284": ("O certificado digital foi revogado.",
            "Esse certificado não serve mais. Providencie outro e cadastre na aba "
            "Certificado do DF-e.", CERTIFICADO),
    "290": ("O certificado que assinou a nota não foi aceito.",
            "Cadastre de novo o certificado A1 na aba Certificado do DF-e.", CERTIFICADO),
    "291": ("O certificado que assinou a nota está fora da validade.",
            "Renove o certificado A1 e cadastre o arquivo novo.", CERTIFICADO),
    "292": ("O certificado que assinou a nota não tem CNPJ.",
            "Use um certificado e-CNPJ (A1) da empresa.", CERTIFICADO),
    "293": ("A cadeia do certificado que assinou a nota não foi reconhecida.",
            "Cadastre de novo o arquivo .pfx completo.", CERTIFICADO),
    "294": ("O certificado que assinou a nota foi revogado.",
            "Providencie outro certificado e cadastre na aba Certificado do DF-e.", CERTIFICADO),
    "297": ("A assinatura digital não conferiu.",
            "Transmita de novo. Se repetir, cadastre o certificado novamente; "
            "persistindo, avise o suporte.", CERTIFICADO),
    "298": ("A assinatura digital saiu fora do padrão exigido.",
            "Transmita de novo e, se repetir, avise o suporte com o código abaixo.", SUPORTE),
    "301": ("A SEFAZ negou a nota por pendência fiscal da sua empresa.",
            "Regularize a situação da empresa na SEFAZ do estado. Enquanto isso, "
            "a nota não é autorizada.", EMPRESA),
    "302": ("A SEFAZ negou a nota por pendência fiscal do cliente.",
            "O destinatário está irregular na SEFAZ. Confirme com ele antes de faturar.",
            CLIENTE),
    "501": ("Passou do prazo de cancelamento.",
            "Não dá mais para cancelar essa nota. O caminho agora é nota de devolução.", NOTA),
    "502": ("A chave de acesso não bate com o conteúdo da nota.",
            "Transmita de novo. Se repetir, avise o suporte.", SUPORTE),
    "528": ("O valor do ICMS não fecha com a soma dos itens.",
            "Confira a tributação dos produtos (CST/CSOSN e alíquota) no cadastro.", PRODUTO),
    "531": ("A base de cálculo do ICMS não fecha com a soma dos itens.",
            "Confira a tributação dos produtos no cadastro.", PRODUTO),
    "539": ("Já existe nota com este número, mas com conteúdo diferente.",
            "Quase sempre é retransmissão de uma nota que já passou. Procure na lista pelo "
            "mesmo número e série antes de mandar de novo.", NOTA),
    "610": ("O total da nota não fecha com a soma dos itens.",
            "Volte na etapa Itens e confira quantidade, valor unitário e desconto.", ITENS),
    "611": ("O código de barras (EAN/GTIN) de um produto é inválido.",
            "No cadastro do produto, deixe o campo de código de barras em branco "
            "se não tiver o GTIN de verdade.", PRODUTO),
    "778": ("O NCM informado não existe na tabela oficial.",
            "Corrija o NCM no cadastro do produto (café cru em grão costuma ser 09011110).",
            PRODUTO),
    "779": ("O NCM informado não está completo.",
            "O NCM precisa ter 8 dígitos. Corrija no cadastro do produto.", PRODUTO),
    # Reforma tributária (NT 2025.002): o CST do IBS/CBS decide se o grupo de
    # base e alíquotas pode ser enviado. Os dois erros são o mesmo assunto,
    # vistos dos dois lados.
    "1021": ("O CST do IBS/CBS deste item não aceita base de cálculo nem alíquota.",
             "CST como 400 (isenção), 410 (imunidade), 550 (suspensão) e 620 "
             "(monofásico) não levam valor de IBS/CBS. Em Cadastros > Regras fiscais, "
             "abra a regra deste item: ou o CST do IBS/CBS está errado para esta "
             "operação, ou ele está certo e as alíquotas de IBS e CBS precisam ficar "
             "zeradas.", ITENS),
    "1022": ("Falta a base de cálculo e as alíquotas do IBS/CBS neste item.",
             "O CST do IBS/CBS deste item é de operação tributada e exige os valores. "
             "Em Cadastros > Regras fiscais, preencha a base e as alíquotas de CBS e "
             "IBS da regra deste item (em 2026 o teste é CBS 0,9% e IBS 0,1%).", ITENS),
    "1115": ("Falta o grupo de IBS/CBS neste item.",
             "Em Cadastros > Regras fiscais, preencha o CST do IBS/CBS, o cClassTrib e "
             "as alíquotas da regra deste item (em 2026 o teste é CBS 0,9% e IBS 0,1%).",
             ITENS),
}

# --------------------------------------------------------------------------- #
# Quando o código não está na tabela: ler a frase da SEFAZ
# --------------------------------------------------------------------------- #
PISTAS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("certificad",),
     "A mensagem fala do certificado digital: confira o certificado A1 na aba "
     "Certificado do DF-e (validade, senha e se é o e-CNPJ da empresa).", CERTIFICADO),
    (("ncm",),
     "A mensagem fala do NCM: corrija o NCM no cadastro do produto (8 dígitos).", PRODUTO),
    (("cfop",),
     "A mensagem fala do CFOP: confira o CFOP dos itens — dentro do estado começa com 5, "
     "para fora do estado com 6.", ITENS),
    (("cest",),
     "A mensagem fala do CEST: preencha ou apague o CEST no cadastro do produto.", PRODUTO),
    (("inscri", " ie "),
     "A mensagem fala de inscrição estadual: confira a da empresa e a do cliente.", CLIENTE),
    (("destinat", "cliente"),
     "A mensagem fala do destinatário: confira o cadastro do cliente — CNPJ/CPF, "
     "inscrição estadual, endereço e código do município.", CLIENTE),
    (("emitente",),
     "A mensagem fala do emitente: confira o cadastro da sua empresa — CNPJ, "
     "inscrição estadual, endereço e código do município.", EMPRESA),
    (("munic",),
     "A mensagem fala do município: confira o código do município (IBGE) no cadastro "
     "da empresa e no do cliente.", EMPRESA),
    (("icms", "pis", "cofins", "tribut", "csosn", "cst"),
     "A mensagem fala de tributação: confira CST/CSOSN, origem e alíquotas no "
     "cadastro do produto.", PRODUTO),
    (("duplicat", "cobran", "fatura", "vencimento"),
     "A mensagem fala das duplicatas: confira as parcelas na etapa Pagamento — "
     "a soma delas tem que bater com o total da nota.", PAGAMENTO),
    (("total", "somat", "valor"),
     "A mensagem fala de valores: confira quantidade, valor unitário e desconto "
     "na etapa Itens.", ITENS),
    (("transport", "frete", "placa", "volume", "peso"),
     "A mensagem fala do transporte: confira a etapa Transporte — frete, placa, "
     "volumes e pesos.", NOTA),
    (("ambiente",),
     "A mensagem fala do ambiente: confira se a nota está em Homologação ou Produção "
     "na primeira etapa, e se o certificado é do mesmo ambiente.", NOTA),
    (("indisponí", "indisponi", "fora do ar", "paralis", "tempo", "timeout"),
     "A SEFAZ não respondeu agora. Não é erro da nota: tente de novo em alguns minutos.",
     ESPERAR),
    (("http 404", "http 403", "http 401", "not found"),
     "O endereço do serviço da SEFAZ respondeu que não existe ou não liberou o acesso. "
     "Confira o estado (UF) da empresa e se o certificado é o da própria empresa. "
     "Se estiver tudo certo, a SEFAZ pode ter mudado o endereço — avise o suporte.", EMPRESA),
    (("http 5", "soap", "fault", "esquema", "schema", "parse", "mal formado", "malformado"),
     "A SEFAZ recusou o envio antes mesmo de olhar a nota — é erro técnico, não de "
     "preenchimento. Tente de novo em alguns minutos; se repetir, use o botão de copiar "
     "abaixo e mande a mensagem inteira para o suporte.", SUPORTE),
)

GENERICO = (
    "Leia a frase da SEFAZ acima — ela diz qual campo recusou. Confira esse campo na nota "
    "ou no cadastro (empresa, cliente ou produto) e transmita de novo. Se não ficar claro, "
    "mande o código e a frase para o suporte."
)


def explicar(codigo: str | None, mensagem: str | None) -> dict:
    """Devolve causa, conserto e em que tela consertar."""
    codigo = (codigo or "").strip()
    mensagem = (mensagem or "").strip()

    if codigo in TABELA:
        causa, corrigir, onde = TABELA[codigo]
        return {"codigo": codigo, "mensagem": mensagem,
                "causa": causa, "corrigir": corrigir, "onde": onde}

    texto = mensagem.lower()
    for palavras, corrigir, onde in PISTAS:
        if any(p in texto for p in palavras):
            return {"codigo": codigo, "mensagem": mensagem,
                    "causa": "A SEFAZ recusou a nota.", "corrigir": corrigir, "onde": onde}

    return {"codigo": codigo, "mensagem": mensagem,
            "causa": "A SEFAZ recusou a nota.", "corrigir": GENERICO, "onde": NOTA}


def explicar_falha(erro: str) -> dict:
    """Mesma ideia para quando nem deu para falar com a SEFAZ (erro de conexão,
    certificado com senha errada, endereço fora do ar)."""
    return explicar("", erro)
