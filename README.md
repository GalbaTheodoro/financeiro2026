# AgroDock — Contratos e Gestão

O **AgroDock** é o sistema de contratos de assessoria e gestão financeira: **contratos de
corretagem** com comissão dos dois lados, **contas a receber**, **contas a pagar**,
**caixa/bancos**, **lançamentos simples e múltiplos**, todos os cadastros de apoio e
relatórios gerenciais e contábeis — incluindo **DRE** e **Balancete de Verificação**.

Vem com um **site de apresentação** na primeira tela, onde o visitante conhece o
sistema, **cria a própria conta** e contrata um dos planos: **semestral R$ 350** ou
**anual R$ 600**, pagos por **Pix**. A conta fica liberada por **48 horas** logo após o
cadastro, para teste, e é desbloqueada de novo quando você confirma o recebimento do Pix.

Back-end em Python (FastAPI) e interface web que abre no navegador. O banco pode ser
um **arquivo no próprio computador** (SQLite, pronto para usar, sem instalar nada) ou um
**PostgreSQL na nuvem** — trocando só uma configuração, sem mexer no sistema. Veja a
seção **6. Colocar no ar**.

---

## 1. Como rodar

**Pré-requisito:** Python 3.10 ou superior instalado.

### Linux / macOS

```bash
chmod +x iniciar.sh
./iniciar.sh
```

### Windows

Dê dois cliques em `iniciar.bat` (ou rode no prompt).

