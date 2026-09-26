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
- **Auto-cadastro**: o visitante informa nome, e-mail, senha, empresa e o plano pretendido
  (plano e prazo na mesma escolha).
  A conta é criada já com plano de contas, centros de custo e operações padrão.
- **Teste de 48 horas** liberado na hora, sem cartão. Uma faixa no topo do sistema mostra
  quanto tempo ainda resta.
- **Pagamento por Pix** dentro do sistema: QR Code, chave e código copia e cola gerados
  com o valor do plano escolhido (padrão EMV do Banco Central) e um identificador por conta.
- **Cupom de desconto**: o cliente digita o código no cadastro ou na tela de pagamento e o
  QR Code e o copia e cola são refeitos com o valor menor.
- Terminadas as 48 horas, a conta é **bloqueada** e cai na tela de pagamento — os dados
  lançados continuam guardados.
- O assinante clica em **“Já fiz o Pix”**; você confere o recebimento e clica em
  **Confirmar Pix**, o que **libera o acesso** pelo prazo do plano (6 ou 12 meses).
- **Cada conta enxerga só o que contratou**: o menu mostra apenas as telas do plano, e o
  servidor recusa o que está fora dele.
- **Isolamento entre contas**: cada assinante enxerga somente as próprias empresas e
  usuários; apenas o perfil MASTER administra o sistema.

#### Os quatro planos

O que muda de um plano para o outro **não é o prazo**: é o que a conta pode usar. Contrato de
assessoria, financeiro inteiro (contas a receber e a pagar, caixa, DRE, balancete e
relatórios) e **emissão de NF-e** estão em todos. O que separa os planos são dois módulos:
**cupom fiscal eletrônico** e **GTA**.

| Plano | Além do miolo | Semestral | Anual |
|---|---|---|---|
| Plano 1 | — | R$ 399,90 | R$ 699,90 |
| Plano 2 | Cupom fiscal | R$ 459,90 | R$ 859,90 |
| Plano 3 | GTA | R$ 519,90 | R$ 969,90 |
| Plano 4 | Cupom fiscal **e** GTA | R$ 579,90 | R$ 1.069,90 |

O código gravado na assinatura carrega as duas escolhas juntas — `P3_ANUAL` é *Plano 3 por 12
meses*. Os oito preços, a duração de cada prazo e as horas de teste são editáveis em
**Config. do site**.

A tabela acima é o **padrão de fábrica**. Quem monta a grade de verdade é você, em dois níveis
— e os dois são exclusivos do seu usuário (MASTER):

**1. Os menus de cada plano** — *Config. do site → Menus de cada plano*. Um quadro com um menu
por linha e um plano por coluna: marcar o cupom no Plano 1 abre o cupom para **todos** os
assinantes do Plano 1 na hora, e a apresentação do plano na página inicial muda junto. Plano
sem nenhum menu marcado é aceito (a conta entra e só enxerga Cadastros e Minha Assinatura).

**2. A exceção de um cliente** — *Assinaturas → Gerenciar → Acessos combinados*. É a
negociação: o cliente fechou o **Plano 1** mas ficou combinado dar a **nota fiscal**, então
você marca a nota fiscal só para ele. O plano e o valor cobrado continuam os mesmos, e o
vizinho de plano não ganha nada. O caminho contrário — tirar da conta um menu que o plano dá —
é a mesma tela, desmarcando. A coluna *de onde vem* diz, linha por linha, se aquele acesso veio
do plano ou de uma combinação.

Guardado assim: a grade de cada plano fica nas configurações do site (`plano1_modulos`…), a
exceção fica na própria assinatura (`modulos_extras` e `modulos_bloqueados`), e quem junta as
duas pontas é `assinaturas.modulos_da_assinatura`. Trocar o cliente de plano recalcula as
exceções contra o plano novo, então quem sobe de plano não fica com "extra" do que o plano
novo já dá.

#### Cupons de desconto

Não confundir com o **cupom fiscal** (NFC-e): aqui é o desconto de venda. Em **Administração
→ Cupons de desconto** (só o seu usuário) você cria um código e uma porcentagem — por exemplo
`PRIMAVERA10`, 10% — e liga ou desliga quando quiser. Não tem validade nem limite de uso: o
que vale é estar ligado.

O cliente digita o código em dois lugares: no **cadastro**, ao escolher o plano (a tela já
mostra quanto ele vai pagar antes de criar a conta), e na **tela de pagamento**, para quem
recebeu o cupom depois. Em qualquer um dos dois o **Pix é refeito**: o copia e cola e o QR
Code passam a carregar o valor com desconto, porque os dois são montados a partir do mesmo
valor de cobrança.

Três coisas que o desconto respeita:

- vale na **primeira cobrança**. Quando você clica em *Confirmar Pix*, o cupom é gasto: some
  da conta, o contador de usos sobe e a renovação volta ao preço cheio. Fica registrado qual
  cupom pagou a entrada daquela conta e quanto abateu;
- **pacote de usuários extra não tem desconto** — o cupom é do plano;
- a porcentagem fica **copiada na assinatura** no momento em que o cliente aplica. Se depois
  você mudar o cupom de 10% para 5%, ou apagar o cupom, quem já aplicou continua com o que foi
  combinado.

