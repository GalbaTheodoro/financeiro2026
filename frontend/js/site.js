/* Site público: apresentação do sistema, planos, login e criação de conta. */
const Site = {
  info: null,
  /* módulos que não são apresentados no site público (continuam no sistema) */
  FORA_DO_SITE: ['GTA'],

  /* Os cartões das seções "Fiscal e vendas" e "Financeiro e gestão". Contratos,
     amostras, armazém e mercado têm seção própria, escrita no index.html. A GTA
     não aparece no site (decisão de out/2026) — continua no sistema para quem tem. */
  RECURSOS: [
    { area: 'fiscal', icone: '⛁', destaque: true, titulo: 'Nota fiscal eletrônica',
      texto: 'NF-e 4.00 assinada com o seu certificado e transmitida à SEFAZ em etapas curtas — o imposto sai da tabela de regras, sem digitar CST nem alíquota a cada nota. DANFE em PDF, envio por e-mail e, quando a SEFAZ recusa, a explicação em português com o que corrigir.' },
    { area: 'fiscal', icone: '⌦', destaque: true, titulo: 'Cupom fiscal eletrônico',
      texto: 'NFC-e para a venda de balcão: uma tela só, QR Code que o consumidor confere no site da SEFAZ e impressão na bobina de 80 mm.' },
    { area: 'fiscal', icone: '🛒', destaque: true, titulo: 'Vendas na tela de balcão',
      texto: 'Categoria, produto, fechar: pedido ou orçamento com número, impresso para o cliente. À vista ou a prazo, com nota, com cupom ou emitindo depois.' },
    { area: 'fiscal', icone: '▣', titulo: 'Controle de estoque',
      texto: 'A nota de entrada gera o estoque; a venda e o cupom baixam sozinhos. Saldo e custo médio por produto, estoque mínimo, extrato e venda barrada quando falta mercadoria.' },
    { area: 'fiscal', icone: '⇩', titulo: 'DF-e: notas emitidas contra você',
      texto: 'Busca na SEFAZ os documentos emitidos contra o seu CNPJ, importa o XML e vira conta a pagar — sem esperar o fornecedor mandar o arquivo.' },
    { area: 'fiscal', icone: '%', titulo: 'Vendas e margens',
      texto: 'Quanto vendeu, para quem e com que margem: melhores clientes, produtos mais vendidos, custos e o que está parado no estoque.' },
    { area: 'fiscal', icone: '＄', titulo: 'Formação do preço',
      texto: 'Markup a partir do custo, com impostos, comissão, frete, despesa fixa e o lucro que você quer — e o quadro de para onde vai cada real do preço.' },
    { area: 'fiscal', icone: '▥', titulo: 'SPED Fiscal e livros',
      texto: 'O arquivo da EFD ICMS/IPI para o contador e os livros fiscais de entrada e saída, gerados das notas que já estão no sistema.' },

    { area: 'financeiro', icone: '↓', destaque: true, titulo: 'Contas a receber',
      texto: 'Títulos por cliente, vencimento e situação, com baixa individual ou em lote, juros, multa, desconto e estorno.' },
    { area: 'financeiro', icone: '↑', destaque: true, titulo: 'Contas a pagar',
      texto: 'Parcelas, atraso destacado, pagamento parcial e onde pagar cada fornecedor — conta bancária ou chave Pix.' },
    { area: 'financeiro', icone: '▤', destaque: true, titulo: 'Caixa e bancos',
      texto: 'Saldo de cada conta, extrato com saldo acumulado, movimentos avulsos e transferência entre contas.' },
    { area: 'financeiro', icone: '▦', titulo: 'DRE, balancete e fluxo de caixa',
      texto: 'Resultado por competência ou caixa, balancete que fecha sozinho e fluxo com o saldo projetado pelos títulos em aberto.' },
    { area: 'financeiro', icone: '✎', titulo: 'Lançamento simples e múltiplo',
      texto: 'Uma tela curta para o dia a dia e o rateio entre várias contas e centros de custo quando o lançamento pede.' },
    { area: 'financeiro', icone: '☺', titulo: 'Cadastros com CNPJ e CEP',
      texto: 'Clientes e fornecedores buscados na Receita pelo CNPJ e o endereço pelo CEP; produtos, unidades, centros de custo e 112 contas contábeis prontas.' },
    { area: 'financeiro', icone: '⚿', titulo: 'Empresas e usuários',
      texto: 'Mais de uma empresa na mesma conta, usuários com perfil, prazo de acesso e bloqueio — cada um vê só o que pode.' },
    { area: 'financeiro', icone: '⎙', titulo: 'Relatórios prontos',
      texto: 'Contratos, títulos, razão, extratos e muito mais, prontos na tela e em CSV para a planilha.' },
  ],

  FAQ: [
    { p: 'O contrato de assessoria serve para o meu ramo?',
      r: 'Ele foi feito para quem aproxima comprador e vendedor e cobra corretagem dos dois lados — café, '
       + 'grãos, gado, o que for. Você escolhe o produto e a unidade no cadastro (saca de 60 kg, arroba, '
       + 'tonelada) e o sistema cuida do peso total, da comissão e das contas a receber.' },
    { p: 'Como sei em que pé está cada contrato?',
      r: 'Cada contrato tem uma situação que muda sozinha: Aberto enquanto não gerou título, Fechado a '
       + 'Receber assim que as comissões viram contas a receber, Recebido Parcial quando parte do dinheiro '
       + 'entra e Recebido Total quando tudo foi pago. O relatório de contratos mostra todos de uma vez, '
       + 'com o que já entrou, o que falta e o que venceu.' },
    { p: 'Qual é a diferença entre os planos?',
      r: 'Todos os planos têm o mesmo miolo: contrato de assessoria, amostras de café, financeiro '
       + 'inteiro (contas a receber e a pagar, caixa, DRE, balancete e relatórios) e emissão de NF-e. '
       + 'O que muda são os módulos extras, como o cupom fiscal eletrônico e o armazém (WMS). Cada '
       + 'cartão acima mostra o que aquele plano libera. Dentro do sistema, cada conta enxerga só '
       + 'as telas do plano dela.' },
    { p: 'O sistema serve para armazém que guarda café de terceiros?',
      r: 'Serve. O módulo de armazém faz a guia de entrada com os lotes e a posição de cada um '
       + '(quadra e pilha), as saídas ligadas ao contrato, os serviços (liga, rebenefício), a '
       + 'transferência de titularidade e a remoção entre quadras e armazéns — com o saldo por '
       + 'lote e por cliente sempre em dia.' },
    { p: 'Posso mudar de plano depois?',
      r: 'Pode. Enquanto o pagamento não foi confirmado, a troca é imediata em Minha Assinatura. '
       + 'Com a assinatura já ativa, a mudança vale na renovação — e nada do que você lançou se perde.' },
    { p: 'Como funciona o teste de 48 horas?',
      r: 'Assim que você conclui o cadastro, a conta fica liberada por 48 horas com os recursos do plano escolhido. '
       + 'Você pode lançar seus contratos e títulos reais, emitir relatórios e conferir o DRE. Depois desse '
       + 'prazo o acesso é bloqueado até a confirmação do pagamento — mas nada do que você lançou é perdido.' },
    { p: 'Como pago a assinatura?',
      r: 'Por Pix. Dentro do sistema você encontra a chave, o QR Code e o código copia e cola já com o '
       + 'valor do plano escolhido. Depois de pagar, clique em “Já fiz o Pix” para nos avisar.' },
    { p: 'Quantas pessoas podem usar?',
      r: 'A assinatura já inclui {U} usuários por empresa. Se precisar de mais, fale com a gente: '
       + 'o limite é ampliado depois da confirmação do pagamento, por Pix como a assinatura.' },
    { p: 'Existe um manual de uso?',
      r: 'Sim. O manual em PDF, com as telas do sistema passo a passo, pode ser baixado no rodapé desta '
       + 'página e, dentro do sistema, no menu Ajuda.' },
    { p: 'Existe cobrança automática ou fidelidade?',
      r: 'Não. O pagamento é único, por Pix, e vale pelo prazo do plano. Ao final do período você decide '
       + 'se renova, sem qualquer cobrança automática no cartão.' },
    { p: 'Preciso entender de contabilidade para usar?',
      r: 'Não. Você lança em linguagem do dia a dia (contrato, comissão, aluguel, folha) e o sistema faz a '
       + 'contabilização por trás, gerando DRE e balancete que fecham sozinhos.' },
  ],

  /* ------------------------------------------------------------------ montar */
  async abrir(secao) {
    document.getElementById('app').classList.add('oculto');
    document.getElementById('tela-pagamento').classList.add('oculto');
    document.getElementById('site').classList.remove('oculto');
    if (!Site.info) await Site.carregar();
    if (secao) document.getElementById(secao)?.scrollIntoView({ behavior: 'smooth' });
  },

  async carregar() {
    try {
      Site.info = await Api.get('/api/publico/info');
    } catch {
      Site.info = { nome_produto: 'AgroDock', marca_subtitulo: 'Contratos e Gestão',
                    planos: [], horas_teste: 48 };
    }
    const i = Site.info;

    const sub = i.marca_subtitulo || 'Contratos e Gestão';
    document.getElementById('site-nome').textContent = i.nome_produto;
    document.getElementById('rodape-nome').textContent = i.nome_produto;
    document.title = `${i.nome_produto} — ${sub}`;
    document.getElementById('site-subtitulo').textContent = sub;
    document.getElementById('hero-horas').textContent = `${i.horas_teste} horas`;
    if (i.slogan) document.getElementById('hero-slogan').textContent = i.slogan;
    document.getElementById('rodape-titular').textContent =
      i.empresa_titular ? `${i.empresa_titular} — todos os direitos reservados` : '';
    const contatos = [
      i.contato_whatsapp ? `WhatsApp: ${i.contato_whatsapp}` : '',
      i.contato_email ? `E-mail: ${i.contato_email}` : '',
    ].filter(Boolean);
    document.getElementById('rodape-contatos').innerHTML = contatos.join('<br>');

    document.querySelectorAll('[data-area]').forEach((caixa) => {
      caixa.innerHTML = Site.RECURSOS.filter((r) => r.area === caixa.dataset.area)
        .map((r) => `
          <div class="recurso ${r.destaque ? 'destaque' : ''}">
            <div class="recurso-icone">${r.icone}</div>
            <h3>${UI.escapar(r.titulo)}</h3>
            <p>${UI.escapar(r.texto)}</p>
          </div>`)
        .join('');
    });

    /* cada plano tem o seu número de usuários: se todos forem iguais o site diz
       "3"; se mudarem de um plano para outro, diz "a partir de 3" */
    const numeros = (Site.info.planos || []).map((p) => Number(p.usuarios)).filter(Boolean);
    const menor = numeros.length ? Math.min(...numeros) : (Site.info.usuarios_incluidos || 3);
    const textoUsuarios = numeros.some((n) => n !== menor) ? `a partir de ${menor}` : String(menor);

    document.getElementById('lista-faq').innerHTML = Site.FAQ
      .map((f) => `
        <details class="faq-item">
          <summary>${UI.escapar(f.p)}</summary>
          <p>${UI.escapar(f.r.replace('{U}', textoUsuarios))}</p>
        </details>`)
      .join('');

    document.querySelectorAll('.js-usuarios-incluidos').forEach((el) => {
      // no número grande do topo "a partir de 3" vira "3+"
      el.textContent = el.tagName === 'B' && textoUsuarios !== String(menor) ? `${menor}+` : textoUsuarios;
    });
    Site.desenharPlanos();
  },

  /* Os planos. O que muda de um para o outro não é o prazo — é o que a conta
     pode usar. Por isso cada cartão mostra primeiro o que o plano libera e, só
     depois, os dois prazos com seus preços. */
  desenharPlanos() {
    const planos = Site.info.planos || [];
    const usuarios = Site.info.usuarios_incluidos || 3;
    document.getElementById('lista-planos').innerHTML = planos
      .map((p) => `
        <div class="plano ${p.destaque ? 'plano-destaque' : ''}">
          ${p.destaque ? '<div class="plano-selo">Completo</div>' : ''}
          <h3>${UI.escapar(p.nome)}</h3>
          <div class="plano-para">${UI.escapar(p.para)}</div>
          <ul class="plano-itens">
            ${p.modulos.filter((m) => !Site.FORA_DO_SITE.includes(m.codigo))
              .map((m) => `<li><b>${UI.escapar(m.nome)}</b><span>${UI.escapar(m.texto)}</span></li>`).join('')}
            <li><b>${p.usuarios || usuarios} usuários inclusos</b><span>por empresa, com pacotes extras quando precisar.</span></li>
          </ul>
          <div class="plano-prazos">
            ${p.prazos.map((z) => `
              <button class="btn ${z.periodo === 'ANUAL' ? 'btn-primario' : ''} btn-bloco plano-prazo"
                      data-plano="${z.codigo}">
                <span class="plano-prazo-valor">${UI.moeda(z.valor)}</span>
                <span class="plano-prazo-nota">assinar ${z.meses} meses · ${UI.moeda(z.valor_mes)}/mês</span>
              </button>`).join('')}
          </div>
          ${p.economia ? `<div class="plano-economia">no anual você economiza ${UI.moeda(p.economia)}</div>` : ''}
        </div>`)
      .join('');

    document.querySelectorAll('[data-plano]').forEach((b) => {
      b.onclick = () => Site.formularioCadastro(b.dataset.plano);
    });
  },

  /* -------------------------------------------------------------- criar conta */
  formularioCadastro(planoEscolhido = 'P1_SEMESTRAL') {
    const planos = (Site.info?.planos) || [];
    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <div class="ok-caixa">
        Ao concluir o cadastro seu acesso fica liberado por
        <b>${Site.info?.horas_teste || 48} horas</b> para teste. O pagamento é feito por Pix
        dentro do sistema, quando você quiser.
      </div>
      <div class="linha-campos">
        ${UI.campo('Seu nome *', '<input name="nome" required placeholder="Nome completo">')}
        ${UI.campo('E-mail *', '<input type="email" name="email" required placeholder="voce@empresa.com.br">', 'será seu login')}
        ${UI.campo('Senha *', '<input type="password" name="senha" required placeholder="mínimo 6 caracteres">')}
        ${UI.campo('Telefone / WhatsApp', '<input name="telefone" placeholder="(00) 00000-0000">')}
        ${UI.campo('Nome da empresa', '<input name="empresa" placeholder="como aparece nos relatórios">')}
        ${UI.campo('CNPJ ou CPF', '<input name="documento">')}
        ${UI.campo('Cidade', '<input name="cidade">')}
        ${UI.campo('UF', '<input name="uf" maxlength="2">')}
        ${UI.campo('Plano pretendido', UI.select('plano', planos.flatMap((p) => p.prazos.map((z) => ({
          valor: z.codigo,
          rotulo: `${p.nome} ${z.rotulo.toLowerCase()} — ${UI.moeda(z.valor)} (${z.meses} meses)`,
        }))), planoEscolhido, { vazio: false }), 'o plano decide quais telas a conta enxerga')}
        ${UI.campo('Cupom de desconto', '<input name="cupom" placeholder="se você recebeu um" '
          + 'autocapitalize="characters" spellcheck="false" style="text-transform:uppercase">',
          'o desconto entra na primeira cobrança')}
      </div>
      <div class="mini" id="aviso-cupom" style="margin-top:12px">
        Você pode trocar o plano depois, antes de fazer o Pix.
      </div>`;

    UI.abrirModal({
      titulo: 'Criar minha conta',
      corpo,
      largo: true,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        {
          rotulo: 'Criar conta e começar',
          classe: 'btn-primario',
          acao: async () => {
            const d = UI.lerFormulario(corpo);
            if (!d.nome || !d.email || !d.senha) {
              return UI.erro('Preencha nome, e-mail e senha.');
            }
            try {
              const r = await Api.post('/api/publico/cadastro', d);
              Estado.token = r.token;
              Estado.usuario = r.usuario;
              localStorage.setItem('fin_token', r.token);
              UI.fecharModal();
              UI.sucesso(r.mensagem);
              await App.iniciarSessao();
              Assinaturas.avisoBoasVindas(r);
            } catch (e) {
              UI.erro(e.message);
            }
          },
        },
      ],
    });

    /* O cupom é conferido na hora, ao sair do campo ou ao trocar de plano: a
       pessoa vê quanto vai pagar antes de criar a conta, não depois. */
    const campoCupom = corpo.querySelector('[name=cupom]');
    const aviso = corpo.querySelector('#aviso-cupom');
    const padrao = aviso.innerHTML;
    const conferirCupom = async () => {
      const codigo = (campoCupom.value || '').trim();
      if (!codigo) { aviso.innerHTML = padrao; aviso.classList.remove('positivo', 'alerta'); return; }
      try {
        const c = await Api.get(`/api/publico/cupom?codigo=${encodeURIComponent(codigo)}`);
        const prazo = planos.flatMap((p) => p.prazos).find(
          (z) => z.codigo === corpo.querySelector('[name=plano]').value);
        const desconto = prazo ? (prazo.valor * c.percentual) / 100 : 0;
        aviso.classList.add('positivo');
        aviso.classList.remove('alerta');
        aviso.innerHTML = `Cupom <b>${UI.escapar(c.codigo)}</b>: ${Assinaturas.porcento(c.percentual)} de desconto`
          + (prazo ? ` — você paga <b>${UI.moeda(prazo.valor - desconto)}</b> em vez de ${UI.moeda(prazo.valor)}.` : '.');
      } catch (e) {
        aviso.classList.add('alerta');
        aviso.classList.remove('positivo');
        aviso.textContent = e.message;
      }
    };
    campoCupom.onblur = conferirCupom;
    corpo.querySelector('[name=plano]').addEventListener('change', () => {
      if ((campoCupom.value || '').trim()) conferirCupom();
    });
  },

  /* -------------------------------------------------------------------- login */
  formularioLogin() {
    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <div class="linha-campos">
        ${UI.campo('E-mail', '<input type="email" name="email" autocomplete="username">')}
        ${UI.campo('Senha', '<input type="password" name="senha" autocomplete="current-password">')}
      </div>
      <div class="mini" style="margin-top:12px">
        Ainda não tem conta? <a href="#" id="link-criar">Crie a sua e teste por 48 horas.</a>
      </div>`;

    const entrar = async () => {
      const d = UI.lerFormulario(corpo);
      if (!d.email || !d.senha) return UI.erro('Informe e-mail e senha.');
      try {
        await Api.login(d.email, d.senha);
        UI.fecharModal();
        await App.iniciarSessao();
      } catch (e) {
        UI.erro(e.message);
      }
    };

    UI.abrirModal({
      titulo: 'Entrar no sistema',
      corpo,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        { rotulo: 'Entrar', classe: 'btn-primario', acao: entrar },
      ],
    });

    corpo.querySelector('#link-criar').onclick = (e) => {
      e.preventDefault();
      UI.fecharModal();
      Site.formularioCadastro();
    };
    corpo.querySelectorAll('input').forEach((i) => {
      i.onkeydown = (e) => { if (e.key === 'Enter') entrar(); };
    });
  },

  ligarBotoes() {
    const abrirCadastro = () => Site.formularioCadastro();
    const nav = document.querySelector('.site-nav');
    document.getElementById('btn-menu-site').onclick = () => nav.classList.toggle('aberto');
    nav.querySelectorAll('a').forEach((a) => {
      a.onclick = () => nav.classList.remove('aberto');
    });
    document.getElementById('btn-criar-conta').onclick = abrirCadastro;
    document.getElementById('btn-hero-cadastro').onclick = abrirCadastro;
    document.getElementById('btn-cta-final').onclick = abrirCadastro;
    document.getElementById('btn-entrar').onclick = () => Site.formularioLogin();
    // o botão agora leva à lista de recursos, que é onde estão nota, venda e estoque
    document.getElementById('btn-hero-contratos').onclick = () =>
      document.getElementById('recursos').scrollIntoView({ behavior: 'smooth' });
  },
};
