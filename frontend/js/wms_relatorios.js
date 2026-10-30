/* WMS — Relatórios e BI do armazém.

   Uma tela com seis abas que partem dos MESMOS filtros (período, armazém,
   cliente, safra, padrão e peneira):

     Painel          indicadores do período, o movimento mês a mês e a
                     fotografia do saldo de hoje — por cliente, safra, padrão,
                     peneira e a ocupação de cada armazém;
     Entradas, Saídas, Transferências (emitidas e recebidas), Serviços e Lotes
                     — cada um com "agrupar por", o gráfico do agrupamento, o
                     resumo e o detalhe, e os botões Excel e PDF.

   O Excel e o PDF são montados no servidor com os mesmos números da tela. */
const WMSRelatorios = {
  ABAS: [
    { id: 'painel', rotulo: 'Painel' },
    { id: 'entradas', rotulo: 'Entradas' },
    { id: 'saidas', rotulo: 'Saídas' },
    { id: 'transferencias', rotulo: 'Transferências' },
    { id: 'servicos', rotulo: 'Serviços' },
    { id: 'lotes', rotulo: 'Lotes' },
  ],
  CORES: { entradas: '#15774a', saidas: '#c2410c', transferencias: '#c9922e' },
  _aba: 'painel',
  _opcoes: null,
  _dados: null,
  _f: null,
  _detalheTodo: false,

  filtrosPadrao() {
    const hoje = new Date();
    return {
      de: `${hoje.getFullYear()}-01-01`, ate: UI.hoje(), armazem_id: '', cliente_id: '',
      safra: '', padrao: '', peneira: '', agrupar: 'cliente', direcao: 'todas', servico: '',
      com_saldo: true,
    };
  },

  async tela(aba) {
    if (aba && WMSRelatorios.ABAS.some((a) => a.id === aba)) WMSRelatorios._aba = aba;
    if (!WMSRelatorios._f) WMSRelatorios._f = WMSRelatorios.filtrosPadrao();
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';
    try {
      const eid = Estado.empresaId;
      const [armazens, opcoes] = await Promise.all([
        Api.get('/api/wms/armazens', { empresa_id: eid }),
        Api.get('/api/wms/relatorios/opcoes', { empresa_id: eid }),
      ]);
      WMS._armazens = armazens;
      WMSRelatorios._opcoes = opcoes;
      await WMSRelatorios.carregar();
    } catch (e) {
      alvo.innerHTML = `<div class="cartao"><div class="vazio">${UI.escapar(e.message)}</div></div>`;
    }
  },

  parametros(extra = {}) {
    const f = WMSRelatorios._f;
    const p = { empresa_id: Estado.empresaId, de: f.de, ate: f.ate, armazem_id: f.armazem_id,
      cliente_id: f.cliente_id, safra: f.safra, padrao: f.padrao, peneira: f.peneira, ...extra };
    if (WMSRelatorios._aba !== 'painel') p.agrupar = f.agrupar;
    if (WMSRelatorios._aba === 'transferencias') p.direcao = f.direcao;
    if (WMSRelatorios._aba === 'servicos') p.servico = f.servico;
    if (WMSRelatorios._aba === 'lotes') p.com_saldo = f.com_saldo ? 'true' : 'false';
    return p;
  },

  async carregar() {
    const aba = WMSRelatorios._aba;
    const caminho = aba === 'painel' ? '/api/wms/relatorios/painel' : `/api/wms/relatorios/${aba}`;
    WMSRelatorios._dados = await Api.get(caminho, WMSRelatorios.parametros());
    WMSRelatorios._detalheTodo = false;
    WMSRelatorios.desenhar();
  },

  /* --------------------------------------------------------------- moldura */
  desenhar() {
    const aba = WMSRelatorios._aba;
    const pagina = document.getElementById('pagina');
    pagina.innerHTML = `
      <div class="abas">${WMSRelatorios.ABAS.map((a) => `<button class="aba ${a.id === aba ? 'ativa' : ''}"
        data-aba="${a.id}">${a.rotulo}</button>`).join('')}</div>
      <div class="cartao" style="margin-bottom:14px">
        <div class="cartao-corpo">
          <form class="linha-campos rel-filtros" id="rel-filtros" data-nao-suja>${WMSRelatorios.campos()}</form>
          <div class="espaco" style="margin-top:12px;flex-wrap:wrap">
            <button class="btn btn-primario" id="rel-aplicar">Aplicar filtros</button>
            <button class="btn" id="rel-limpar">Limpar</button>
            <span class="mini" style="margin-left:4px">${UI.escapar(WMSRelatorios._dados?.filtros || '')}</span>
            ${aba !== 'painel' ? `<span class="direita espaco">
              <button class="btn" id="rel-xlsx">⤓ Excel</button>
              <button class="btn" id="rel-pdf">⤓ PDF</button></span>` : ''}
          </div>
        </div>
      </div>
      <div id="rel-conteudo">${aba === 'painel' ? WMSRelatorios.painel() : WMSRelatorios.relatorio()}</div>`;
    WMSRelatorios.ligar();
  },

  campos() {
    const f = WMSRelatorios._f;
    const o = WMSRelatorios._opcoes || {};
    const aba = WMSRelatorios._aba;
    const lista = (v) => (v || []).map((x) => ({ valor: x, rotulo: x }));
    const agrupamentos = Object.entries(o.agrupamentos || {})
      .filter(([k]) => k !== 'servico' || aba === 'servicos')
      .map(([valor, rotulo]) => ({ valor, rotulo }));
    return `
      ${aba !== 'lotes' ? `
        ${UI.campo('De', `<input type="date" name="de" value="${f.de}">`)}
        ${UI.campo('Até', `<input type="date" name="ate" value="${f.ate}">`)}` : ''}
      ${UI.campo('Armazém', UI.select('armazem_id', WMS._armazens.map((a) => ({ valor: a.id, rotulo: a.nome })),
        f.armazem_id, { vazio: 'Todos' }))}
      ${UI.campo('Cliente', UI.select('cliente_id', WMS.depositantes().map((p) => ({ valor: p.id, rotulo: p.nome })),
        f.cliente_id, { vazio: 'Todos' }))}
      ${UI.campo('Safra', UI.select('safra', lista(o.safras), f.safra, { vazio: 'Todas' }))}
      ${UI.campo('Padrão', UI.select('padrao', lista(o.padroes), f.padrao, { vazio: 'Todos' }))}
      ${UI.campo('Peneira', UI.select('peneira', lista(o.peneiras), f.peneira, { vazio: 'Todas' }))}
      ${aba === 'transferencias' ? UI.campo('Direção', UI.select('direcao', [
        { valor: 'todas', rotulo: 'Emitidas e recebidas' },
        { valor: 'emitidas', rotulo: 'Só emitidas (o cliente cedeu)' },
        { valor: 'recebidas', rotulo: 'Só recebidas (o cliente recebeu)' }], f.direcao, { vazio: false }),
        'vale quando um cliente está escolhido') : ''}
      ${aba === 'servicos' ? UI.campo('Serviço', UI.select('servico', lista(o.servicos), f.servico, { vazio: 'Todos' })) : ''}
      ${aba === 'lotes' ? `<label class="campo">Mostrar
        <span class="espaco" style="margin-top:6px"><input type="checkbox" name="com_saldo" ${f.com_saldo ? 'checked' : ''}>
        <span class="mini">só lotes com saldo</span></span></label>` : ''}
      ${aba !== 'painel' ? UI.campo('Agrupar por', UI.select('agrupar', agrupamentos, f.agrupar, { vazio: false })) : ''}`;
  },

  lerFiltros() {
    const form = document.getElementById('rel-filtros');
    const f = WMSRelatorios._f;
    form.querySelectorAll('[name]').forEach((c) => {
      f[c.name] = c.type === 'checkbox' ? c.checked : c.value;
    });
  },

  ligar() {
    const pagina = document.getElementById('pagina');
    pagina.querySelectorAll('[data-aba]').forEach((b) => {
      b.onclick = () => {
        WMSRelatorios.lerFiltros();
        WMSRelatorios._aba = b.dataset.aba;
        if (WMSRelatorios._aba !== 'servicos' && WMSRelatorios._f.agrupar === 'servico') {
          WMSRelatorios._f.agrupar = 'cliente';
        }
        WMSRelatorios.recarregar();
      };
    });
    pagina.querySelector('#rel-aplicar').onclick = () => { WMSRelatorios.lerFiltros(); WMSRelatorios.recarregar(); };
    pagina.querySelector('#rel-limpar').onclick = () => {
      WMSRelatorios._f = WMSRelatorios.filtrosPadrao();
      WMSRelatorios.recarregar();
    };
    // trocar o agrupamento ou um seletor já recarrega, sem precisar do botão
    pagina.querySelectorAll('#rel-filtros select, #rel-filtros input[type=checkbox]').forEach((c) => {
      c.onchange = () => { WMSRelatorios.lerFiltros(); WMSRelatorios.recarregar(); };
    });
    pagina.querySelector('#rel-xlsx')?.addEventListener('click', () => WMSRelatorios.baixar('xlsx'));
    pagina.querySelector('#rel-pdf')?.addEventListener('click', () => WMSRelatorios.baixar('pdf'));
    pagina.querySelector('#rel-mais')?.addEventListener('click', () => {
      WMSRelatorios._detalheTodo = true;
      document.getElementById('rel-detalhe').innerHTML = WMSRelatorios.detalhe();
    });
  },

  async recarregar() {
    try {
      await WMSRelatorios.carregar();
    } catch (e) {
      UI.erro(e.message);
    }
  },

  async baixar(formato) {
    WMSRelatorios.lerFiltros();
    const aba = WMSRelatorios._aba;
    const query = new URLSearchParams();
    Object.entries(WMSRelatorios.parametros()).forEach(([k, v]) => {
      if (v !== '' && v !== null && v !== undefined) query.set(k, v);
    });
    const botao = document.getElementById(formato === 'xlsx' ? 'rel-xlsx' : 'rel-pdf');
    if (botao) { botao.disabled = true; botao.textContent = 'Gerando...'; }
    try {
      const resposta = await fetch(`/api/wms/relatorios/${aba}/${formato}?${query}`, {
        headers: Estado.token ? { Authorization: `Bearer ${Estado.token}` } : {},
      });
      if (!resposta.ok) {
        const corpo = await resposta.json().catch(() => ({}));
        throw new Error(corpo.detail || 'Não foi possível gerar o arquivo.');
      }
      const nome = (resposta.headers.get('Content-Disposition') || '')
        .split('filename=')[1]?.replace(/"/g, '') || `armazem-${aba}.${formato}`;
      const blob = await resposta.blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = nome;
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 2000);
    } catch (e) {
      UI.erro(e.message);
    } finally {
      if (botao) { botao.disabled = false; botao.textContent = formato === 'xlsx' ? '⤓ Excel' : '⤓ PDF'; }
    }
  },

  /* ---------------------------------------------------------------- painel */
  painel() {
    const d = WMSRelatorios._dados;
    const k = d.indicadores;
    const sc = (v) => `${UI.numero(v, 0)} sc`;
    const cartao = (titulo, corpo, dica = '') => `
      <div class="cartao"><div class="cartao-cabecalho"><div><h3>${titulo}</h3>
        ${dica ? `<div class="mini">${dica}</div>` : ''}</div></div>
        <div class="cartao-corpo">${corpo}</div></div>`;
    const ranking = (lista) => UI.graficoRanking(lista, { campo: 'sacas', formato: sc, limite: 12 });
    return `
      <div class="grade g4" style="margin-bottom:14px">
        ${WMS.cartao('Saldo no armazém', sc(k.saldo_sacas), `${UI.numero(k.saldo_peso, 0)} kg · hoje`, 'verde')}
        ${WMS.cartao('Lotes com saldo', String(k.lotes_com_saldo), `${k.clientes_com_saldo} cliente(s)`, 'azul')}
        ${WMS.cartao('Entradas no período', sc(k.entradas_sacas), `${k.entradas_guias} guia(s)`, '')}
        ${WMS.cartao('Saídas no período', sc(k.saidas_sacas), `${k.saidas_guias} guia(s)`, '')}
      </div>
      <div class="grade g4" style="margin-bottom:14px">
        ${WMS.cartao('Transferências', sc(k.transferencias_sacas), `${k.transferencias_guias} guia(s) no período`, '')}
        ${WMS.cartao('Serviços', String(k.servicos_guias), `${UI.numero(k.servicos_despejo, 0)} sc despejadas`, '')}
        ${WMS.cartao('Resultado dos serviços', sc(k.servicos_resultado), 'lotes gerados', '')}
        ${WMS.cartao('Quebra nos serviços', sc(k.servicos_quebra), k.servicos_despejo
          ? `${UI.numero(k.servicos_quebra / k.servicos_despejo * 100, 1)}% do despejado` : 'sem serviço',
          k.servicos_quebra > 0 ? 'ambar' : '')}
      </div>
      ${cartao('Movimento mês a mês', UI.graficoColunas(d.mensal.map((m) => ({ ...m, periodo: m.rotulo })), {
        series: [
          { campo: 'entradas', rotulo: 'Entradas', cor: WMSRelatorios.CORES.entradas },
          { campo: 'saidas', rotulo: 'Saídas', cor: WMSRelatorios.CORES.saidas },
          { campo: 'transferencias', rotulo: 'Transferências', cor: WMSRelatorios.CORES.transferencias },
        ], formato: (v) => UI.numero(v, 0), altura: 220 }), 'sacas, nos 12 meses até a data final')}
      <div class="grade g2 rel-grade">
        ${cartao('Saldo por cliente', ranking(d.por_cliente), 'os 10 maiores, em sacas')}
        ${cartao('Saldo por safra', WMSRelatorios.rosca(d.por_safra), 'quanto do armazém é de cada safra')}
        ${cartao('Saldo por padrão', ranking(d.por_padrao), 'os 10 maiores')}
        ${cartao('Saldo por peneira', ranking(d.por_peneira))}
      </div>
      ${cartao('Ocupação dos armazéns', WMSRelatorios.ocupacao(d.ocupacao), 'saldo de hoje contra a capacidade cadastrada')}`;
  },

  /* rosca: a parte de cada safra no todo (até 6 fatias + "outras") */
  rosca(lista) {
    if (!lista || !lista.length) return '<div class="vazio">Nenhum lote com saldo.</div>';
    const cores = ['#15774a', '#c9922e', '#7c4a21', '#2563eb', '#0f766e', '#9333ea', '#94a3b8'];
    let fatias = lista.slice(0, 6);
    const resto = lista.slice(6).reduce((s, x) => s + x.sacas, 0);
    if (resto > 0) fatias = fatias.concat([{ rotulo: 'outras', sacas: resto }]);
    const total = fatias.reduce((s, x) => s + x.sacas, 0) || 1;
    const r = 52;
    const c = 2 * Math.PI * r;
    let acumulado = 0;
    const arcos = fatias.map((x, i) => {
      const parte = x.sacas / total;
      const arco = `<circle r="${r}" cx="70" cy="70" fill="none" stroke="${cores[i % cores.length]}"
        stroke-width="22" stroke-dasharray="${Math.max(parte * c - 1.5, 0.5)} ${c}"
        stroke-dashoffset="${-acumulado * c}" transform="rotate(-90 70 70)"><title>${UI.escapar(x.rotulo)}: ${UI.numero(x.sacas, 0)} sc</title></circle>`;
      acumulado += parte;
      return arco;
    }).join('');
    return `<div class="rosca">
      <svg viewBox="0 0 140 140" role="img" aria-label="Saldo por safra">${arcos}
        <text x="70" y="66" text-anchor="middle" class="rosca-total">${UI.numero(total, 0)}</text>
        <text x="70" y="82" text-anchor="middle" class="rosca-rotulo">sacas</text></svg>
      <ul class="rosca-legenda">${fatias.map((x, i) => `<li><i style="background:${cores[i % cores.length]}"></i>
        <span>${UI.escapar(x.rotulo)}</span><b>${UI.numero(x.sacas, 0)} sc</b>
        <em>${UI.numero(x.sacas / total * 100, 1)}%</em></li>`).join('')}</ul></div>`;
  },

  ocupacao(lista) {
    if (!lista || !lista.length) return '<div class="vazio">Nenhum armazém ativo.</div>';
    return `<div class="ocupacao">${lista.map((a) => {
      const pct = a.ocupacao;
      const largura = pct === null ? 0 : Math.min(pct, 100);
      const cor = pct === null ? 'var(--cinza-300)' : pct > 90 ? 'var(--vermelho)' : pct > 70 ? 'var(--ambar)' : 'var(--primaria)';
      return `<div class="ocupacao-linha">
        <div><b>${UI.escapar(a.rotulo)}</b>
          <span class="mini">${UI.numero(a.sacas, 0)} sc${a.capacidade ? ` de ${UI.numero(a.capacidade, 0)}` : ' · sem capacidade cadastrada'}</span></div>
        <div class="ocupacao-trilho"><i style="width:${largura}%;background:${cor}"></i></div>
        <b class="ocupacao-pct">${pct === null ? '—' : `${UI.numero(pct, 1)}%`}</b></div>`;
    }).join('')}</div>`;
  },

  /* ------------------------------------------------------------ relatório */
  relatorio() {
    const d = WMSRelatorios._dados;
    const t = d.totais;
    const aba = WMSRelatorios._aba;
    const sc = (v) => `${UI.numero(v, 0)} sc`;
    let kpis;
    if (aba === 'servicos') {
      kpis = [
        WMS.cartao('Guias de serviço', String(t.guias), `${t.clientes} cliente(s)`, 'azul'),
        WMS.cartao('Despejado', sc(t.despejo), 'café que entrou no serviço', ''),
        WMS.cartao('Resultado', sc(t.resultado), 'lotes gerados', 'verde'),
        WMS.cartao('Quebra', sc(t.quebra), t.despejo ? `${UI.numero(t.quebra / t.despejo * 100, 1)}% do despejado` : '—',
          t.quebra > 0 ? 'ambar' : ''),
      ];
    } else {
      kpis = [
        WMS.cartao(aba === 'lotes' ? 'Saldo' : 'Sacas', sc(t.sacas), `${UI.numero(t.peso, 0)} kg`, 'verde'),
        WMS.cartao(aba === 'lotes' ? 'Lotes' : 'Guias', String(aba === 'lotes' ? t.lotes : t.guias),
          `${t.linhas} linha(s)`, 'azul'),
        WMS.cartao('Clientes', String(t.clientes), aba === 'transferencias' ? 'cedentes ou recebedores' : 'no filtro', ''),
        aba === 'entradas'
          ? WMS.cartao('Valor', UI.moeda(t.valor), 'sacas × valor por saca', '')
          : WMS.cartao('Grupos', String(d.grupos.length), `por ${d.agrupar_rotulo.toLowerCase()}`, ''),
      ];
    }
    const grupos = d.grupos;
    const grafico = d.agrupar === 'mes'
      ? UI.graficoColunas(grupos.map((g) => ({ periodo: g.rotulo, sacas: g.sacas, resultado: g.resultado })), {
        series: aba === 'servicos'
          ? [{ campo: 'sacas', rotulo: 'Despejado', cor: WMSRelatorios.CORES.saidas },
            { campo: 'resultado', rotulo: 'Resultado', cor: WMSRelatorios.CORES.entradas }]
          : [{ campo: 'sacas', rotulo: 'Sacas', cor: 'var(--primaria)' }],
        formato: (v) => UI.numero(v, 0), altura: 220 })
      : UI.graficoRanking(grupos, { campo: 'sacas', formato: sc, limite: 12 });
    return `
      <div class="grade g4" style="margin-bottom:14px">${kpis.join('')}</div>
      <div class="grade g2 rel-grade">
        <div class="cartao"><div class="cartao-cabecalho"><div><h3>${aba === 'servicos' ? 'Despejado' : 'Sacas'} por ${UI.escapar(d.agrupar_rotulo.toLowerCase())}</h3>
          ${grupos.length > 12 && d.agrupar !== 'mes' ? `<div class="mini">os 12 maiores de ${grupos.length}</div>` : ''}</div></div>
          <div class="cartao-corpo">${grafico}</div></div>
        <div class="cartao"><div class="cartao-cabecalho"><h3>Resumo</h3></div>
          <div class="cartao-corpo sem-padding">${WMSRelatorios.resumo()}</div></div>
      </div>
      <div class="cartao">
        <div class="cartao-cabecalho"><div><h3>Detalhe</h3>
          <div class="mini">${t.linhas} linha(s) — o Excel e o PDF levam todas</div></div></div>
        <div class="cartao-corpo sem-padding" id="rel-detalhe">${WMSRelatorios.detalhe()}</div>
      </div>`;
  },

  resumo() {
    const d = WMSRelatorios._dados;
    const total = d.totais.sacas || 0;
    const servicos = d.tipo === 'servicos';
    const colunas = [
      { titulo: d.agrupar_rotulo, valor: (g) => `<b>${UI.escapar(g.rotulo)}</b>` },
      { titulo: 'Linhas', classe: 'direita', valor: (g) => String(g.linhas) },
      ...(servicos ? [
        { titulo: 'Despejado', classe: 'direita', valor: (g) => UI.numero(g.despejo, 2) },
        { titulo: 'Resultado', classe: 'direita', valor: (g) => UI.numero(g.resultado, 2) },
        { titulo: 'Quebra', classe: 'direita', valor: (g) => UI.numero(g.quebra, 2) },
      ] : [
        { titulo: 'Sacas', classe: 'direita', valor: (g) => `<b>${UI.numero(g.sacas, 2)}</b>` },
        { titulo: 'Peso (kg)', classe: 'direita', valor: (g) => UI.numero(g.peso, 0) },
      ]),
      { titulo: '%', classe: 'direita', valor: (g) => `${UI.numero(total ? g.sacas / total * 100 : 0, 1)}%` },
    ];
    return UI.tabela({ colunas, linhas: d.grupos, vazio: 'Nada neste filtro.' });
  },

  detalhe() {
    const d = WMSRelatorios._dados;
    const limite = 300;
    const linhas = WMSRelatorios._detalheTodo ? d.linhas : d.linhas.slice(0, limite);
    const fmt = (c, v) => {
      if (c.formato === 'd') return v ? UI.data(v) : '';
      if (c.formato === 'n') return UI.numero(v, 2);
      if (c.formato === 'm') return UI.moeda(v);
      if (c.chave === 'movimento') return `<span class="tag ${v === 'Resultado' ? 'tag-pago' : 'tag-parcial'}">${UI.escapar(v)}</span>`;
      return UI.escapar(v ?? '');
    };
    const tabela = UI.tabela({
      colunas: d.colunas.map((c) => ({
        titulo: c.titulo, classe: ['n', 'm'].includes(c.formato) ? 'direita' : '',
        valor: (l) => fmt(c, l[c.chave]),
      })),
      linhas,
      vazio: 'Nenhum movimento com estes filtros.',
    });
    const resto = d.linhas.length - linhas.length;
    return tabela + (resto > 0 ? `<div class="espaco" style="padding:12px 16px">
      <span class="mini">mostrando ${linhas.length} de ${d.linhas.length}</span>
      <button class="btn btn-mini" id="rel-mais">Mostrar todas</button></div>` : '');
  },
};