Código errado ou cupom desligado dão a **mesma** resposta ("cupom não encontrado ou não está
mais valendo"), de propósito: quem está do lado de fora não descobre que o cupom existe e foi
desligado. Cupom errado digitado no cadastro não derruba a conta — ela é criada e o aviso vai
junto.

Código: `backend/descontos.py` (as regras), `Assinatura.cupom_*` e `CupomDesconto` em
`backend/models.py`, as rotas em `backend/routers/assinatura.py` e `publico.py`, e as telas em
`frontend/js/assinaturas.js` e `site.js`.
Teste: `python testes/teste_cupons.py` (lê o valor de dentro do payload Pix, não do JSON).

#### Como o sistema respeita o plano

Cada plano tem uma lista de **módulos**; cada módulo, uma lista de **rotas** do menu. Daí saem
duas barreiras, e as duas são necessárias:

- no **servidor**, a dependência `exigir_modulo` recusa a chamada com a frase dizendo em que
  planos aquilo está (`Cupom fiscal eletrônico não faz parte do seu plano. Está no Plano 2 e
  Plano 4.`) — esconder botão não é segurança, quem souber o endereço chama a rota do mesmo
  jeito. Todos os cinco módulos têm essa porta, inclusive contrato, financeiro e NF-e: agora
  que a grade é editável, qualquer um deles pode ser tirado de um plano ou de um cliente;
- na **tela**, o menu não mostra o que a conta não tem, e endereço digitado à mão cai no
  painel com o aviso. A lista de rotas liberadas vem do servidor junto com a situação da
  assinatura, então trocar de plano redesenha o menu na hora.

Contas de antes dos planos separados (plano gravado como `SEMESTRAL` ou `ANUAL`) contrataram o
sistema do jeito que ele era: valem como **Plano 4**, e ninguém perde nada na atualização.

Código: `backend/planos.py` (o catálogo: módulos, níveis, preços e rotas), `exigir_modulo` em
`backend/deps.py` e o menu em `frontend/js/app.js`.
Teste: `python testes/teste_planos.py`.

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
| **Produtos** | O que é negociado (café arábica, conilon...), já com unidade, embalagem, **preço de venda** e **classificação** |
| **Categorias** | Que tipo de coisa é o produto: Café, Grãos, Pecuária, Insumos, Embalagens |
| **Marcas** | A marca comercial do produto; a granel, fica "Sem marca" |
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
50 kg, arroba, tonelada, quilo, litro, unidade), **modalidades**, **categorias**, uma
**marca** genérica e **produtos** prontos para usar — e os produtos já nascem classificados.

#### Classificar o produto: categoria e marca

Cada produto tem uma **categoria** (o que ele é) e uma **marca** (de quem ele é), as duas com
código, nome e descrição, as duas por empresa. **Salvar produto sem escolher as duas não
passa** — nem ao criar nem ao editar —, e a mensagem diz onde cadastrar o que falta. Também
não dá para classificar com a categoria de outro assinante: o sistema confere a empresa antes
de gravar.

A classificação serve em três lugares:

- **filtro na lista de produtos** — dois seletores no topo, que se somam com a busca por texto;
  o contador vira "1 de 6 registro(s)" para você saber que está vendo um recorte;
- **filtro no estoque** — ver o saldo só de uma categoria ou de uma marca, com o resumo
  (valor total, negativos, abaixo do mínimo) acompanhando o filtro;
- **relatório Por categoria / Por marca**, em Relatórios: quanto **saiu** no período (dos itens
  das notas de saída autorizadas, pelo preço cobrado) e quanto **sobrou** hoje (pelo custo
  médio). São duas leituras diferentes de propósito — o estoque é a foto de agora, não tem
  período.

Duas escolhas que evitam surpresa: a coluna aceita vazio no banco, então **produto cadastrado
antes disto continua válido** e o produto criado pela **importação de XML** da SEFAZ cai em
*Outros / Sem marca* em vez de travar a importação. E produto sem classificação **não some do
relatório**: aparece em linha própria, para o total bater com o da empresa.

Apagar uma categoria ou marca que tem produto é barrado — o caminho é trocar a classificação
dos produtos ou inativar.

Código: `CategoriaProduto` e `MarcaProduto` em `backend/models.py`, as rotas em
`backend/routers/cadastros.py`, os padrões em `backend/plano_contas.py`, o relatório em
`backend/routers/relatorios.py` e as telas em `frontend/js/cadastros.js`, `estoque.js` e
`relatorios.js`.
Teste: `python testes/teste_classificacao.py`.

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

Na lista, toda nota que tem XML guardado ganha o botão **XML**, que baixa o arquivo
direto — sem abrir a nota. É o arquivo inteiro (`nfeProc` nas emitidas), com o nome da
chave de acesso, que é o que o contador pede. Nota que veio só como resumo da SEFAZ não
tem XML e por isso não mostra o botão.

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

### Pedido de venda e orçamento (tela de balcão)

**Movimento → Pedidos e Vendas** é a tela de PDV: **categorias à esquerda, produtos no meio,
carrinho à direita**. Quem atende não digita código nem procura em lista — clica na categoria,
clica no produto, e o item entra no carrinho. Clicar de novo no mesmo produto soma quantidade
em vez de repetir a linha.

O preço que aparece no cartão do produto é o **Preço de venda** do cadastro (campo novo em
Cadastros → Produtos). Dá para mudar o valor do item na hora da venda; o cadastro é só o
padrão.

O documento nasce como **orçamento** ou como **pedido**, com número sequencial por empresa, e
fica guardado: dá para reabrir, editar e finalizar depois. Orçamento e pedido **dividem a mesma
sequência**, porque o orçamento aprovado vira pedido com o **mesmo número** — o cliente continua
falando do mesmo papel. Orçamento não vira venda direto: tem de ser aprovado antes.

#### Finalizar: uma tela só para decidir como recebe

Um botão só, **FINALIZAR**, que abre a segunda tela. Separar as duas coisas é proposital:
montar a venda e decidir como recebe são momentos diferentes, e misturá-los é o que faz o
operador errar a forma de pagamento com o cliente esperando.

**1. Como o cliente paga** — à vista ou a prazo. No a prazo: quantas parcelas, o primeiro
vencimento e o intervalo (mensal, quinzenal, semanal). A tela mostra as parcelas **antes de
confirmar**, e essa conta vem do servidor de propósito: o que aparece na tela é exatamente o
que vai virar duplicata e conta a receber, centavo por centavo.

A divisão arredonda em centavos e **joga a sobra na primeira parcela** (100,00 em 3x = 33,34 +
33,33 + 33,33). O vencimento mensal anda de **mês em mês**, não de 30 em 30 dias: 31/01 vence
em 28/02 e 31/03, não em 02/03.

**2. Que documento sai** — **nota fiscal (NF-e 55)** ou **cupom fiscal (NFC-e 65)**. A NF-e
exige o cliente cadastrado; o cupom aceita consumidor não identificado, e a tela diz isso
quando falta. Em produção, a confirmação explícita continua valendo, igual às outras telas.

Fechada a venda: **a prazo** gera a conta a receber com as parcelas, pelo mesmo `faturar` que
o sistema já usava nas notas; **à vista** não gera título nenhum, porque o dinheiro já entrou.

#### O que a finalização reaproveita — e o que ela protege

