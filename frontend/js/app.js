/* Inicialização, menu e roteamento.

   O menu não é fixo: ele é o que o **plano da conta** libera. O servidor manda,
   junto com a situação da assinatura, a lista de rotas permitidas (`rotas`), e
   é ela que decide o que aparece na barra e o que acontece quando alguém digita
   um endereço à mão. Esconder o item é conforto — quem barra de verdade é o
   servidor (ver `exigir_modulo` em backend/deps.py). */
const App = {
  rotas: {
    '/painel': { titulo: 'Painel', subtitulo: 'Visão geral do financeiro', acao: () => Relatorios.painel() },
    '/receber': { titulo: 'Contas a Receber', subtitulo: 'Títulos, recebimentos e baixas', acao: () => Lancamentos.contas('RECEBER') },
    '/pagar': { titulo: 'Contas a Pagar', subtitulo: 'Títulos, pagamentos e baixas', acao: () => Lancamentos.contas('PAGAR') },
    '/caixa': { titulo: 'Caixa e Bancos', subtitulo: 'Saldos, extrato e movimentos', acao: () => Caixa.tela() },
    '/contratos': { titulo: 'Contratos', subtitulo: 'Corretagem, compra e venda de café — com contas a receber e a pagar', acao: () => Contratos.tela() },
    '/notas': { titulo: 'Notas Fiscais', subtitulo: 'Gestão das notas: itens, cliente/fornecedor, faturar e desfaturar', acao: () => Notas.tela() },
    '/pedidos': { titulo: 'Pedidos e orçamentos', subtitulo: 'Monte a venda no balcão e finalize à vista ou a prazo', acao: () => Pedidos.tela() },
    '/cupom': { titulo: 'Cupom Fiscal', subtitulo: 'Venda de balcão: NFC-e em uma tela só, com impressão em 80 mm', acao: () => Cupom.tela() },
    '/gta': { titulo: 'GTA — Guia de Trânsito Animal', subtitulo: 'Controle das guias dos produtores e ficha de preparo para o portal do estado', acao: () => GTA.tela() },
    '/estoque': { titulo: 'Estoque', subtitulo: 'Saldo e custo médio de cada produto — a entrada vem da nota, a saída é baixada sozinha', acao: (aba) => Estoque.tela(aba) },
    '/dfe': { titulo: 'DF-e — Documentos fiscais', subtitulo: 'Notas emitidas contra o CNPJ da empresa: XML, DANFE, manifestação e importação', acao: (aba) => DFe.tela(aba) },
    '/relatorios': { titulo: 'Relatórios', subtitulo: 'DRE, balancete e relatórios gerenciais', acao: () => Relatorios.tela() },
    '/cadastros': { titulo: 'Cadastros', subtitulo: 'Todos os cadastros do sistema em um só lugar', acao: (aba) => Cadastros.hub(aba) },
    '/assinatura': { titulo: 'Minha Assinatura', subtitulo: 'Plano, pagamento por Pix e situação da conta', acao: () => Assinaturas.minha() },
    '/admin-empresas': { titulo: 'Empresas e acessos', subtitulo: 'Liberar e bloquear por data, limite de usuários por empresa', acao: () => Assinaturas.empresas(), master: true },
    '/admin-assinaturas': { titulo: 'Assinaturas', subtitulo: 'Contas cadastradas e confirmação de pagamentos', acao: () => Assinaturas.admin(), master: true },
    '/admin-cupons': { titulo: 'Cupons de desconto', subtitulo: 'Códigos de desconto da assinatura', acao: () => Assinaturas.cupons(), master: true },
    '/admin-sefaz': { titulo: 'Endereços da SEFAZ', subtitulo: 'Webservices da NFC-e em cada estado', acao: () => Assinaturas.sefaz(), master: true },
    '/configuracoes': { titulo: 'Configurações do site', subtitulo: 'Identidade, contatos, Pix e planos', acao: () => Assinaturas.configuracoes(), master: true },
  },

  /** As rotas que o plano da conta libera. Sem lista = tudo (conta interna). */
  rotasDoPlano() {
    const assinatura = Estado.usuario?.assinatura;
    return Array.isArray(assinatura?.rotas) ? assinatura.rotas : null;
  },

  /** Esta rota faz parte do plano? Cadastros, assinatura e admin são de todos. */
  noPlano(rota) {
    const liberadas = App.rotasDoPlano();
    if (!liberadas) return true;
    if (!App.ROTAS_DE_PLANO.includes(rota)) return true;
    return liberadas.includes(rota);
  },

  /* Só estas rotas dependem do plano; o resto é de toda conta. */
  ROTAS_DE_PLANO: ['/painel', '/receber', '/pagar', '/caixa', '/contratos', '/notas',
    '/pedidos', '/dfe', '/estoque', '/cupom', '/gta', '/relatorios'],

  menu() {
    /* Um grupo por assunto: o que é venda fica junto, o que é fiscal fica junto,
       o financeiro fica junto. Grupo cujo plano não libera nenhum item some
       inteiro — quem não tem o módulo não vê um título vazio na barra. */
    const itens = [
      { grupo: 'Vendas' },
      { rota: '/pedidos', icone: '🛒', rotulo: 'Pedidos e Vendas' },
      { rota: '/cupom', icone: '⌦', rotulo: 'Cupom Fiscal' },
      { rota: '/contratos', icone: '§', rotulo: 'Contratos' },
      { grupo: 'Fiscal' },
      { rota: '/notas', icone: '⛁', rotulo: 'Notas Fiscais' },
      { rota: '/dfe', icone: '⎙', rotulo: 'DF-e (buscar na SEFAZ)' },
      { rota: '/gta', icone: '☙', rotulo: 'GTA (trânsito animal)' },
      { grupo: 'Estoque' },
      { rota: '/estoque', icone: '▣', rotulo: 'Estoque' },
      { grupo: 'Financeiro' },
      { rota: '/painel', icone: '◧', rotulo: 'Painel' },
      { rota: '/receber', icone: '↓', rotulo: 'Contas a Receber' },
      { rota: '/pagar', icone: '↑', rotulo: 'Contas a Pagar' },
      { rota: '/caixa', icone: '▤', rotulo: 'Caixa e Bancos' },
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
        { rota: '/admin-cupons', icone: '%', rotulo: 'Cupons de desconto' },
        { rota: '/admin-sefaz', icone: '⌁', rotulo: 'Endereços da SEFAZ' },
        { rota: '/configuracoes', icone: '⚑', rotulo: 'Config. do site' },
      );
    } else {
      itens.push(
        { grupo: 'Assinatura' },
        { rota: '/assinatura', icone: '★', rotulo: 'Minha Assinatura' },
      );
    }
    itens.push(
      { grupo: 'Ajuda' },
      { link: App.MANUAL, icone: '?', rotulo: 'Manual do sistema (PDF)' },
    );
    // fora o que o plano não inclui — e o título de grupo que ficou sem nenhum item
    const doPlano = itens.filter((i) => !i.rota || App.noPlano(i.rota));
    return doPlano.filter((item, i) => {
      if (!item.grupo) return true;
      const proximo = doPlano[i + 1];
      return proximo && !proximo.grupo;
    });
  },

  /* Manual em PDF (frontend/manual/). Abre numa aba nova e dá para baixar. */
  MANUAL: '/static/manual/Manual-AgroDock.pdf',

  desenharMenu() {
    document.getElementById('menu').innerHTML = App.menu()
      .map((i) => (i.grupo
        ? `<div class="menu-grupo">${i.grupo}</div>`
        : i.link
        ? `<a class="menu-item" href="${i.link}" target="_blank" rel="noopener" download="Manual-AgroDock.pdf">
             <span class="menu-icone">${i.icone}</span><span>${i.rotulo}</span></a>`
        : `<a class="menu-item" href="#${i.rota}" data-rota="${i.rota}">
             <span class="menu-icone">${i.icone}</span><span>${i.rotulo}</span></a>`))
      .join('');
  },

  /* Links antigos (#/parceiros, #/bancos...) continuam funcionando: viram abas do hub. */
  ABAS_ANTIGAS: ['parceiros', 'bancos', 'centros-custo', 'operacoes', 'plano-contas',
    'empresas', 'usuarios', 'parametros', 'produtos', 'unidades', 'modalidades', 'icms'],

  async navegar() {
    if (!Estado.token) return;
    let caminho = location.hash.replace('#', '') || '/painel';
    if (App.ABAS_ANTIGAS.includes(caminho.slice(1))) caminho = `/cadastros${caminho}`;

    let aba = null;
    if (caminho.startsWith('/cadastros')) {
      aba = caminho.split('/')[2] || null;
      caminho = '/cadastros';
    } else if (caminho.startsWith('/dfe')) {
      aba = caminho.split('/')[2] || null;
      caminho = '/dfe';
    } else if (caminho.startsWith('/estoque')) {
      aba = caminho.split('/')[2] || null;
      caminho = '/estoque';
    }
    const rota = App.rotas[caminho] || App.rotas['/painel'];
    if (rota.master && !Api.ehMaster()) return App.irPara('/painel');
    // endereço digitado à mão para uma tela que o plano não tem
    if (!App.noPlano(caminho)) {
      UI.erro(`${rota.titulo} não faz parte do seu plano. Veja em Minha Assinatura.`);
      return App.irPara(App.primeiraRota());
    }

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

  /** Onde a conta cai quando o painel não faz parte do plano dela. */
  primeiraRota() {
    if (App.noPlano('/painel')) return '/painel';
    const item = App.menu().find((i) => i.rota);
    return item ? item.rota : '/cadastros';
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
    document.getElementById('modal-fechar').onclick = () => UI.tentarFecharModal();
    // clique fora só fecha quando não há nada digitado esperando para ser salvo
    document.getElementById('modal-fundo').onclick = (e) => {
      if (e.target.id !== 'modal-fundo') return;
      if (UI.modalComEdicao()) return UI.perguntarSaida();
      UI.fecharModal();
    };
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      App.fecharMenu();
      if (document.getElementById('pergunta-saida')) return UI.tirarPerguntaSaida();
      UI.tentarFecharModal();
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
