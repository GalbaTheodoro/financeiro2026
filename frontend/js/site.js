/* Site público: apresentação do sistema, planos, login e criação de conta. */
const Site = {
  info: null,

  RECURSOS: [
    { icone: '§', destaque: true, titulo: 'Contratos de assessoria',
      texto: 'Comprador, vendedor, representante, produto e unidade; corretagem em percentual dos dois lados, número automático e peso total calculado.' },
    { icone: '⇢', destaque: true, titulo: 'Do contrato ao recebível',
      texto: 'Um clique transforma as comissões em contas a receber, com vencimento, parcelamento e classificação contábil — e estorno enquanto não houver baixa.' },
    { icone: '◉', destaque: true, titulo: 'Situação de cada contrato',
      texto: 'Aberto, Fechado a Receber, Recebido Parcial, Recebido Total ou Cancelado — a situação muda sozinha conforme o dinheiro entra.' },
    { icone: '⎙', destaque: true, titulo: 'Contrato impresso em PDF',
      texto: 'Uma página A4 com seu logotipo, as partes, dados bancários, valor por extenso e campos de assinatura, pronta para salvar em PDF e enviar.' },
    { icone: '↓', titulo: 'Contas a receber',
      texto: 'Títulos por cliente, vencimento e situação, com baixa individual ou em lote, juros, multa, desconto e estorno.' },
    { icone: '↑', titulo: 'Contas a pagar',
      texto: 'Mesma agilidade para fornecedores: parcelas, atraso destacado, pagamento parcial e onde pagar cada um.' },
    { icone: '▤', titulo: 'Caixa e bancos',
      texto: 'Saldo de cada conta, extrato com saldo acumulado, movimentos avulsos e transferência entre contas.' },
    { icone: '✎', titulo: 'Lançamento simples e múltiplo',
      texto: 'Uma tela curta para o dia a dia e o rateio entre várias contas e centros de custo quando o lançamento pede.' },
    { icone: '▦', titulo: 'DRE e balancete',
      texto: 'Resultado por competência ou caixa e balancete de verificação que fecham sozinhos, a partir das partidas dobradas.' },
    { icone: '⇄', titulo: 'Fluxo de caixa e projeção',
      texto: 'Entradas e saídas por dia ou mês, com saldo projetado incluindo os títulos ainda em aberto.' },
    { icone: '☺', titulo: 'Clientes e fornecedores',
      texto: 'Busca do cadastro pelo CNPJ na Receita e do endereço pelo CEP, com as contas e chaves Pix de cada um.' },
    { icone: '≣', titulo: 'Cadastros num menu só',
      texto: 'Produtos, unidades com peso de conversão, modalidades, bancos, centros de custo, operações e plano de contas com 112 contas prontas.' },
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
    { p: 'Como funciona o teste de 48 horas?',
      r: 'Assim que você conclui o cadastro, a conta fica liberada por 48 horas com todos os recursos. '
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

    document.getElementById('lista-recursos').innerHTML = Site.RECURSOS
      .map((r) => `
        <div class="recurso ${r.destaque ? 'destaque' : ''}">
          <div class="recurso-icone">${r.icone}</div>
          <h3>${UI.escapar(r.titulo)}</h3>
          <p>${UI.escapar(r.texto)}</p>
        </div>`)
      .join('');

    document.getElementById('lista-faq').innerHTML = Site.FAQ
      .map((f) => `
        <details class="faq-item">
          <summary>${UI.escapar(f.p)}</summary>
          <p>${UI.escapar(f.r.replace('{U}', Site.info.usuarios_incluidos || 3))}</p>
        </details>`)
      .join('');

    document.querySelectorAll('.js-usuarios-incluidos').forEach((el) => {
      el.textContent = Site.info.usuarios_incluidos || 3;
    });
    Site.desenharPlanos();
  },

  desenharPlanos() {
    const planos = Site.info.planos || [];
    document.getElementById('lista-planos').innerHTML = planos
      .map((p) => `
        <div class="plano ${p.destaque ? 'plano-destaque' : ''}">
          ${p.destaque ? '<div class="plano-selo">Mais vantajoso</div>' : ''}
          <h3>${UI.escapar(p.nome)}</h3>
          <div class="plano-valor">${UI.moeda(p.valor)}</div>
          <div class="plano-periodo">pagamento único · ${p.meses} meses</div>
          <div class="plano-mes">equivale a ${UI.moeda(p.valor_mes)} por mês</div>
          ${p.economia ? `<div class="plano-economia">economia de ${UI.moeda(p.economia)} no ano</div>` : ''}
          <ul class="plano-itens">
            <li>Contratos de assessoria e comissões</li>
            <li>Impressão do contrato em PDF</li>
            <li>Contas a pagar e a receber sem limite</li>
            <li>Caixa, bancos e transferências</li>
            <li>DRE, balancete e razão contábil</li>
            <li>${Site.info.usuarios_incluidos || 3} usuários inclusos por empresa</li>
          </ul>
          <button class="btn ${p.destaque ? 'btn-primario' : ''} btn-bloco" data-plano="${p.codigo}">
            Assinar ${UI.escapar(p.nome.replace('Plano ', '').toLowerCase())}
          </button>
        </div>`)
      .join('');

    document.querySelectorAll('[data-plano]').forEach((b) => {
      b.onclick = () => Site.formularioCadastro(b.dataset.plano);
    });
  },

  /* -------------------------------------------------------------- criar conta */
  formularioCadastro(planoEscolhido = 'SEMESTRAL') {
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
        ${UI.campo('Plano pretendido', UI.select('plano', planos.map((p) => ({
          valor: p.codigo, rotulo: `${p.nome} — ${UI.moeda(p.valor)} (${p.meses} meses)`,
        })), planoEscolhido, { vazio: false }))}
      </div>
      <div class="mini" style="margin-top:12px">
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
    document.getElementById('btn-hero-contratos').onclick = () =>
      document.getElementById('contratos-site').scrollIntoView({ behavior: 'smooth' });
  },
};