A finalização **não reimplementa** emissão nem financeiro: ela monta a entrada das rotas que já
existiam e as chama (`criar_rascunho` + `transmitir` para a NF-e, a venda do cupom para o 65, o
`faturar` de sempre para o título). O pedido guarda o id da nota e do título, que é o rastro de
onde ele foi parar.

E **se a SEFAZ recusar, a venda não se perde**: o pedido continua aberto, com o motivo na tela,
e dá para corrigir e finalizar de novo. Perder uma venda montada porque o certificado venceu
seria o pior jeito de descobrir isso.

O desconto do total é **rateado entre os itens** na hora de virar nota, porque a NF-e não tem
"desconto do total" — cada item leva o seu, e a soma fecha com o valor do pedido.

A tela de **Cupom Fiscal** continua existindo, para quem quer a venda numa chamada só sem
guardar pedido.

Código: `backend/pedidos.py` (numeração, totais e a conta das parcelas),
`backend/routers/pedidos.py`, `Pedido`/`PedidoItem` em `backend/models.py` e a tela em
`frontend/js/pedidos.js`.
Teste: `python testes/teste_pedidos.py`.

### Cupom fiscal (NFC-e, modelo 65)

**Movimento → Cupom Fiscal** é a venda de balcão: escolhe o produto, a quantidade, a forma
de pagamento e pronto — uma tela só, e o cupom sai impresso. É o oposto da NF-e, que é
montada com calma em cinco etapas: no balcão o consumidor está esperando, então a venda é
**uma chamada só** ao servidor, que cria e transmite de uma vez.

Por dentro a NFC-e é a mesma NF-e 4.00 — mesmos itens, mesmos impostos (as regras fiscais
valem igual), mesma assinatura, mesmo lote síncrono. O que muda:

- `mod` 65, `tpImp` 4 (o cupom estreito), `indPres` 1 e `indFinal` 1: é venda **presencial a
  consumidor final**;
- `idDest` 1 — **só dentro do estado**. Para outro estado, ou para empresa que vai revender e
  creditar ICMS, tem de ser NF-e 55; o cupom não resolve;
- o **destinatário é opcional**: a maioria dos cupons sai sem identificar ninguém. Quem pede
  "CPF na nota" informa só o documento, sem endereço e sem cadastro de cliente;
- não leva transporte nem duplicatas, e o **troco** entra no grupo de pagamento;
- os **webservices são outros** — em Minas, `nfce.fazenda.mg.gov.br`, não `nfe.`; e são de
  cada estado (veja *Em que estados o cupom sai*, abaixo);
- a **numeração é separada** da nota fiscal: modelos diferentes, sequências diferentes.

#### O CSC e o QR Code

O cupom impresso leva um **QR Code** que o consumidor lê para conferir a venda no site da
SEFAZ. Ele é assinado com o **CSC** (Código de Segurança do Contribuinte), um código que a
empresa pede no portal da SEFAZ do estado — em Minas, no SIARE; em São Paulo e Goiás, na área do contribuinte do portal da NFC-e. **Sem CSC nenhum cupom é
aceito**, e por isso a tela avisa antes de a pessoa montar a venda.

O texto do QR Code (versão 2.0, emissão on-line) é::

    <URL da SEFAZ>?p=<chave>|2|<ambiente>|<idToken>|<hash>
    hash = SHA1("<chave>|2|<ambiente>|<idToken>" + CSC)   em hexadecimal maiúsculo

O CSC entra **só no cálculo** — nunca no XML, nunca na tela. É ele que prova que o cupom é
verdadeiro, então fica cifrado no banco (AES-GCM, igual ao certificado) e nenhuma rota o
devolve. Cada ambiente tem o seu: o CSC de homologação não funciona em produção, e os dois
ficam guardados separados. O teste refaz o hash por conta própria e compara — se o cálculo
mudar, o teste acusa.

#### O cupom impresso

A folha sai em **80 mm**, do tamanho da bobina, com o que a SEFAZ exige: identificação do
emitente, o aviso "DANFE NFC-e", os itens, o total, as formas de pagamento e o troco, o
consumidor (ou "CONSUMIDOR NAO IDENTIFICADO"), a chave de acesso para digitar, o QR Code e o
protocolo. Imprimir é o botão do próprio navegador — o mesmo caminho da DANFE e do contrato.

O cancelamento usa o mesmo evento 110111 da nota, mas o **prazo é de cada estado**: 30 minutos
em Minas, 24 horas no Tocantins. Passado isso, a saída é uma devolução. A tela diz se ainda dá
tempo, com o prazo do estado da empresa.

#### Em que estados o cupom sai

De fábrica: **Minas Gerais, São Paulo e Goiás**. O **Tocantins** vem com a autorização pronta
(pelo SVRS, confirmado pela própria SEFAZ-TO: o estado não tem servidor próprio de NFC-e) e
precisa só das duas URLs do portal do estado — QR Code e consulta pela chave. O site da
SEFAZ-TO bloqueia leitura automática, então esses dois não dá para trazer prontos; cada cartão
da tela diz **onde copiar** cada endereço.

A NFC-e segue o **padrão nacional do ENCAT** (MOC e anexos, no Portal Nacional da NF-e), não um
manual de cada estado: o que muda por UF são os endereços. A transmissão já é **síncrona**
(`indSinc=1`), como o cupom exige. O que o sistema **ainda não faz** é a **contingência
off-line** do Anexo IV — sem internet, o cupom não sai. Para um balcão que perde conexão, é a
próxima coisa a construir.

A **NF-e (modelo 55) não tem essa limitação**: São Paulo, Goiás, Minas e mais nove estados têm
endereço próprio na tabela de `backend/emissao.py`, e todos os outros — o Tocantins entre eles —
caem no **SVRS**, que é quem autoriza para eles. Quem emite NF-e emite em qualquer estado.

**Por que os endereços do cupom são editáveis.** Eles mudam: Goiás trocou a URL do QR Code da
NFC-e em 2025 (Informe Técnico 2025.003, de `http` para `https`, com host novo). Quando um
endereço chumbado no código sai de circulação, o cupom do cliente para de sair no balcão e ele
fica esperando uma versão nova do sistema. Então o código traz o **padrão de fábrica** e quem
manda é o que estiver gravado: em **Administração → Endereços da SEFAZ** (só o MASTER) há um
cartão por estado, com os oito endereços (autorização, evento, QR Code e consulta, em produção
e homologação), o prazo de cancelamento, de onde veio cada valor e um botão de voltar ao
padrão. Campo salvo igual ao padrão não é gravado — assim o estado volta a acompanhar as
atualizações do sistema sozinho.

