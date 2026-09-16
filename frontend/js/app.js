/* Inicialização, menu e roteamento. */
const App = {
  rotas: {
    '/painel': { titulo: 'Painel', subtitulo: 'Visão geral do financeiro', acao: () => Relatorios.painel() },
    '/receber': { titulo: 'Contas a Receber', subtitulo: 'Títulos, recebimentos e baixas', acao: () => Lancamentos.contas('RECEBER') },
    '/pagar': { titulo: 'Contas a Pagar', subtitulo: 'Títulos, pagamentos e baixas', acao: () => Lancamentos.contas('PAGAR') },
    '/caixa': { titulo: 'Caixa e Bancos', subtitulo: 'Saldos, extrato e movimentos', acao: () => Caixa.tela() },
    '/contratos': { titulo: 'Contratos', subtitulo: 'Intermediação, comissões e geração de recebíveis', acao: () => Contratos.tela() },
    '/relatorios': { titulo: 'Relatórios', subtitulo: 'DRE, balancete e relatórios gerenciais', acao: () => Relatorios.tela() },
    '/cadastros': { titulo: 'Cadastros', subtitulo: 'Todos os cadastros do sistema em um só lugar', acao: (aba) => Cadastros.hub(aba) },
    '/assinatura': { titulo: 'Minha Assinatura', subtitulo: 'Plano, pagamento por Pix e situação da conta', acao: () => Assinaturas.minha() },
    '/admin-empresas': { titulo: 'Empresas e acessos', subtitulo: 'Liberar e bloquear por data, limite de usuários por empresa', acao: () => Assinaturas.empresas(), master: true },
    '/admin-assinaturas': { titulo: 'Assinaturas', subtitulo: 'Contas cadastradas e confirmação de pagamentos', acao: () => Assinaturas.admin(), master: true },
    '/configuracoes': { titulo: 'Configurações do site', subtitulo: 'Identidade, contatos, Pix e planos', acao: () => Assinaturas.configuracoes(), master: true },
  },

  menu() {
    const itens = [
      { grupo: 'Movimento' },
      { rota: '/painel', icone: '◧', rotulo: 'Painel' },
      { rota: '/receber', icone: '↓', rotulo: 'Contas a Receber' },
      { rota: '/pagar', icone: '↑', rotulo: 'Contas a Pagar' },
      { rota: '/caixa', icone: '▤', rotulo: 'Caixa e Bancos' },
      { rota: '/contratos', icone: '§', rotulo: 'Contratos' },
      { grupo: 'Análise' },
      { rota: '/relatorios', icone: '▦', rotulo: 'Relatórios' },
      { grupo: 'Cadastros' },
      { rota: '/cadastros', icone: '≣', rotulo: 'Cadastros' },
    ];
    if (Api.ehMaster()) {
      itens.push(
        { grupo: 'Administração' },
        { rota: '/admin-empresas', icone: '⚿', rotulo: 'Empresas e acessos' },
        { rota: '/admin-assinaturas', icone: '★', rotulo: 'Assinaturas' },
        { rota: '/configuracoes', icone: '⚑', rotulo: 'Config. do site' },
      );
    } else {
      itens.push(
        { grupo: 'Assinatura' },
        { rota: '/assinatura', icone: '★', rotulo: 'Minha Assinatura' },
      );
    }
    return itens;
  },

  desenharMenu() {
    document.getElementById('menu').innerHTML = App.menu()
      .map((i) => (i.grupo
        ? `<div class="menu-grupo">${i.grupo}</div>`
        : `<a class="menu-item" href="#${i.rota}" data-rota="${i.rota}">
             <span class="menu-icone">${i.icone}</span><span>${i.rotulo}</span></a>`))
      .join('');
  },

  /* Links antigos (#/parceiros, #/bancos...) continuam funcionando: viram abas do hub. */
  ABAS_ANTIGAS: ['parceiros', 'bancos', 'centros-custo', 'operacoes', 'plano-contas',
    'empresas', 'usuarios', 'parametros', 'produtos', 'unidades', 'modalidades'],

  async navegar() {
    if (!Estado.token) return;
    let caminho = location.hash.replace('#', '') || '/painel';
    if (App.ABAS_ANTIGAS.includes(caminho.slice(1))) caminho = `/cadastros${caminho}`;

    let aba = null;
    if (caminho.startsWith('/cadastros')) {
      aba = caminho.split('/')[2] || null;
      caminho = '/cadastros';
    }
    const rota = App.rotas[caminho] || App.rotas['/painel'];
    if (rota.master && !Api.ehMaster()) return App.irPara('/painel');

    document.getElementById('titulo-pagina').textContent = rota.titulo;
    document.getElementById('subtitulo-pagina').textContent = rota.subtitulo;
    document.querySelectorAll('.menu-item').forEach((a) => {
      a.classList.toggle('ativo', a.dataset.rota === caminho);
    });
    App._rotaAtual = rota;
    App.fecharMenu();
    try {
      if (!Api.ehMaster() || !caminho.startsWith('/admin-')) await Api.carregarCache();
      await rota.acao(aba);
    } catch (e) {
      document.getElementById('pagina').innerHTML =
        `<div class="cartao"><div class="vazio">${UI.escapar(e.message)}</div></div>`;
    }
  },

  irPara(rota) {
    location.hash = `#${rota}`;
  },

  recarregar() {
    if (App._rotaAtual) App.navegar();
  },

  async iniciarSessao() {
    const dados = Estado.usuario && Estado.usuario.assinatura
      ? Estado.usuario
      : await Api.get('/api/auth/me');
    Estado.usuario = dados;
    const situacao = dados.assinatura || {};

    if (situacao.liberado === false) {
      await Assinaturas.bloquear(situacao.mensagem);
      return;
    }

    document.getElementById('site').classList.add('oculto');
    document.getElementById('tela-pagamento').classList.add('oculto');
    document.getElementById('app').classList.remove('oculto');
    document.getElementById('usuario-nome').textContent =
      `${dados.nome}${dados.perfil === 'MASTER' ? ' · admin' : ''}`;
    Assinaturas.faixa(situacao);

    Estado.empresas = await Api.get('/api/empresas');
    if (!Estado.empresas.length) {
      document.getElementById('pagina').innerHTML =
        '<div class="cartao"><div class="vazio">Nenhuma empresa cadastrada. Vá em Cadastros &gt; Empresas para criar a primeira.</div></div>';
    }
    if (!Estado.empresaId || !Estado.empresas.some((e) => e.id === Estado.empresaId)) {
      Estado.empresaId = Estado.empresas.length ? Estado.empresas[0].id : null;
    }
    localStorage.setItem('fin_empresa', Estado.empresaId || '');

    const seletor = document.getElementById('seletor-empresa');
    seletor.innerHTML = Estado.empresas
      .map((e) => `<option value="${e.id}" ${e.id === Estado.empresaId ? 'selected' : ''}>${UI.escapar(e.nome_fantasia || e.razao_social)}</option>`)
      .join('');
    seletor.onchange = async () => {
      Estado.empresaId = Number(seletor.value);
      localStorage.setItem('fin_empresa', Estado.empresaId);
      await Api.carregarCache(true);
      App.navegar();
    };

    App.desenharMenu();
    App.mostrarVersao();
    await App.navegar();
  },

  /** Mostra a data da versão carregada — serve para conferir se a atualização pegou. */
  async mostrarVersao() {
    const alvo = document.getElementById('versao-sistema');
    if (!alvo) return;
    try {
      const { versao } = await Api.get('/api/health');
      const d = new Date(Number(versao) * 1000);
      alvo.textContent = `versão de ${d.toLocaleDateString('pt-BR')} ${d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`;
    } catch {
      alvo.textContent = '';
    }
  },

  /* ------------------------------------------------ gaveta do menu (celular) */
  abrirMenu() {
    document.getElementById('app').classList.add('menu-aberto');
  },
  fecharMenu() {
    document.getElementById('app').classList.remove('menu-aberto');
  },

  async inicio() {
    document.getElementById('btn-abrir-menu').onclick = App.abrirMenu;
    document.getElementById('btn-fechar-menu').onclick = App.fecharMenu;
    document.getElementById('menu-fundo').onclick = App.fecharMenu;
    document.getElementById('modal-fechar').onclick = UI.fecharModal;
    document.getElementById('modal-fundo').onclick = (e) => {
      if (e.target.id === 'modal-fundo') UI.fecharModal();
    };
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { UI.fecharModal(); App.fecharMenu(); }
    });
    document.getElementById('btn-sair').onclick = () => Api.sair();
    window.addEventListener('hashchange', () => App.navegar());
    Site.ligarBotoes();

    if (Estado.token) {
      try {
        await App.iniciarSessao();
        return;
      } catch {
        Estado.token = null;
        localStorage.removeItem('fin_token');
      }
    }
    await Site.abrir();
  },
};

document.addEventListener('DOMContentLoaded', App.inicio);