### Manualmente

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --port 8000
```

Depois abra **http://localhost:8000** no navegador — o site de apresentação aparece
primeiro; para entrar no sistema, use **Entrar** no topo.

**Acesso do administrador:** `admin@financeiro.local` / senha `admin123`
(troque a senha em Cadastros → Usuários assim que entrar).

O banco de dados fica no arquivo `dados/financeiro.db`. Para fazer backup, basta
copiar esse arquivo. Para começar do zero, apague-o e reinicie o sistema.
O esquema é atualizado sozinho a cada versão nova, sem perder os dados.

### Atualizando para uma versão nova

1. Substitua as pastas `backend`, `frontend` e `testes` e o `README.md` pelos novos.
   **Não mexa em `dados/`** — é onde ficam os seus lançamentos.
2. Feche a janela do sistema (Ctrl+C) e rode `iniciar.bat` de novo. As colunas novas do
   banco são criadas sozinhas na inicialização.
3. No canto inferior esquerdo, embaixo do seu nome, aparece **a data da versão carregada**.
   Se ela não bater com a atualização, atualize a página com **Ctrl+F5**.

O sistema já manda o navegador conferir os arquivos a cada carregamento (cada arquivo
vai com um carimbo de versão), então o normal é a atualização aparecer sozinha.

---

## 1.1. Primeiros passos como dono do sistema

**Quem é o administrador do site:** a conta com o e-mail **galbatheo@gmail.com** (ou o
e-mail colocado na variável `FIN_MASTER_EMAIL`). Basta ter cadastro com esse e-mail — no
próximo login ela vira administradora e ganha o menu **Administração**. Nesse momento o
login de fábrica `admin@financeiro.local` é desligado se ainda estiver com a senha
`admin123` (que está escrita neste manual e não pode ficar valendo num site na internet).

1. Entre como administrador e vá em **Administração → Config. do site**.
2. Preencha a **chave Pix**, o **titular** e a **cidade** — é com esses dados que o
   sistema monta o QR Code e o código copia e cola de cada assinante.
3. Ajuste o **nome do produto**, o **slogan**, o **WhatsApp** e o **e-mail de suporte**
   que aparecem no site, e os **valores dos planos** se quiser mudar o preço.
4. Acompanhe os cadastros em **Administração → Assinaturas**: quem está em teste, quem
   já avisou que pagou e quem está ativo. Ao receber o Pix, clique em **Confirmar Pix**
   para liberar a conta pelo prazo do plano.
5. Em **Administração → Empresas e acessos** fica a lista de todas as empresas
   cadastradas, com CNPJ, responsável, situação, até quando está liberada e usuários em
   uso / limite. Ali você:
   - **Liberar até…** — escolhe a data (atalhos +30 dias, +6 meses, +1 ano). No dia
     seguinte a empresa bloqueia sozinha;
   - **Bloquear** — corta o acesso na hora (os dados ficam guardados);
   - **Limite** — muda quantos usuários a empresa pode ter (padrão: 3). Em branco volta
     ao padrão;
   - **Usuários** — para cada pessoa da empresa: liberado/bloqueado e **acesso até**
     uma data. Quem o administrador do site bloqueia, o admin da empresa não reativa.

Enquanto a chave Pix não estiver preenchida, o assinante vê um aviso pedindo para falar
com o suporte, em vez de dados de pagamento inventados.

---

## 2. O que o sistema faz

### Site, cadastro e assinatura

- **Página inicial** apresentando os recursos, como funciona e os planos, com botões de
  **Entrar** e **Criar conta grátis**.
- **Auto-cadastro**: o visitante informa nome, e-mail, senha, empresa e plano pretendido.
  A conta é criada já com plano de contas, centros de custo e operações padrão.
- **Teste de 48 horas** liberado na hora, sem cartão. Uma faixa no topo do sistema mostra
  quanto tempo ainda resta.
- **Pagamento por Pix** dentro do sistema: QR Code, chave e código copia e cola gerados
  com o valor do plano escolhido (padrão EMV do Banco Central) e um identificador por conta.
- Terminadas as 48 horas, a conta é **bloqueada** e cai na tela de pagamento — os dados
  lançados continuam guardados.
- O assinante clica em **“Já fiz o Pix”**; você confere o recebimento e clica em
  **Confirmar Pix**, o que **libera o acesso** pelo prazo do plano (6 ou 12 meses).
- **Isolamento entre contas**: cada assinante enxerga somente as próprias empresas e
  usuários; apenas o perfil MASTER administra o sistema.

| Plano | Valor | Duração | Equivale a |
|---|---|---|---|
| Semestral | R$ 350,00 | 6 meses | R$ 58,33/mês |
| Anual | R$ 600,00 | 12 meses | R$ 50,00/mês |

Os valores, a duração e as horas de teste são editáveis em **Config. do site**.

### Faixa de cotações do café (rodapé)

Uma faixa fixa no rodapé — no site e dentro do sistema — fica passando as cotações:

| Grupo | Contratos | Fonte |
|---|---|---|
| **Bolsa de NY** (arábica, ¢/lb) | os 3 próximos vencimentos (mar, mai, jul, set, dez) | ICE US via Yahoo Finance, com poucos minutos de atraso; se falhar, Notícias Agrícolas |
| **Bolsa de Londres** (robusta, US$/t) | 3 próximos vencimentos | fechamento do dia anterior, Notícias Agrícolas |
| **Bolsa B3** (arábica 4/5, US$/sc) | 3 próximos vencimentos, variação em % | fechamento do dia anterior, Notícias Agrícolas |
| **Moedas** | DXY, Dólar, Euro e Ptax | Yahoo Finance (dólar/euro têm reserva na AwesomeAPI) e Banco Central (Ptax) |

O servidor consulta as fontes no máximo de 10 em 10 minutos e guarda o resultado no banco
(tabela `cache_externo`); os navegadores pedem a faixa de 5 em 5 minutos. Se uma fonte cair,
o grupo continua com o último valor bom ("último valor disponível"). Passar o mouse pausa
a faixa. Em **Config. do site → Faixa de cotações** dá para desligar (`cotacoes_ativas`) ou
mudar o intervalo (`cotacoes_minutos`). Código: `backend/cotacoes.py` e `frontend/js/cotacoes.js`;
teste sem internet: `python testes/teste_cotacoes.py`.

> As cotações de bolsa são informativas e vêm de fontes públicas gratuitas, sem garantia
> de disponibilidade. Para uso comercial com clientes pagantes, avalie contratar um
> provedor de dados licenciado.

#### Painel "Mercado do Café" (`/mercado`)

Clicar na faixa (ou em **Painel completo ›**) abre `/mercado` numa nova aba, sem login:

| Aba | O que mostra | Filtros | Fonte |
|---|---|---|---|
| **Bolsas e indicadores** | NY, Londres, B3, Cepea (arábica e conilon), Dólar Ptax/comercial, euro e DXY: gráfico, máxima, mínima, variação no período e tabela | série, contrato, 7/30/90 dias, 1 ano, tudo, de/até; **baixar CSV** | Notícias Agrícolas, Banco Central |
| **Preços por cidade** | cartão por cidade (Patrocínio, Varginha, Araguari e Patos de Minas primeiro) com tipo 6/7, tipo 6 duro, cereja descascado, conilon e as cotações por cidade da AgnoCafé; histórico por cidade | tipo de café, cidade, data, só a região | Notícias Agrícolas (Expocaccer, Minasul, Coocacer, Cooxupé...) e agnocafe.com.br |
| **Notícias** | café e demais culturas, marcadas por cultura e por região; as da região em destaque ficam com borda laranja | região (as 4 cidades, Sul de Minas, Triângulo/Alto Paranaíba), cultura, busca, período | RSS do Canal Rural e do g1 (Agronegócios, Sul de Minas, Triângulo) e Notícias Agrícolas |

* O histórico fica na tabela `cotacao_historico`. As fontes mostram só ~10 pregões, mas o
  painel guarda todos os que lê: o filtro de período alcança mais tempo a cada dia.
* Notícias: guardadas por 60 dias em `cache_externo`; só título, resumo curto e link (a
  matéria abre no site de quem publicou). Dos feeds regionais do g1 entram só as do agro.
* Patos de Minas ainda não tem cotação publicada nas fontes gratuitas; o cartão avisa isso.
* Config. do site: `mercado_minutos` (30), `noticias_minutos` (20) e `mercado_agnocafe`
  (1/0, desliga as cotações da AgnoCafé). Desligar a faixa (`cotacoes_ativas`) desliga o painel.
* Código: `backend/mercado.py`, rotas `/api/publico/mercado/*` em `backend/routers/publico.py`,
  `frontend/mercado.html`, `frontend/mercado.css`, `frontend/js/mercado.js`.
  Teste sem internet: `python testes/teste_mercado.py`.

> Os preços por cidade da AgnoCafé e as páginas do Notícias Agrícolas são lidos do site deles
> (não há API pública). Antes de vender o painel como recurso pago, peça autorização a esses
> sites ou contrate um provedor de dados; se a página deles mudar, o painel mostra o último
> valor guardado até o leitor ser ajustado.

### Cadastros

Tudo num único menu **Cadastros**, com abas — não há mais itens de cadastro espalhados
pela barra lateral.

| Aba | Para que serve |
|---|---|
| **Clientes / Fornecedores** | Um único cadastro, com tipo Cliente, Fornecedor ou ambos, **busca automática pelo CNPJ** e **várias formas de pagamento** por parceiro |
| **Produtos** | O que é negociado (café arábica, conilon...), já com unidade e embalagem padrão |
| **Unidades** | Código, nome e **peso de conversão em quilos** — é o que dá o peso total do contrato |
| **Modalidades** | Modalidade do contrato (disponível, futuro, a fixar, CIF, FOB...) |
| **Bancos e caixas** | Conta corrente, poupança, aplicação, cartão e caixa interno, com saldo inicial |
| **Centros de custo** | Classificação gerencial (administrativo, comercial, projetos...) |
| **Operações** | Natureza do movimento (venda, compra, folha, aluguel...) — sugere a conta contábil |
| **Plano de contas** | Contas contábeis sintéticas e analíticas, com grupo no DRE |
| **Empresas** | Multiempresa: cada empresa tem seus próprios cadastros e relatórios, além do **logotipo e das cláusulas** usados no contrato impresso |
| **Usuários** | Acesso ao sistema, com perfis Administrador, Operador e Consulta |
| **Parâmetros contábeis** | Contas usadas automaticamente pelo sistema (clientes, fornecedores, juros...) |

Ao criar uma empresa o sistema já gera um **plano de contas brasileiro completo**
(112 contas), centros de custo e operações padrão, além de **unidades** (saca de 60 e de
50 kg, arroba, tonelada, quilo, litro, unidade), **modalidades** e **produtos** prontos
para usar.

### Usuários incluídos e pacotes extras

Cada empresa assinante tem **3 usuários** inclusos (configurável em Config. do site →
`usuarios_incluidos`; bancos antigos que estavam no padrão 5 passam para 3 uma vez só).
Ao tentar cadastrar o quarto usuário, o sistema avisa e não deixa passar.

Para aumentar: o administrador do site muda o **Limite** da empresa em **Empresas e
acessos** depois de receber o pagamento. Continua existindo o caminho automático dos
pacotes: em **Minha Assinatura** o assinante pede pacotes de **+5 usuários** com **65% de
desconto** sobre o plano, paga pelo Pix próprio do pedido e o limite sobe na confirmação.

### Contratos: corretagem, compra e venda

Em **Movimento → Contratos** cabem os três jeitos de fazer o negócio. O tipo é escolhido na
primeira etapa do formulário e decide quem são as partes e quais títulos o contrato gera:

| Tipo | Partes | O que o contrato gera |
|---|---|---|
| **Corretagem (intermediação)** | comprador e vendedor, os dois de fora | **contas a receber** das comissões do comprador e do vendedor |
| **Compra de café** | o comprador é a **sua empresa**; escolha só o fornecedor | **conta a pagar** do fornecedor (valor do café), classificada em *Custo das Mercadorias Vendidas* |
| **Venda de café** | o vendedor é a **sua empresa**; escolha só o cliente | **conta a receber** do cliente, classificada em *Receita de Venda de Mercadorias* |

Nos três tipos dá para informar um **agente** que intermediou, com percentual sobre o valor
do contrato ou valor fechado: a comissão dele vira uma **conta a pagar** da sua empresa, em
*Comissões sobre Vendas*. Na compra e na venda o ICMS usa a UF da sua empresa de um lado e a
do parceiro do outro. A ficha e a folha impressa mudam conforme o tipo (na compra, por
exemplo, sai "Contrato de compra", com a sua empresa no lado do comprador), e a situação do
contrato aparece com as palavras certas: na compra, *Fechado a Pagar*, *Pago Parcial* e
*Pago Total*.

O resto vale para todos os tipos:

- **Numeração automática**: o número sai pronto (00000001, 00000002...) seguindo o maior
  número já usado na empresa. Dá para digitar outro quando o contrato vem numerado de fora.
- **Partes e mercadoria**: comprador, vendedor, **representante** (escolhido entre os
  usuários da empresa), **produto**, **modalidade** e **unidade** vindos dos cadastros,
  embalagem, local de coleta e de descarga, números de compra e venda.
- **Peso total**: quantidade × peso de conversão da unidade — 330 sacas de 60 kg viram
  19.800 kg, calculado na tela enquanto você digita.
- **Quantidade e valores**: quantidade × (preço unitário + diferencial) = valor negociado,
  calculado na hora enquanto você digita. Dá para digitar o valor fechado direto.
- **Corretagem dos dois lados** (só na corretagem): um percentual para o comprador e outro
  para o vendedor, independentes. O valor aparece calculado e pode ser ajustado à mão quando o combinado
  foi um valor fixo.
- **Gerar os títulos**: um clique cria as contas — na corretagem, uma para cada comissão;
  na compra, a conta a pagar do café; na venda, a conta a receber do café; e, quando há
  agente, a conta a pagar dele (com vencimento próprio, se quiser). Sempre com o número do
  contrato como documento, vencimento na data de pagamento do contrato e classificação
  contábil automática. Aceita parcelar e escolher o que gerar.
- **Situação que anda sozinha**: cada contrato mostra em que pé está, e a situação muda
  conforme o dinheiro entra — sem ninguém marcar nada:

  | Situação | Quando aparece |
  |---|---|
  | **Aberto** | contrato lançado, comissões ainda não viraram título |
  | **Fechado a Receber** | as contas a receber foram geradas, nada recebido ainda |
  | **Fechado Recebido Parcial** | parte da comissão já foi baixada no caixa |
  | **Fechado Recebido Total** | a comissão inteira foi recebida |
  | **Cancelado** | cancelado à mão (dá para reabrir depois) |

  Na lista, as situações aparecem como botões com a contagem — um clique filtra.
- **Migração automática**: quem já usava o sistema não precisa fazer nada. Na primeira
  subida os contratos antigos passam a ser do tipo *Corretagem* e os campos de comprador e
  vendedor deixam de ser obrigatórios (na compra e na venda um dos lados é a própria
  empresa). Teste: `python testes/teste_migracao.py`.
- **Estorno**: enquanto não houver baixa, um clique apaga os títulos e devolve o contrato
  para "aberto".
- **Lançamento em etapas**: o formulário é dividido em cinco etapas curtas
  (Identificação › Partes › Quantidade › Comissões › Embarque), com Voltar/Próximo e o
  resumo do cálculo sempre à vista. **No celular dá para lançar um contrato inteiro com o
  polegar**; no computador as etapas viram abas e você pula direto para a que interessa.
- **Impressão em PDF**: o botão **Imprimir** (na lista e na ficha) abre a folha do contrato
  pronta em uma página A4 e já chama a impressão do navegador — escolha *Salvar como PDF*
  e o arquivo está feito. A folha traz o cabeçalho com o **logotipo e os dados da sua
  empresa**, comprador e vendedor com endereço, documento e **dados bancários/Pix**, a
  mercadoria com **quantidade, peso total e valor por extenso**, a tabela da corretagem
  dos dois lados, embarque e pagamento, suas cláusulas fixas e três campos de assinatura.

Exemplo com números reais de um contrato de café: 330 sacas a R$ 1.320,00 = R$ 435.600,00;
0,50% de cada lado = R$ 2.178,00 do comprador + R$ 2.178,00 do vendedor = **R$ 4.356,00**
de comissão, virando duas contas a receber.

A lista de contratos totaliza valor negociado e comissão do período, com filtros por data,
situação e busca por número, e exporta CSV.

#### ICMS no contrato

Em **Cadastros → ICMS** fica a grade de alíquotas: **UF do vendedor × UF do comprador**, com
produto opcional (em branco = todos os produtos; a linha do produto vale antes da geral).
O botão **Gerar alíquotas interestaduais** cria, a partir de um estado, as 26 linhas de
referência (7% de MG/PR/RJ/RS/SC/SP para N, NE, CO e ES; 12% nas demais) e, se informada, a
alíquota interna. Confirme com o contador: isenção, diferimento e redução de base do café
variam por estado.

No contrato (etapa **Quantidade**) o sistema pega a UF do cadastro do vendedor e do comprador,
busca a alíquota e mostra **ICMS = valor negociado × alíquota**. Dá para digitar outra
alíquota (fica marcada como "digitada") e voltar para a da tabela. O ICMS é **informativo**:
não soma no valor negociado nem muda a corretagem. Aparece no resumo, na ficha e na folha
impressa. O contrato guarda percentual e valor — mudar a tabela depois só afeta o contrato
quando ele for editado. Código: `backend/icms.py`, `backend/routers/icms.py`;
teste: `python testes/teste_icms.py` (com o servidor no ar).

### DF-e — notas fiscais eletrônicas emitidas contra o CNPJ

Em **Movimento → DF-e (notas fiscais)** o sistema busca na SEFAZ, sozinho, todo documento
fiscal emitido contra o CNPJ da empresa — sem depender do contador nem do e-mail do
fornecedor.

**Como fala com a SEFAZ.** Na aba **Certificado digital** a empresa envia o **certificado
A1** (arquivo `.pfx` ou `.p12`) e a senha. O arquivo é conferido na hora (senha, validade e
CNPJ igual ao da empresa) e guardado **cifrado com AES-GCM**, com chave derivada de
`FIN_SECRET_KEY`; nenhuma rota devolve o arquivo nem a senha. Certificado A3 (cartão/token)
não serve — precisa do dispositivo plugado na máquina. Só administradores cadastram ou
removem o certificado.

**Busca.** O botão **Buscar na SEFAZ** chama o webservice nacional **NFeDistribuiçãoDFe**
(`https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe`) usando o certificado como identidade
TLS. A SEFAZ entrega até 50 documentos por consulta, em ordem de **NSU**; o sistema guarda o
último NSU recebido e continua dali na próxima vez. Chegam resumos (`resNFe`), notas
completas (`nfeProc`) e eventos (`resEvento`/`procEventoNFe`) — o evento de cancelamento
marca a nota como cancelada sozinho. Quem recebe o XML por e-mail usa **Enviar XML**.

**Manifestação do destinatário.** Ciência da operação (210210), Confirmação (210200),
Desconhecimento (210220) e Operação não realizada (210240, com justificativa). O evento é
montado já na forma canônica e assinado com o A1 (XMLDSig, SHA-1 + C14N 1.0) — sem
biblioteca de canonicalização: o mesmo texto assinado é o que vai no envelope. A ciência é o
que faz a SEFAZ passar a entregar o **XML completo** da nota.

**DANFE.** `GET /api/dfe/notas/{id}/danfe` devolve a folha da nota pronta para imprimir
(A4, com código de barras Code 128-C da chave desenhado em SVG) — o navegador salva em PDF,
igual à impressão do contrato.

**Importação.** Um clique grava os itens na tabela de itens da nota e as formas de pagamento
e duplicatas na tabela de pagamentos, completa o cadastro do **cliente/fornecedor** do
emitente (IE, endereço, código do município do IBGE) e o dos **produtos** (NCM, CEST, CFOP,
unidade, CST e alíquota) e, se pedido, gera a **conta a pagar** já classificada e
contabilizada, com **uma parcela por duplicata** da nota. Nada é sobrescrito: só o que
estiver em branco é preenchido. Quando o emitente é o próprio CNPJ da empresa, a nota é de
saída e o título gerado é a receber.

Tabelas novas: `certificados_digitais`, `notas`, `nota_itens`, `nota_pagamentos`; campos
fiscais novos em `produtos` e `parceiros`. Código: `backend/dfe.py` (certificado, SEFAZ,
leitura do XML e assinatura), `backend/danfe.py` (folha impressa) e
`backend/routers/dfe.py`; tela em `frontend/js/dfe.js`.
Teste: `python testes/teste_dfe.py` — a parte do motor roda com os XML gravados em
`testes/dados_dfe/` (sem internet e sem SEFAZ).


### Notas Fiscais: faturar, desfaturar e emitir

**Movimento → Notas Fiscais** é a tela de gestão (o DF-e é só a caixa de entrada).

**Faturar** transforma a nota em título: conta a **pagar** na nota de entrada, a **receber**
na nota que a própria empresa emitiu. As parcelas saem das **duplicatas** da nota; sem
duplicata, sai uma parcela só. O título nasce classificado e contabilizado.
**Desfaturar** apaga esse título, estorna as partidas e libera a nota — só no AgroDock, a
nota na SEFAZ não é tocada. Título com baixa não desfatura: primeiro estorne a baixa.
Também dá para faturar **em lote**; o que falhar volta listado com o motivo.
Código: `backend/notas.py` e `backend/routers/notas.py`; teste: `python testes/teste_faturamento.py`.

**Emitir NF-e** (modelo 55) sai da mesma tela. O caminho é rascunho → prévia → transmitir:

- o **rascunho** pode nascer de um contrato de venda (puxa cliente, produto, quantidade e
  preço) ou do zero, e **não gasta numeração** — o número da série só é usado na transmissão,
  e volta para a série se a SEFAZ rejeitar;
- o XML é montado no **layout 4.00** com os dados dos cadastros (NCM, CFOP, CST/CSOSN e
  alíquotas vêm do produto; o regime, CRT, vem da empresa), assinado com o mesmo certificado
  A1 do DF-e e enviado em **lote síncrono** (`indSinc=1`), então a resposta já vem autorizada
  ou rejeitada, sem consultar recibo;
- em **homologação** o sistema troca o nome do destinatário e a descrição do primeiro item
  pelo aviso exigido pela SEFAZ. O ambiente de produção exige confirmação explícita na tela;
- autorizada, a nota guarda o `nfeProc` — é dele que saem a DANFE e o XML do contador, e é
  por ele que a nota entra no faturamento como conta a receber;
- **cancelar** é o evento 110111, com justificativa de 15 letras e dentro do prazo legal.

Os webservices são resolvidos por UF (MG, SP, PR, RS, GO, MT, MS, BA, PE, CE e AM têm
servidor próprio; o resto cai no SVRS). Antes de sair, a nota é barrada por item sem NCM ou
CFOP, cliente sem código do município do IBGE, contribuinte sem inscrição estadual e empresa
sem IE ou sem código do município — com a mensagem dizendo o que corrigir e onde.

> A tributação (CFOP, CST/CSOSN, alíquotas) é responsabilidade do contribuinte e do seu
> contador: o sistema usa o que está nos cadastros e não decide tributação sozinho.
> Comece sempre em homologação.

Código: `backend/emissao.py` (chave, XML, assinatura, transmissão e cancelamento) e
`backend/routers/emissao.py`; tela em `frontend/js/emissao.js`.
Teste: `python testes/teste_emissao.py` — monta e confere o XML inteiro **sem tocar na SEFAZ**.


### Onde pagar cada cliente/fornecedor

Um mesmo parceiro costuma ter mais de uma forma de receber. Na lista de
**Clientes e Fornecedores**, o botão **Pagamento** abre a gestão dessas formas:

- **Pix** com tipo de chave (CPF, CNPJ, e-mail, telefone ou aleatória);
- **Depósito ou TED** com banco, agência, operação (para a Caixa), conta e tipo
  (corrente, poupança ou conta de pagamento);
- **Boleto, dinheiro, cartão ou outro**, para os casos que não se encaixam nos anteriores.

Cada forma aceita titular e CPF/CNPJ próprios — útil quando o pagamento vai para a conta
de um sócio ou de uma filial — além de apelido e observação. Uma delas fica marcada como
**principal**; a primeira cadastrada assume esse papel sozinha, e trocar é um clique.
Formas já usadas em pagamentos não podem ser excluídas, só desativadas, para não perder
o histórico.

Na hora de **dar baixa num título**, o sistema mostra as contas daquele parceiro logo no
topo da tela, com a principal já selecionada e um botão **Copiar** que joga a chave Pix
ou o bloco com banco, agência e conta na área de transferência. A forma escolhida fica
registrada na baixa e aparece depois no histórico do título ("via 341 Itaú · Ag 1234 ·
C/C 56789-0"). A lista de clientes/fornecedores ganhou a coluna **Onde pagar**, mostrando
a forma principal e quantas outras existem.

### Busca automática de CNPJ e CEP

Dois atalhos que evitam digitação e erro de cadastro:

- **CNPJ** no cadastro de cliente/fornecedor — preenche a empresa inteira.
- **CEP** no cadastro de cliente/fornecedor e de empresa — preenche logradouro, bairro,
  cidade e UF, e já leva o cursor para o número. Além do botão **Buscar**, a consulta
  acontece sozinha ao sair do campo quando o logradouro ainda está vazio.

#### CNPJ na API do governo

No cadastro de cliente/fornecedor, digite o CNPJ e clique em **Buscar**: o sistema
preenche razão social, nome fantasia, endereço completo, telefone e e-mail, e mostra a
situação cadastral, a natureza jurídica, a atividade principal e os sócios.

Provedores (em **Config. do site → Consulta de CNPJ**):

| Provedor | Quando usar |
|---|---|
| `CONECTA_GOV` | API oficial do governo (SERPRO / Conecta gov.br). Exige consumer key, consumer secret e o CPF do usuário autorizado |
| `BRASILAPI` | Base pública da Receita Federal, sem credencial — funciona de imediato |
| `AUTO` (padrão) | Usa o Conecta Gov quando há credenciais; senão, a base pública |
| `DESATIVADO` | Esconde o botão de busca |

Endpoints do Conecta Gov usados, conforme a opção **tipo de consulta**:

```
/api-cnpj-basica/v2/basica/{cnpj}     dados cadastrais
/api-cnpj-qsa/v2/qsa/{cnpj}           quadro de sócios e administradores
/api-cnpj-empresa/v2/empresa/{cnpj}   cadastrais + sócios numa chamada só
```

A autenticação é OAuth2 `client_credentials`: o sistema pega o token em
`/oauth2/jwt-token` e o reaproveita até expirar. Com o tipo `basica`, o quadro de sócios
é buscado numa segunda chamada (pode ser desligado em `cnpj_incluir_socios`).
O CNPJ é validado pelos dígitos verificadores antes de consumir uma consulta.

#### CEP nos Correios

Provedores (em **Config. do site → Consulta de CEP**):

| Provedor | Quando usar |
|---|---|
| `CORREIOS` | API oficial (`api.correios.com.br`). Exige contrato: usuário e senha do Meu Correios + número do cartão de postagem |
| `VIACEP` | Base pública dos Correios, sem credencial — funciona de imediato |
| `BRASILAPI` | Consulta vários provedores, inclusive os Correios |
| `AUTO` (padrão) | Usa os Correios quando há contrato; senão, o ViaCEP |
| `DESATIVADO` | Esconde o botão de busca |

Na API oficial o sistema autentica em `/token/v1/autentica/cartaopostagem` (Basic com
usuário e senha, número do cartão no corpo), guarda o token e consulta
`/cep/v2/enderecos/{cep}`.

### Lançamentos

- **Simples** — uma classificação e uma parcela. Opção de baixa imediata (à vista).
- **Múltiplo** — rateio do valor entre várias contas contábeis / centros de custo /
  operações, e parcelamento em quantas parcelas quiser (mensal ou a cada N dias).
- Validação automática: a soma do rateio e das parcelas precisa bater com o valor do título.

### Contas a receber / a pagar

- Filtros por situação, período de vencimento, cliente/fornecedor e texto livre.
- Baixa individual com **juros, multa e desconto**, ou **baixa em lote**.
- Baixa parcial (a parcela fica com status *Parcial* e mantém o saldo).
- Estorno de baixa desfaz o movimento no caixa e a contabilização.
- Indicadores de vencidos, vencendo hoje e saldo em aberto.

### Caixa e bancos

- Saldo de cada conta e saldo consolidado.
- Extrato com saldo acumulado linha a linha.
- Movimentos avulsos de entrada e saída (tarifas, aportes, resgates).
- Transferência entre contas, gerando os dois lados do movimento.

### No celular

O sistema inteiro é responsivo — não existe versão separada, é a mesma tela se ajustando:

- o menu vira uma **gaveta** que abre no botão ☰ e fecha ao escolher a tela;
- cada linha das listas vira um **cartão**, com o nome da coluna ao lado do valor —
  nada de rolar a tabela para o lado procurando a coluna;
- filtros, indicadores e botões se empilham, e os campos ficam no tamanho do dedo
  (sem aquele zoom automático do iPhone ao tocar num campo);
- o formulário do contrato vem **em etapas**, uma tela de cada vez;
- relatórios em matriz (DRE, balancete, razão) encolhem a fonte e continuam tabela.

### Relatórios

| Relatório | Conteúdo |
|---|---|
| **DRE** | Receita bruta, deduções, custos, despesas por grupo, resultado financeiro e resultado líquido, com % sobre a receita, detalhamento por conta e comparação com o período anterior |
| **Balancete de verificação** | Saldo anterior, débitos, créditos e saldo atual por conta, com sintéticas totalizadas e conferência de fechamento |
| **Contas a receber / a pagar** | Analítico por vencimento, emissão, competência ou pagamento, com *aging* (a vencer, 1–30, 31–60, 61–90, +90 dias) |
| **Fluxo de caixa** | Entradas, saídas, resultado e saldo por dia ou mês, com projeção dos títulos em aberto |
| **Contratos × financeiro** | Em que pé está cada contrato: comissão combinada, quanto virou título, quanto já entrou, quanto falta, o que venceu e há quantos dias — com resumo por situação, comprador, representante, produto ou mês |
| **Por centro de custo** | Receitas, despesas e resultado de cada centro |
| **Por conta contábil** | Movimento de cada conta de resultado |
| **Por operação** | Quanto cada natureza de movimento representa |
| **Por cliente/fornecedor** | Quanto cada parceiro gerou de receita ou despesa |
| **Razão contábil** | Lançamentos de uma conta com contrapartida e saldo acumulado |

Todos os relatórios exportam **CSV** e têm layout próprio de impressão.

---

## 3. Como a contabilidade funciona

Cada evento financeiro grava automaticamente uma **partida dobrada** na tabela
`partidas`. O balancete e o DRE são calculados só a partir dela — por isso os
débitos e créditos sempre fecham.

| Evento | Débito | Crédito |
|---|---|---|
| Título a receber | Clientes a Receber | Conta de receita (por item de rateio) |
| Título a pagar | Conta de despesa/custo (por item) | Fornecedores a Pagar |
| Recebimento | Banco / Descontos concedidos | Clientes a Receber / Juros recebidos |
| Pagamento | Fornecedores a Pagar / Juros e multas pagos | Banco / Descontos obtidos |
| Entrada avulsa no caixa | Banco | Conta contábil informada |
| Saída avulsa do caixa | Conta contábil informada | Banco |
| Transferência | Banco de destino | Banco de origem |
| Saldo inicial de conta | Conta do banco | Saldos de Abertura |

O **DRE** usa a data de **competência** (pode ser trocado para regime de caixa no filtro);
o **balancete** e o **fluxo de caixa** usam a data do movimento.

As contas usadas nessas contrapartidas ficam em **Cadastros → Parâmetros contábeis** e podem
ser trocadas a qualquer momento.

---

## 4. Estrutura do projeto

```
sistema-financeiro/
├── iniciar.sh / iniciar.bat     Scripts de inicialização (banco no próprio PC)
├── iniciar-nuvem.bat            Inicia o sistema no PC usando o banco da nuvem
├── app.py / vercel.json         Publicação no Vercel (porta de entrada e configuração)
├── publicar.bat                 Publica a versão nova (GitHub → Vercel) com dois cliques
├── .python-version / .vercelignore  Versão do Python e o que não sobe para o Vercel
├── render.yaml                  Receita da publicação no Render (caminho alternativo)
├── requirements.txt
├── dados/financeiro.db          Banco de dados local (criado na primeira execução)
├── backend/
│   ├── main.py                  Aplicação FastAPI
│   ├── config.py                Configurações (banco, chave, porta)
│   ├── database.py              Conexão e sessão
│   ├── models.py                Tabelas do banco
│   ├── schemas.py               Validação das requisições
│   ├── security.py              Hash de senha e token de sessão
│   ├── contabil.py              Motor de partidas dobradas
│   ├── plano_contas.py          Plano de contas e cadastros padrão
│   ├── relatorios_dre.py        Estrutura do DRE
│   ├── assinaturas.py           Planos, assinatura, configurações e Pix
│   ├── consulta_cnpj.py         Consulta de CNPJ na API do governo
│   ├── consulta_cep.py          Consulta de CEP nos Correios
│   ├── externo.py               Chamadas HTTP às APIs externas
│   ├── dfe.py                   Certificado A1, NFeDistribuiçãoDFe e manifestação
│   ├── danfe.py                 Folha da nota fiscal (DANFE) pronta para imprimir
│   ├── notas.py                 Regras das notas: importar o XML, faturar e desfaturar
│   ├── emissao.py               NF-e 4.00: chave, XML, assinatura e webservices por UF
│   ├── migracao.py              Atualização automática do banco
│   ├── diagnostico.py           Página que explica por que o sistema não ligou
│   ├── seed.py                  Dados iniciais
│   └── routers/
│       ├── publico.py           Site: informações, planos e auto-cadastro
│       ├── auth.py              Login
│       ├── assinatura.py        Pagamento, confirmação e administração das contas
│       ├── consulta.py          Buscas de CNPJ e CEP usadas pelos cadastros
│       ├── contratos.py         Contratos de intermediação e geração de recebíveis
│       ├── dfe.py               DF-e: certificado, busca na SEFAZ, DANFE e importação
│       ├── notas.py             Notas fiscais: gestão, faturar e desfaturar
│       ├── emissao.py           Emissão de NF-e: rascunho, transmissão e cancelamento
│       ├── cadastros.py         Todos os cadastros
│       ├── lancamentos.py       Títulos, parcelas e baixas
│       ├── caixa.py             Extrato, movimentos e transferências
│       └── relatorios.py        Relatórios, DRE, balancete e painel
├── frontend/
│   ├── index.html
│   ├── styles.css
│   ├── img/                     logotipo do AgroDock, ícone e favicon
│   └── js/                      api, ui, site, cadastros, lancamentos, caixa, impressao,
│                                contratos, dfe, mercado, relatorios, assinaturas, app
├── deploy/                      publicação: nuvem (Neon + Vercel) e servidor Ubuntu
│   ├── migrar_para_postgres.py  Leva os dados do PC para a nuvem — e traz de volta
│   ├── subir-para-nuvem.bat     Atalho do Windows para a primeira carga
│   ├── baixar-da-nuvem.bat      Atalho do Windows para o backup da nuvem
│   ├── nuvem-exemplo.txt        Modelo do arquivo com o endereço do banco
│   ├── instalar.sh              Servidor próprio: Ubuntu + Nginx + systemd
│   ├── atualizar.sh             Servidor próprio: aplicar uma versão nova
│   └── backup.sh                Servidor próprio: backup diário do banco
└── testes/
    ├── teste_completo.py        Teste ponta a ponta da API financeira
    ├── teste_assinatura.py      Teste do cadastro, bloqueio e liberação por Pix
    ├── teste_cnpj.py            Teste da consulta de CNPJ (com API do governo simulada)
    ├── teste_cep.py             Teste da consulta de CEP (com Correios simulado)
    ├── teste_formas_pagamento.py Teste das contas/chaves Pix por cliente/fornecedor
    ├── teste_contratos.py       Teste do contrato de corretagem e dos recebíveis gerados
    ├── teste_cadastros.py       Teste dos cadastros, numeração automática e limite de usuários
    ├── teste_dfe.py             Teste do DF-e (XML gravados, sem internet) e da importação
    ├── teste_faturamento.py     Teste de faturar e desfaturar a nota
    ├── teste_emissao.py         Teste da emissão de NF-e (sem tocar na SEFAZ)
    ├── teste_impressao.py       Teste da folha do contrato e geração do PDF
    ├── teste_status_contrato.py Teste do ciclo Aberto → Recebido Total e do relatório
    ├── teste_postgres.py        Teste do sistema rodando com o banco na nuvem
    ├── teste_celular.py         Teste da interface no celular (390x844)
    └── teste_interface.py       Teste do site e das telas (Playwright)
```

A documentação interativa da API fica em **http://localhost:8000/docs**.

---

## 5. Testes

Com o servidor rodando em outra janela:

```bash
python testes/teste_completo.py     # fluxo financeiro + conferência do balancete
python testes/teste_assinatura.py   # cadastro, teste de 48h, bloqueio, Pix e liberação
python testes/teste_cnpj.py         # consulta de CNPJ contra um Conecta Gov simulado
python testes/teste_cep.py          # consulta de CEP contra os Correios simulados
python testes/teste_formas_pagamento.py   # contas e chaves Pix por parceiro e uso na baixa
python testes/teste_contratos.py    # contrato de corretagem, comissões e contas a receber
python testes/teste_compra_venda.py # compra e venda de café, agente e títulos gerados
python testes/teste_icms.py         # tabela de ICMS e o ICMS calculado no contrato
python testes/teste_dfe.py          # DF-e: certificado, XML, DANFE, manifestação e importação
python testes/teste_faturamento.py  # faturar e desfaturar a nota (título, parcelas, estorno)
python testes/teste_emissao.py      # emissão de NF-e: chave, XML 4.00, assinatura e retornos
python testes/teste_cadastros.py    # unidades, modalidades, produtos, nº automático e usuários
python testes/teste_impressao.py    # folha do contrato e PDF (sai em testes/capturas/contrato.pdf)
python testes/teste_status_contrato.py  # ciclo de vida do contrato e relatório de contratos
python testes/teste_celular.py      # tela de 390x844: menu, listas em cartões e contrato por etapas
python testes/teste_interface.py    # site e telas no navegador (precisa de playwright)
# por último (desliga o login de fábrica); servidor e teste com a mesma FIN_MASTER_EMAIL:
python testes/teste_empresas_acesso.py  # administrador, liberar/bloquear por data e limites
```

Sem precisar de servidor:

```bash
python testes/teste_cotacoes.py     # faixa de cotações, com respostas gravadas
python testes/teste_mercado.py      # painel Mercado do Café, com respostas gravadas
python testes/teste_migracao.py     # atualização de um banco antigo para o formato novo
```

Com o banco na nuvem (o servidor precisa estar apontando para o mesmo endereço):

```bash
FIN_DATABASE_URL="postgresql://..." python testes/teste_postgres.py
```

Esse último confere o que muda quando o banco não é mais o arquivo do PC: numeração
automática continuando de onde parou, sim/não, datas e centavos voltando certos,
relatórios somando igual e — o mais importante — o sistema **reconectando sozinho**
depois que o banco derruba a conexão por falta de uso.

O teste financeiro cria uma empresa de exemplo, lança títulos simples e múltiplos, faz
baixas com juros e desconto, movimenta o caixa e confere se o **saldo bate**, se o
**balancete fecha** e se o **DRE apura o resultado correto**.

O teste de assinatura cadastra dois clientes pelo site, usa o sistema durante o teste,
força o fim das 48 horas, confere que o acesso é **bloqueado**, informa o Pix, confirma
o recebimento e verifica que o acesso volta **com os dados intactos** — além de checar
que um assinante não consegue ler nem gravar dados de outro.

---

## 6. Colocar no ar

Há dois caminhos. O primeiro não exige servidor nenhum e é o recomendado.

### 6.1. Na nuvem, sem servidor (banco Neon + site Vercel) — recomendado

O banco deixa de ser um arquivo no computador e passa a ser um **PostgreSQL
gerenciado** no Neon; o sistema roda no Vercel. O mesmo dado aparece no PC e
no celular, e nada muda no jeito de usar: é a mesma tela, os mesmos contratos.

| Onde | O que fica lá | Plano grátis |
|---|---|---|
| [Neon](https://neon.com) | o banco de dados (todos os seus dados) | **sem prazo para acabar**; 0,5 GB e 100 horas de computação por mês; desliga sozinho após 5 min parado e **religa sozinho** no próximo acesso (menos de 1 segundo) |
| [Vercel](https://vercel.com) | o site/sistema | não dorme; plano Hobby é **só para uso pessoal, não comercial** |

> **Por que Neon e não Supabase:** o Supabase grátis também não expira, mas
> **pausa o banco depois de 7 dias sem acesso** e só volta clicando em *Restore*
> no painel. O Neon nunca fica parado esperando alguém: acorda sozinho.
>
> **Atenção ao cobrar assinantes:** os termos do plano Hobby do Vercel proíbem
> uso comercial. Quando o AgroDock tiver clientes pagando, o certo é o Pro
> (US$ 20/mês).

Passo a passo resumido:

1. **Neon** → criar conta → *Create project* → região **AWS South America (São Paulo)**.
   Depois, botão **Connect** → ligar **Connection pooling** → copiar o endereço
   (`postgresql://neondb_owner:SENHA@ep-xxxx-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require`).
   Confira que tem **`-pooler`** no nome do servidor.
2. **Levar os dados que já existem no PC** (pule se estiver começando do zero):

   ```bash
   python deploy/migrar_para_postgres.py "postgresql://neondb_owner:SENHA@ep-xxxx-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"
   ```

   No Windows dá para usar o atalho `deploy\subir-para-nuvem.bat`, depois de salvar
   o endereço em `deploy/nuvem.txt` (veja `deploy/nuvem-exemplo.txt`).
   Faça isto **antes** de abrir o site pela primeira vez.
3. **GitHub** → subir esta pasta para um repositório (o `.gitignore` e o
   `.vercelignore` já impedem que banco, senhas e o ambiente Python vão junto).
4. **Vercel** → *Add New → Project* → importar o repositório. Ele reconhece sozinho
   (FastAPI, arquivos `app.py` e `vercel.json`). Antes de *Deploy*, abrir
   **Environment Variables** e cadastrar:

   | Nome | Valor |
   |---|---|
   | `FIN_DATABASE_URL` | o endereço do Neon (passo 1) |
   | `FIN_SECRET_KEY` | uma frase longa e secreta qualquer (assina os logins) |

5. Pronto — o endereço `https://<nome>.vercel.app` abre no celular e no PC. Cada
   `git push` no GitHub publica a versão nova sozinho.

O que o código faz para funcionar bem nessa dupla:

- `app.py` (raiz) é a porta de entrada que o Vercel procura; `vercel.json` põe o
  sistema em São Paulo (`gru1`, perto do banco) e deixa testes e scripts fora do pacote;
- a conexão desliga os *prepared statements* (`prepare_threshold=None`), exigência de
  poolers em modo transação (o do Neon e o do Supabase), testa a conexão antes de usar
  e reconecta sozinha quando o Neon desliga por falta de uso;
- sem `FIN_DATABASE_URL` ou sem `FIN_SECRET_KEY`, o sistema **se recusa a subir** no
  Vercel com uma mensagem clara (em vez de gravar num arquivo temporário e perder tudo);
- a conferência das tabelas roda só quando o código muda: fica guardada uma
  "impressão digital" do esquema na tabela `agrodock_meta`, então cada cópia nova do
  sistema que o Vercel liga faz uma consulta só. Se duas sobem juntas, uma trava
  (`pg_advisory_xact_lock`) garante que só uma mexe nas tabelas.
- A integração oficial do Neon no Marketplace do Vercel cria a variável
  `POSTGRES_URL` sozinha — o sistema também aceita esse nome.
- Continua funcionando com Supabase (pooler porta 6543), se um dia preferir.

**Publicar uma versão nova:** dois cliques em **`publicar.bat`** (na pasta do projeto).
Ele confere se banco, senha e `.venv` estão fora do envio, confere se o código Python
abre, registra as alterações ("Publicação dd/mm/aaaa hh:mm") e manda para o GitHub — o
Vercel coloca no ar sozinho em 1 a 3 minutos. Precisa do **Git for Windows** instalado
uma vez (https://git-scm.com/download/win); no primeiro envio abre o login do GitHub.

**Se o site não abrir:** em vez do "500 FUNCTION_INVOCATION_FAILED", o AgroDock mostra
uma página dizendo o que falhou (variável faltando, senha do banco errada, endereço
errado…) e o que fazer — sem mostrar a senha. Depois de corrigir no Vercel, **Redeploy**.

Depois de no ar:

```bash
# usar o sistema no PC lendo o mesmo banco do celular
iniciar-nuvem.bat

# trazer uma cópia de segurança da nuvem para a pasta backups/
deploy\baixar-da-nuvem.bat

# conferir se PC e nuvem estão iguais
python deploy/migrar_para_postgres.py "postgresql://..." --conferir
```

> Com o banco desligado por falta de uso, a primeira tela depois de um tempo parado
> leva um instante a mais (o Neon religa em menos de um segundo). As 100 horas
> mensais contam só o tempo ligado — para um escritório usando em horário comercial,
> sobra.
>
> O `render.yaml` continua na pasta para quem preferir o Render no lugar do Vercel.

### 6.2. Servidor próprio (VPS, Oracle Cloud, máquina na empresa)

A pasta `deploy/` tem tudo pronto para um servidor Ubuntu:

```bash
# no servidor, dentro da pasta do AgroDock
sudo bash deploy/instalar.sh                  # acesso pelo IP
sudo bash deploy/instalar.sh meusite.com.br   # com domínio e HTTPS automático
```

O instalador cria o ambiente Python, gera a chave de sessão, registra o serviço no
systemd (sobe junto com o servidor e reinicia sozinho se cair), põe o Nginx na frente,
libera as portas 80 e 443 no firewall do Ubuntu e programa o backup diário do banco.

| Arquivo | Para que serve |
|---|---|
| `deploy/instalar.sh` | Instalação completa. Pode rodar de novo sem medo — não apaga o banco |
| `deploy/atualizar.sh` | Depois de copiar uma versão nova: faz backup, atualiza e reinicia |
| `deploy/backup.sh` | Backup do banco (roda sozinho às 3h; guarda 30 dias em `backups/`) |
| `deploy/agrodock.env` | Gerado na instalação: a chave que assina as sessões. **Não compartilhe** |

Comandos do dia a dia no servidor:

```bash
sudo systemctl status agrodock     # está no ar?
sudo systemctl restart agrodock    # reiniciar
tail -f dados/agrodock.log         # acompanhar
```

Na Oracle Cloud, além disso, é preciso liberar as portas 80 e 443 na **Security List da
VCN** (painel da Oracle) — o instalador cuida só do firewall de dentro do Ubuntu.

Esse servidor também pode usar o banco na nuvem: basta acrescentar a linha
`FIN_DATABASE_URL=postgresql://...` no arquivo `deploy/agrodock.env` e reiniciar.

---

## 7. Segurança e produção

- Antes de expor o sistema fora da sua máquina, defina a variável de ambiente
  `FIN_SECRET_KEY` com uma chave própria e troque a senha do administrador.
- Para receber cadastros pela internet, hospede o sistema num servidor com **HTTPS**
  (por exemplo atrás do Nginx ou Caddy) — o cadastro trafega senha.
- As credenciais das APIs de CNPJ e CEP ficam no banco e só o perfil MASTER as enxerga;
  elas nunca são enviadas para o site público.
- A confirmação do Pix é **manual**, feita por você em Administração → Assinaturas.
  Isso evita depender de integração bancária, mas exige conferir o extrato antes de
  liberar cada conta.
- O banco é escolhido pela variável `FIN_DATABASE_URL`: sem ela, o sistema usa o
  arquivo `dados/financeiro.db`; com ela, usa o PostgreSQL indicado (o endereço pode
  ser colado no formato que o serviço fornecer — `postgres://` ou `postgresql://`).
- Faça backup periódico: `dados/financeiro.db` no PC, ou
  `python deploy/migrar_para_postgres.py "postgresql://..." --baixar` quando o banco
  estiver na nuvem.