**Conferir antes da primeira venda.** Cada estado ligado tem o botão **Conferir o QR Code**:
ele monta o texto que vai dentro do QR Code, em produção e em homologação, com uma chave e um
CSC de exemplo. Dá para comparar o começo da linha com um cupom de verdade daquele estado antes
de vender — endereço errado aparece ali, e não na frente do cliente.

**Endereço em branco não vira palpite.** Sem a URL do QR Code o sistema **recusa emitir**
naquele estado, com a frase dizendo qual serviço falta e onde preencher. É de propósito: um
endereço chutado faz a SEFAZ devolver a **rejeição 395**, ou — pior — autoriza um cupom cujo
QR Code o consumidor não consegue conferir. A origem de cada padrão fica escrita na tela,
porque a confiança não é a mesma: São Paulo foi conferido no portal da SEFAZ-SP, os endereços
do SVRS no portal do SVRS, e o QR Code de Goiás veio do Informe Técnico 2025.003 por fonte
secundária — **confira no portal da SEFAZ-GO antes de usar em produção**. O jeito certo de
conferir qualquer um deles é emitir em **homologação** primeiro.

Código: `backend/cupom.py` (QR Code e CSC), `backend/sefaz_enderecos.py` (a tabela por estado),
`backend/danfe_cupom.py` (a folha), `backend/routers/cupom.py` e as telas em
`frontend/js/cupom.js` e `frontend/js/assinaturas.js`.
Teste: `python testes/teste_cupom.py` — valida o XML no schema oficial e confere o QR Code;
`python testes/teste_cupom_estados.py` — o QR Code de cada estado, a recusa quando falta
endereço e a edição pela tela.

#### Mandar a nota para o cliente por e-mail

Autorizada, a nota **sai sozinha por e-mail** para o cliente, com dois anexos: o **XML**
(o documento fiscal, que o contador escritura) e a **DANFE em PDF** (a folha de conferir e
imprimir). O PDF é desenhado no layout oficial a partir do próprio XML autorizado, pela
biblioteca `brazilfiscalreport` — Python puro, então funciona igual no PC e no servidor,
sem navegador e sem nada instalado.

Quem envia é a **conta de e-mail da própria empresa** (*Cadastros → E-mail*, ou o botão
*Configurar e-mail* na linha da empresa): o sistema só conversa com o servidor SMTP dela.
A aba **E-mail** mostra numa olhada se o envio está de pé, por qual endereço sai e qual foi
o último erro. Assim o cliente vê a nota vindo
da empresa e responde para ela. A tela tem servidores prontos para Gmail, Microsoft e
domínio próprio, e um **e-mail de teste** — que é a única forma honesta de saber se a senha
está certa antes da primeira nota. Gmail e Microsoft exigem **senha de app**; quando o
servidor recusa a senha, a mensagem de erro já diz isso.

A **senha fica cifrada** no banco (AES-GCM com chave derivada de FIN_SECRET_KEY, igual ao
certificado digital) e **nenhuma rota a devolve**: a tela mostra apenas se existe senha
guardada. Salvar com o campo em branco mantém a que já estava.

Se a DANFE não puder ser desenhada, **o XML vai assim mesmo** — é ele o documento fiscal —,
mas o sistema **diz por quê**: o aviso aparece na tela como erro (não como sucesso), fica
gravado na nota e a aba *E-mail* passa a mostrar em vermelho que a DANFE não vai sair. Foi
um defeito real: a biblioteca não estava instalada, o e-mail saía só com o XML e o sistema
dizia "enviado" — silêncio é o pior jeito de falhar.

Vão cópias para o e-mail da empresa e para o do contador, se configurados. O envio
automático pode ser desligado. **Falha de e-mail não derruba a nota**: ela já está
autorizada na SEFAZ, então o erro aparece como aviso e a nota guarda o que houve — na lista
o botão vira **Reenviar**, mostrando para quem e quando já foi.

Código: `backend/correio.py` (o envio), `backend/danfe.py` (`gerar_pdf`) e
`backend/routers/correio.py`.
Teste: `python testes/teste_email.py` — sobe um servidor SMTP de mentira em 127.0.0.1
(`testes/smtp_de_mentira.py`) e confere a mensagem inteira; **nenhum e-mail sai para a
internet**.

Os webservices são resolvidos por UF (MG, SP, PR, RS, GO, MT, MS, BA, PE, CE e AM têm
servidor próprio; o resto cai no SVRS). O corpo do envio vai no formato padrão
(`<nfeDadosMsg>` solto); se a SEFAZ responder que **não achou o método de despacho** — há
estado cujo WSDL espera o invólucro com o nome da operação — o sistema repete o envio no
outro formato sozinho, sem pedir nada a quem está emitindo. Antes de sair, a nota é barrada por item sem NCM ou
CFOP, cliente sem código do município do IBGE, contribuinte sem inscrição estadual e empresa
sem IE ou sem código do município — com a mensagem dizendo o que corrigir e onde.

#### De onde vem o imposto de cada item: as regras fiscais

O mesmo café não tem a mesma tributação para todo mundo: para indústria dentro de Minas é
diferido; para fora do estado é 7% ou 12%; para exportação é imune. Guardar isso no cadastro
do produto obrigaria a criar um produto por situação — por isso existe a **tabela de regras
fiscais**, na mesma ideia da tabela de ICMS dos contratos (que cruza UF de origem com UF de
destino), só que com mais dimensões.

Cada **cliente** e cada **produto** recebem um **tipo fiscal** (aba *Cadastros → Tipos
fiscais*): o cliente ganha algo como *Indústria*, *Produtor rural*, *Não contribuinte* ou
*Exportação*; o produto ganha *Café cru em grão*, *Café industrializado*, *Serviço*… O botão
**Criar os tipos sugeridos** já deixa a lista pronta.

A aba *Cadastros → Regras fiscais* é onde mora **toda a tributação**. A janela vem na ordem
em que se pensa a operação:

1. **Quando vale** — CFOP, UF de origem (já preenchida com a UF do cadastro da empresa),
   UF de destino, tipo de cliente, tipo de item, operação e prioridade.
2. **ICMS** — CST/CSOSN, base de cálculo, redução da base, alíquota e origem da mercadoria.
3. **PIS e COFINS** — CST, base de cálculo, redução da base, alíquota de PIS, de COFINS,
   e o IPI.
4. **IBS e CBS** — CST, `cClassTrib`, base de cálculo, redução da base, **redução de
   alíquota**, alíquota de CBS, de IBS estadual e de IBS municipal.

As **bases são percentuais do valor do item** — 100 quer dizer "o valor inteiro entra na
base" —, e a **redução** é aplicada depois, sobre essa base. Exemplo num item de R$ 100.000:
base 80% e redução de 25% dão base de R$ 60.000, e 18% de alíquota dão R$ 10.800 de ICMS.
A **redução de alíquota** do IBS/CBS é o redutor da reforma: 60 desconta 60% das três
alíquotas de uma vez, então uma CBS de 0,9% vira 0,36%.

**Zero é zero.** Todo número da regra vale como está: base 0% zera a base, alíquota 0% não
destaca imposto. Não existe "campo vazio vira padrão" na regra — quem preencheu a regra
decidiu. Os padrões da reforma (IBS 0,1% e CBS 0,9%) só entram quando **nenhuma regra serve**
para o item. Por isso, numa regra que destaca IBS/CBS, preencha as alíquotas: deixá-las em
branco não é "usar o padrão", é dizer que não há IBS nem CBS.

**O CST do IBS/CBS decide se a base e a alíquota podem ir na nota.** Na tabela oficial cada
CST tem o indicador `ind_gIBSCBS`; quando ele é 0 — isenção (400), imunidade (410), suspensão
(550), monofasia (620), transferência de crédito (800), ajustes (810/811), regime específico
(820), exclusão de base (830) — o grupo `gIBSCBS` **não pode** ser enviado, e mandá-lo é a
rejeição **1021 (grupo IBS/CBS informado indevidamente)**; nos demais (000, 010, 011, 200,
210, 220, 221, 222, 510, 515) ele é obrigatório, e omiti-lo é a **1022/1115**. A emissão
resolve isso sozinha (`CST_SEM_GRUPO_IBSCBS` em `backend/emissao.py`): o CST e o `cClassTrib`
sempre saem, o grupo de valores só sai quando o CST permite, e o `IBSCBSTot` soma apenas os
itens que levaram o grupo, mas **sai sempre**, zerado se for o caso: sem ele a SEFAZ
devolve a rejeição **1119 (total de IBS e CBS não informado)**. Na Conferência do cálculo,
a regra com um CST desses avisa em vermelho que os valores não vão para a nota.

**O CST e o `cClassTrib` não podem discordar**, e é aí que a 1021 costuma nascer: nos códigos
oficiais os **três primeiros números do `cClassTrib` são o CST** — `000001` é do 000, `400001`
é do 400, `620002` é do 620. Um `cClassTrib` de isenção com o CST em branco fazia o item sair
como 000 (tributado), com base e alíquota que aquele código não aceita. Agora: `cClassTrib`
preenchido e CST vazio → o CST **vem do código**; os dois preenchidos e discordando → a regra
nem salva, e a emissão para antes da SEFAZ dizendo qual item e quais códigos.

Na tela do item, **campo de valor nunca fica vazio**: zero aparece como `0`. Vazio deixava
dúvida se era zero mesmo ou se faltava preencher — e, em imposto, essa dúvida vira recusa.

No fim da janela da regra tem a **Conferência do cálculo**: digite um valor de item (vem com
R$ 1.000) e a tela mostra, a cada campo mexido, a conta inteira — `valor × base% = base
cheia − redução% → base` e `base × alíquota% = imposto` — para ICMS, PIS, COFINS, IPI, CBS e
IBS, com o total de impostos do item. Mexer nesse campo não conta como alteração a salvar. O
botão **Testar uma situação** mostra a mesma conta junto com a regra que venceu. Os números
vêm de `fiscal.calcular()`, que é a **mesma** função usada na hora de gravar o item da nota —
então o que aparece na conferência é o que vai sair na NF-e.

O **cadastro do produto não guarda mais CST nem alíquota**. Lá ficam só a identificação da
mercadoria — NCM, CEST, origem, unidades, GTIN, pesos, cBenef — e o **tipo fiscal**. Quem
decide imposto é a tabela de regras, porque a mesma mercadoria é tributada de um jeito para
cada cliente e cada destino.

O campo `cClassTrib` tem o botão **Procurar na tabela**, que abre os códigos do Informe
Técnico 2025.002 com busca por número, por CST ou por palavra (tabela resumida em
`backend/cclasstrib.py`; o campo continua aceitando qualquer código digitado).

Campo em branco quer dizer *qualquer um*. Quando mais de uma regra serve, ganha a **mais
específica**, pelo peso de cada campo: tipo de cliente 32, tipo de item 16, CFOP 8, UF de
destino 4, UF de origem 2, operação 1 — e no empate, a de maior `prioridade`. O botão
**Testar uma situação** mostra qual linha venceria para um cliente, um produto e um CFOP de
verdade, sem precisar montar nota.

No item da nota, **mudar o CFOP refaz a busca da regra na hora**: é o CFOP digitado, com as
UFs e os dois tipos, que decide qual legislação vale para aquele item. A ordem de quem manda
é **o que foi digitado à mão → a regra fiscal → zero**. O item mostra qual regra foi usada e
tem o botão *Refazer os impostos por esta regra*. Item sem regra nenhuma nasce **sem CST** —
o aviso na etapa de conferência mostra isso antes de transmitir.

A tela do item **não guarda imposto por conta própria**: ela manda para o servidor só os
campos que a pessoa digitou à mão, e tudo que estiver em branco é calculado lá pela regra. É
por isso que a **base de cálculo sai sempre da tabela de regras** — antes a tela calculava a
base sozinha (valor do item menos a redução) e mandava esse número, que valia como digitado e
atropelava o percentual da regra. Consequência prática: **corrigir a regra conserta os
rascunhos abertos** — basta reabrir e salvar, sem tocar em item nenhum.

O que foi digitado à mão fica gravado em `NotaItem.campos_manuais` (os nomes dos campos,
separados por vírgula), então o rascunho reaberto sabe o que é da regra e o que é da pessoa.
Apagar o campo na tela o devolve para a regra; o botão *Refazer os impostos por esta regra*
limpa todos de uma vez.

Código: `backend/fiscal.py` (o casamento e a conta) e `backend/routers/fiscal.py`.
Testes: `python testes/teste_regras_fiscais.py` e `python testes/teste_base_da_regra.py`.

#### Impostos item a item

Cada item da nota abre um bloco **Impostos** com tudo à vista e editável:

| Imposto | Campos |
| --- | --- |
| ICMS | origem, CST (regime normal) ou CSOSN (Simples), redução da base, base de cálculo, alíquota e valor |
| PIS / COFINS | CST, alíquota e valor de cada um |
| IPI | CST, alíquota e valor |
| IBS / CBS | CST, `cClassTrib`, base, IBS estadual (%/valor), IBS municipal (%/valor) e CBS (%/valor) |

Os valores são **calculados enquanto se digita** (base × alíquota), mas qualquer um pode
ser escrito à mão — o que for digitado passa a mandar e não é mais sobrescrito; apagando o
campo, ele volta a se calcular sozinho. O que vem em branco é buscado no cadastro do
produto. CST sem destaque (40, 41, 50, 51, 60 e os CSOSN equivalentes) zera o valor do ICMS
sozinho, e a redução de base entra antes da alíquota.

As alíquotas de IBS e CBS nascem com os valores de **teste de 2026** (IBS 0,1% e CBS 0,9%,
apuração informativa), definidos em `IBS_UF_PADRAO`, `IBS_MUN_PADRAO` e `CBS_PADRAO` no
`backend/emissao.py`. A etapa de conferência avisa quando falta CST ou `cClassTrib`.

Esses campos **vão no XML**: cada item leva o grupo `IBSCBS` (CST, `cClassTrib` e, dentro de
`gIBSCBS`, a base, o IBS do estado, o IBS do município, o total do IBS e a CBS), e o `<total>`
leva o `IBSCBSTot` somando tudo. Sem esse grupo a SEFAZ devolve a rejeição **1115 — IBS/CBS
não informado**. Item sem CST/`cClassTrib` cadastrado sai como tributação integral
(`000` / `000001`) com as alíquotas de teste — o que deixa a nota passar; a classificação
certa de cada operação se cadastra nas Regras fiscais. A estrutura foi tirada do schema
oficial em `testes/xsd/`, e `teste_schema_nfe.py` confere ordem, valores e o somatório.

> A tributação (CFOP, CST/CSOSN, alíquotas) é responsabilidade do contribuinte e do seu
> contador: o sistema usa o que está nos cadastros e não decide tributação sozinho.
> Comece sempre em homologação.

#### Conferir o XML antes de mandar

O schema oficial da NF-e 4.00 está em `testes/xsd/`, e `testes/teste_schema_nfe.py` valida
contra ele a nota simples, a nota completa (transporte, duplicatas, texto livre), os CST de
ICMS que o café usa (00, 20, 51 diferimento, 40 e 60), a nota **assinada** e o lote.

**Indicativo do intermediador.** A NT 2020.006 exige o `indIntermed` quando a venda não é
presencial (`indPres` 2, 3, 4 ou 9) — sem ele vem a rejeição **434**. O sistema manda
`indIntermed = 0` (sem intermediador) nesses casos e omite o campo quando `indPres` é 0 ou 1,
onde ele não cabe. Venda por marketplace precisaria de `1` mais o CNPJ da plataforma.

**Data e hora da nota.** O servidor roda em **UTC** e o banco guarda tudo em UTC; o `dhEmi`
sai no fuso de Brasília, então a hora é *convertida* — nunca apenas etiquetada. Etiquetar
jogava a nota três horas para a frente e trazia a rejeição **703 — Data-Hora de Emissão
posterior ao horário de recebimento**. Por segurança, qualquer diferença de relógio para o
futuro é puxada de volta para agora, e a mesma regra vale para o `dhEvento` da manifestação
e do cancelamento. `backend/emissao.py: _hora_de_emissao()`. Assim o
erro aparece aqui, com o nome do campo, em vez de virar uma *Rejeição 225 — Falha no Schema
XML* que não diz qual campo está errado. Foi esse teste que mostrou o `dhEmi` saindo com
fração de segundo (`...T21:48:18.609636-03:00`), que o schema não aceita. O sistema em si
continua sem depender de `lxml`: a validação é só do teste.

#### Quando a SEFAZ recusa

A SEFAZ responde com um código (`cStat`) e uma frase curta — *"Rejeição: Duplicidade de
NF-e"* — que não diz o que fazer. O sistema traduz essa resposta em três partes e mostra
num painel que **fica na tela** (não some como aviso): o que aconteceu, o que fazer para
a nota passar, e a resposta original da SEFAZ com o código, para levar ao contador.
Junto vai um **atalho para o lugar do conserto**: cadastro da empresa, do cliente, do
produto, o certificado digital ou a etapa certa da própria nota.

O painel é **o elemento mais destacado da tela**: faixa vermelha com o título *A SEFAZ NÃO
ACEITOU A NOTA*, selos com o código e com o número do item apontado (a SEFAZ manda
`[nItem: 3]`), a causa em letra grande, o que fazer logo abaixo e, por último, as palavras
exatas da SEFAZ numa caixa à parte. Quando a recusa é de um item, o atalho vira *Ir para o
item 3* e abre a nota já rolada até ele, com o bloco de impostos aberto.

O aviso continua dentro da nota quando ela é reaberta, então dá para corrigir com calma.
Rejeição comum devolve o número da série e a nota volta a ser rascunho; denegação consome
o número e exige nota nova. Códigos fora da tabela ainda saem explicados: a frase da SEFAZ
é lida em busca de palavras conhecidas (certificado, NCM, CFOP, inscrição estadual...).

Código: `backend/emissao.py` (chave, XML, assinatura, transmissão e cancelamento),
`backend/rejeicoes.py` (a tradução das recusas) e `backend/routers/emissao.py`;
tela em `frontend/js/emissao.js`.
Teste: `python testes/teste_emissao.py` — monta e confere o XML inteiro **sem tocar na SEFAZ**.


### Estoque

**Movimento → Estoque** responde duas perguntas: *quantos eu tenho* e *quanto vale o que
está parado*. O estoque aqui não é um número que alguém digita — é a **soma dos
movimentos**, e cada movimento diz de onde veio.

Só entra no controle o produto marcado com **controla estoque** no cadastro. Comissão,
frete e serviço continuam saindo em nota sem mexer em saldo nenhum — é o que impede o
relatório de virar um amontoado.

| De onde vem | Como acontece |
|---|---|
| **Entrada** | O botão **+ Estoque** na linha da nota de entrada. É manual de propósito: nota de entrada chega da SEFAZ o tempo todo e nem toda ela é mercadoria que a empresa guarda. |
| **Saída** | **Sozinha**, no momento em que a SEFAZ autoriza a NF-e de saída ou o cupom fiscal. Autorizou, saiu do estoque. |
| **Devolução** | Nota cancelada devolve o que tinha tirado. |
| **Acerto** | A tela de estoque, para inventário, perda e saldo inicial — sempre com o motivo escrito. |

#### O custo médio

Ponderado, que é o método que a legislação aceita. Na entrada:

    novo = (saldo × custo_medio + quantidade × custo_da_entrada) / (saldo + quantidade)

Na saída, o custo que sai é o custo médio do momento — o custo médio em si não muda. É isso
que faz a tela responder "quanto vale o que está parado" e dá base para a margem da venda.

O custo da entrada é o valor do item na nota: **valor − desconto + frete**. IPI e ST ficam
de fora, porque nem sempre compõem custo e dependem do regime da empresa; quem precisar
desse detalhe ajusta pela tela.

#### O que o sistema não deixa passar

- **Venda maior que o saldo é barrada** antes de a nota ir para a SEFAZ, com a frase
  dizendo o produto, quanto tem e quanto a nota quer. Nota autorizada não volta atrás, então
  descobrir depois não adiantaria nada. A conferência acontece antes até de abrir o
  certificado, e a nota barrada **não gasta número da série**.
- **Somar saca com quilo** é recusado: o saldo é contado na unidade do primeiro movimento, e
  movimento em outra unidade explica o que fazer em vez de estragar o saldo em silêncio.
- **Acerto sem motivo** é recusado — é o motivo que explica o movimento daqui a seis meses.
- **Estorno não apaga**: lança os movimentos de sentido contrário, e o extrato mostra os dois.
  Quem apaga movimento apaga a história.
- **Saldo inicial** só vale para produto ainda sem movimento; depois disso o caminho é o
  acerto, que deixa rastro.

A tela tem **Posição** (saldo, custo médio e valor por produto, com aviso de estoque mínimo e
de saldo negativo) e **Extrato** (os movimentos, com o saldo e o custo médio **depois de cada
um** — assim um erro antigo fica visível em vez de sumir numa soma).

Código: `backend/estoque.py` (o motor), `backend/routers/estoque.py`, o botão em
`backend/routers/notas.py` e a baixa em `backend/routers/emissao.py`; tela em
`frontend/js/estoque.js`.
Teste: `python testes/teste_estoque.py`.


### GTA — Guia de Trânsito Animal

**Movimento → GTA (trânsito animal)** guarda e vigia as guias dos produtores atendidos, e
imprime a **ficha de preparo** para quem vai digitar no portal do estado.

#### Por que o sistema não emite a GTA

A GTA não é documento fiscal eletrônico como a NF-e: é documento de defesa sanitária animal, e
**a emissão fica no sistema do estado**, fechado, onde se entra com login pessoal — em Minas o
**SIAPEC**, do IMA; em São Paulo o GEDAVE; em Goiás o SIDAGO; no Pará o Sigeagro; em Mato
Grosso o INDEA. Quem emite é o **produtor** ou o **médico-veterinário habilitado**, com a
senha dele. A tela diz isso em cima, para ninguém procurar um botão que não pode existir.

**Existe um webservice federal — e ele não emite.** É o `GtaEmitidaWsService` da **PGA —
Plataforma de Gestão Agropecuária**, do Ministério da Agricultura (SOAP, em
`pga.agricultura.gov.br/sispga_ws/GtaEmitidaWsService?wsdl`). Repare no nome: GTA
**emitida**. O método principal é `gravarGtaEmitida` — quem chama já emitiu a guia e está
*registrando* isso; o manual descreve o serviço como "mantém informações da Guia de Trânsito
Animal, sem validação das informações do destino". Nada ali gera número de guia nem autoriza
trânsito. E quem chama é o **OESA** (o órgão estadual: IMA, Adepará, Indea…): o fluxo é "dos
OESAs para a PGA no MAPA", o estado prestando contas ao governo federal.

Os métodos de **consulta** desse mesmo serviço (`obterGtasEmitidaEstadual`,
`obterGtasEmitidaDestino`, `obterGtasEmitidaChave`) seriam muito úteis aqui — dariam para a
GTA o que o DF-e dá para a nota fiscal: buscar as guias sozinho em vez de digitá-las. Mas o
credenciamento é desenhado para OESA; enquanto não houver acesso, o módulo não fala com
serviço nenhum. Fonte: manual do WS da PGA, em `sites.google.com/agro.gov.br/manual-ws-pga`.

O que sobra — e é o que faltava — são duas coisas:

**1. Controle.** Toda GTA fica guardada: origem e destino (produtor, propriedade, inscrição
estadual, município/UF), espécie, categorias, finalidade, transporte, veterinário, número,
emissão e validade, com vínculo ao contrato e à nota e o PDF da guia anexado. A situação é
*em preparo*, *emitida*, *utilizada* ou *cancelada* — e **vencida o sistema calcula sozinho**,
comparando a validade com o dia de hoje: guia emitida que passou da data aparece como vencida
sem ninguém marcar nada, e o filtro por *vencida* usa essa conta, não a coluna. Faltando três
dias ou menos, a linha acende em âmbar com a frase ("Faltam 2 dias para esta guia vencer").
O cabeçalho conta válidas, vencendo, vencidas, em preparo e com pendência.

**2. Preparo.** A **conferência** aponta, *antes* de abrir o portal, o que o portal vai
cobrar: propriedade e inscrição estadual dos dois lados (o portal procura a fazenda, não a
pessoa), finalidade, categorias, placa no rodoviário — e, quando a carga muda de estado, que a
guia é interestadual e exige veterinário com CRMV. Os animais não entram como um número só:
vão separados por **sexo e faixa de idade**, como o portal pede, com as faixas certas de cada
espécie (bovino e bubalino em quatro faixas, suíno em três), e a quantidade total é a soma —
divergência é apontada. Escolher o produtor no cadastro traz nome, documento, inscrição e
município sozinho; o que foi digitado à mão manda sobre o cadastro, porque a propriedade pode
ser outra.

A **ficha de preparo** é a folha A4 para levar ao portal: diz o sistema e o órgão do estado,
lista as pendências em vermelho no topo, e traz os blocos **na ordem das telas do portal** —
origem, destino, animais, transporte, responsável técnico e, por último, os campos para anotar
o número e a validade depois que a guia sair. Campo em branco sai marcado *— em branco —*, em
vermelho. A folha avisa, em cima, que **não é a GTA**: a guia válida é a que sair do portal.

Apagar guia já emitida no portal é barrado, porque apagar aqui não cancela lá — o caminho é
cancelar no portal e marcar como cancelada, para o histórico ficar certo.

A tela tem um **manual só da GTA** em PDF (`frontend/manual/Manual-GTA.pdf`), com os
cadastros necessários e o passo a passo inteiro — da guia em preparo até a guia utilizada.
A fonte dele está em `docs/manual/` (ver o LEIA-ME de lá).

Código: `backend/gta.py` (tabelas, conferência e ficha), `backend/routers/gta.py`; tela em
`frontend/js/gta.js`.
Teste: `python testes/teste_gta.py`.


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

Com a gaveta fechada, é a **barra de cima** que diz onde a pessoa está: ela leva o ícone e
o nome **AgroDock** ao lado do ☰, e o nome da tela vai numa segunda linha, com uma
divisória — assim título comprido não sai cortado. Em celular pequeno (menos de 370px) o
seletor de empresa desce e fica ao lado do nome da tela.

Nada estoura para o lado: a varredura automática de layout confere, em **320, 390, 768,
1024 e 1920px**, se alguma tela tem rolagem horizontal ou algum elemento passando da
borda. No computador largo (a partir de 1620px) o conteúdo para de esticar em 1560px e a
folga vai para as laterais — igual no aviso de assinatura, na barra de cima e na página,
para tudo terminar na mesma linha.

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
│   ├── danfe.py                 Folha da nota fiscal (DANFE): página para imprimir e PDF
│   ├── notas.py                 Regras das notas: importar o XML, faturar e desfaturar
│   ├── emissao.py               NF-e 4.00: chave, XML, assinatura e webservices por UF
│   ├── rejeicoes.py             Recusas da SEFAZ explicadas e com o lugar do conserto
│   ├── correio.py               Envio de e-mail pela conta da empresa (SMTP), com anexos
│   ├── cupom.py                 Cupom fiscal (NFC-e 65): QR Code, CSC e endereços da SEFAZ
│   ├── danfe_cupom.py           A folha do cupom, em 80 mm, com o QR Code
│   ├── gta.py                   GTA: espécies, conferência e ficha de preparo do portal
│   ├── estoque.py               Estoque: movimentos, custo médio e conferência da venda
│   ├── planos.py                Os quatro planos: módulos, preços e o que cada um libera
│   ├── descontos.py             Cupons de desconto da assinatura (não é o cupom fiscal)
│   ├── sefaz_enderecos.py       Endereços da NFC-e por estado, editáveis na tela
│   ├── pedidos.py               Pedido e orçamento: numeração, totais e parcelas
│   ├── fiscal.py                Regras fiscais: cruza CFOP, UFs, tipo de cliente e de item
│   ├── cclasstrib.py            Tabela de classificação tributária do IBS/CBS (NT 2025.002)
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
│       ├── cupom.py             Cupom fiscal: CSC, venda de balcão e impressão
│       ├── gta.py               GTA: guias dos produtores, situação e ficha de preparo
│       ├── correio.py           Conta de e-mail da empresa e envio da nota
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
    ├── teste_edicao.py          Teste do aviso de "não salvo" e do Salvar em cada etapa
    ├── teste_regras_fiscais.py  Teste do cruzamento cliente x item e do imposto escolhido
    ├── teste_base_da_regra.py   Teste de que a base do item sai da regra, e não da tela
    ├── teste_cupom.py           Teste do cupom fiscal: schema oficial e QR Code conferido
    ├── teste_email.py           Teste do envio da nota por e-mail (XML + DANFE em PDF)
    ├── teste_gta.py             Teste da GTA: conferência, validade e ficha de preparo
    ├── teste_estoque.py         Teste do estoque: custo médio, baixa na venda e bloqueio
    ├── teste_planos.py          Teste dos quatro planos e do que cada conta enxerga
    ├── teste_cupons.py          Teste dos cupons de desconto e do Pix com desconto
    ├── teste_cupom_estados.py   Teste do cupom em MG, SP, GO e TO
    ├── teste_classificacao.py   Teste da categoria e da marca do produto
    ├── teste_pedidos.py         Teste do pedido, das parcelas e da finalização
    ├── smtp_de_mentira.py       Servidor SMTP falso usado pelo teste de e-mail
    ├── teste_schema_nfe.py      Valida o XML contra o schema oficial 4.00 (xsd/)
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
python testes/teste_classificacao.py # categoria e marca: obrigatórias, filtros e relatório
python testes/teste_pedidos.py      # pedido de venda, parcelas e contas a receber
python testes/teste_impressao.py    # folha do contrato e PDF (sai em testes/capturas/contrato.pdf)
python testes/teste_status_contrato.py  # ciclo de vida do contrato e relatório de contratos
python testes/teste_celular.py      # tela de 390x844: menu, listas em cartões e contrato por etapas
python testes/teste_edicao.py       # janela não fecha sozinha e Salvar em qualquer etapa
python testes/teste_regras_fiscais.py   # tipos fiscais, tabela de regras e o imposto do item
python testes/teste_base_da_regra.py    # a base do item da nota vem da regra fiscal
python testes/teste_email.py        # nota por e-mail, com servidor SMTP de mentira
python testes/teste_cupom.py        # cupom fiscal (NFC-e): XML no schema e QR Code
python testes/teste_gta.py          # GTA: conferência, validade, resumo e ficha de preparo
python testes/teste_estoque.py      # estoque: custo médio, entrada pela nota e baixa na venda
python testes/teste_planos.py       # os quatro planos, o bloqueio por plano e o menu
python testes/teste_cupons.py       # cupons de desconto: o valor certo no copia e cola
python testes/teste_schema_nfe.py   # valida o XML no schema oficial (precisa de lxml)
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
