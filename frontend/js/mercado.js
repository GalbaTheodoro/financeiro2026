/* Painel "Mercado do Café" (/mercado): bolsas com histórico e filtro de período,
   preços por cidade e notícias do café e do agro com filtro por região e cultura. */
const Mercado = {
  API: '/api/publico',
  resumo: null,
  estado: {
    aba: 'bolsas',
    serie: 'ny', item: '', dias: 30, de: '', ate: '', linhas: [],
    tipo: '', cidade: '', data: '', foco: false, linhasCidade: [],
    cultura: '', regiao: '', busca: '', nde: '', nate: '',
  },

  /* ---------------------------------------------------------------- utilidades */
  $(id) { return document.getElementById(id); },
  esc(t) { return UI.escapar(t); },

  async pegar(caminho) {
    const r = await fetch(Mercado.API + caminho);
    let corpo = null;
    try { corpo = await r.json(); } catch { corpo = null; }
    if (!r.ok) throw new Error((corpo && corpo.detail) || `Erro ${r.status}`);
    return corpo;
  },

  casas(grupo) {
    if (grupo === 'londres') return 0;
    if (grupo === 'moedas') return 4;
    return 2;
  },

  num(v, casas = 2) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
    return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
  },

  classe(v) {
    const n = Number(v || 0);
    return n > 0 ? 'sobe' : n < 0 ? 'desce' : 'igual';
  },

  variacao(v, tipo, grupo) {
    if (v === null || v === undefined) return '<span class="igual">—</span>';
    const n = Number(v);
    const seta = n > 0 ? '▲' : n < 0 ? '▼' : '■';
    const casas = tipo === '%' ? 2 : tipo === 'valor' ? 4 : Mercado.casas(grupo);
    return `<span class="${Mercado.classe(n)}">${seta} ${n > 0 ? '+' : ''}${Mercado.num(n, casas)}${tipo === '%' ? '%' : ''}</span>`;
  },

  isoLocal(d) {
    const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
    return z.toISOString().slice(0, 10);
  },

  diasAtras(n) {
    const d = new Date();
    d.setDate(d.getDate() - n);
    return Mercado.isoLocal(d);
  },

  quando(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const minutos = Math.round((Date.now() - d.getTime()) / 60000);
    if (minutos < 60) return `há ${Math.max(1, minutos)} min`;
    if (minutos < 24 * 60) return `há ${Math.round(minutos / 60)} h`;
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
  },

  vencido(rotulo) {
    // 'Dezembro/26' -> já passou do mês de entrega?
    const meses = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
    const m = /^([A-Za-zçÇ]+)\/(\d{2,4})/.exec(rotulo || '');
    if (!m) return false;
    const mes = meses.indexOf(m[1].slice(0, 3).toLowerCase()) + 1;
    let ano = Number(m[2]);
    if (ano < 100) ano += 2000;
    const hoje = new Date();
    return ano * 100 + mes <= hoje.getFullYear() * 100 + hoje.getMonth() + 1;
  },

  grupo(chave) {
    return (Mercado.resumo?.grupos || []).find((g) => g.chave === chave);
  },

  /* ---------------------------------------------------------------- início */
  async iniciar() {
    document.querySelectorAll('.mc-abas button').forEach((b) =>
      b.addEventListener('click', () => Mercado.abrirAba(b.dataset.aba, true)));
    Mercado.$('mc-recarregar').addEventListener('click', () => Mercado.carregar());
    Mercado.ligarBolsas();
    Mercado.ligarCidades();
    Mercado.ligarNoticias();
    const aba = (location.hash || '').replace('#', '');
    Mercado.abrirAba(['bolsas', 'cidades', 'noticias'].includes(aba) ? aba : 'bolsas', false);
    window.addEventListener('hashchange', () => {
      const a = location.hash.replace('#', '');
      if (['bolsas', 'cidades', 'noticias'].includes(a)) Mercado.abrirAba(a, false);
    });
    let espera;
    window.addEventListener('resize', () => {
      clearTimeout(espera);
      espera = setTimeout(() => { Mercado.desenharGraficoBolsa(); Mercado.desenharGraficoCidade(); }, 200);
    });
    await Mercado.carregar();
    setInterval(Mercado.carregarAgora, 5 * 60 * 1000);
  },

  abrirAba(aba, mudarHash) {
    Mercado.estado.aba = aba;
    document.querySelectorAll('.mc-abas button').forEach((b) =>
      b.setAttribute('aria-selected', String(b.dataset.aba === aba)));
    ['bolsas', 'cidades', 'noticias'].forEach((a) => Mercado.$(`aba-${a}`).classList.toggle('oculto', a !== aba));
    if (mudarHash) history.replaceState(null, '', `#${aba}`);
    if (aba === 'noticias' && !Mercado.noticiasCarregadas) Mercado.carregarNoticias();
    if (aba === 'bolsas') Mercado.desenharGraficoBolsa();
    if (aba === 'cidades') Mercado.desenharGraficoCidade();
  },

  async carregar() {
    Mercado.$('mc-atualizado').textContent = 'Atualizando…';
    Mercado.carregarAgora();
    try {
      Mercado.resumo = await Mercado.pegar('/mercado/resumo');
    } catch (erro) {
      Mercado.$('mc-atualizado').textContent = 'Não foi possível carregar';
      Mercado.$('g-grafico').innerHTML = `<div class="mc-vazio">${Mercado.esc(erro.message)}</div>`;
      return;
    }
    const r = Mercado.resumo;
    Mercado.$('mc-atualizado').textContent = r.atualizado_em
      ? `Atualizado ${Mercado.quando(r.atualizado_em)}` : 'Sem atualização ainda';
    Mercado.montarSeries();
    Mercado.montarCidades();
    await Mercado.carregarHistorico();
    if (Mercado.noticiasCarregadas) Mercado.carregarNoticias();
  },

  /* ---------------------------------------------------------------- agora (faixa) */
  async carregarAgora() {
    const area = Mercado.$('mc-agora');
    try {
      const dados = await Mercado.pegar('/cotacoes');
      if (!dados.ativo || !dados.grupos.length) {
        area.innerHTML = '<div class="mc-vazio-escuro">Cotações de agora indisponíveis no momento.</div>';
        return;
      }
      area.innerHTML = dados.grupos.map((g) => `
        <div class="mc-bloco">
          <h4>${Mercado.esc(g.titulo)} <small>${Mercado.esc(g.unidade || '')}</small></h4>
          <ul>${g.itens.map((i) => {
            const casas = g.chave === 'londres' ? 0 : g.chave === 'moedas' ? (i.contrato === 'DXY' ? 2 : 4) : 2;
            const tipo = i.tipo_variacao === '%' ? '%' : 'n';
            const v = Number(i.variacao || 0);
            const txt = `${v > 0 ? '+' : ''}${Mercado.num(v, tipo === '%' ? 2 : casas)}${tipo === '%' ? '%' : ''}`;
            return `<li><span>${Mercado.esc(i.contrato)}</span><b>${Mercado.num(i.cotacao, casas)}</b>
              <span class="mc-var ${Mercado.classe(v)}">${txt}</span></li>`;
          }).join('')}</ul>
          <div class="mc-ref">${Mercado.esc(g.atrasado ? 'último valor disponível' : (g.referencia || ''))}</div>
        </div>`).join('');
    } catch {
      area.innerHTML = '<div class="mc-vazio-escuro">Cotações de agora indisponíveis no momento.</div>';
    }
  },

  /* ---------------------------------------------------------------- bolsas */
  ligarBolsas() {
    const e = Mercado.estado;
    Mercado.$('f-serie').addEventListener('change', (ev) => {
      e.serie = ev.target.value;
      e.item = '';
      Mercado.montarItens();
      Mercado.carregarHistorico();
    });
    Mercado.$('f-item').addEventListener('change', (ev) => {
      e.item = ev.target.value;
      Mercado.desenharUltimo();
      Mercado.carregarHistorico();
    });
    document.querySelectorAll('.mc-periodos button').forEach((b) => b.addEventListener('click', () => {
      e.dias = Number(b.dataset.dias);
      Mercado.$('f-de').value = e.dias ? Mercado.diasAtras(e.dias) : '';
      Mercado.$('f-ate').value = '';
      Mercado.carregarHistorico();
    }));
    ['f-de', 'f-ate'].forEach((id) => Mercado.$(id).addEventListener('change', () => {
      e.dias = -1;  // período personalizado
      Mercado.carregarHistorico();
    }));
    Mercado.$('f-de').value = Mercado.diasAtras(30);
    Mercado.$('b-csv').addEventListener('click', Mercado.baixarCsv);
  },

  montarSeries() {
    const sel = Mercado.$('f-serie');
    const grupos = Mercado.resumo.grupos;
    const bolsas = grupos.filter((g) => g.categoria === 'bolsa');
    const fisicos = grupos.filter((g) => g.categoria === 'fisico');
    const opcao = (g) => `<option value="${g.chave}">${Mercado.esc(g.titulo)}</option>`;
    sel.innerHTML = `<optgroup label="Bolsas e indicadores">${bolsas.map(opcao).join('')}</optgroup>
      <optgroup label="Mercado físico (por cidade)">${fisicos.map(opcao).join('')}</optgroup>`;
    if (!Mercado.grupo(Mercado.estado.serie) && grupos.length) Mercado.estado.serie = grupos[0].chave;
    sel.value = Mercado.estado.serie;
    Mercado.montarItens();
  },

  montarItens() {
    const e = Mercado.estado;
    const g = Mercado.grupo(e.serie);
    const sel = Mercado.$('f-item');
    if (!g) { sel.innerHTML = ''; return; }
    const atuais = g.itens.map((i) => i.item);
    const lista = g.todos_itens.filter((i) => g.categoria !== 'bolsa' || !Mercado.vencido(i) || atuais.includes(i));
    sel.innerHTML = lista.map((i) => `<option>${Mercado.esc(i)}</option>`).join('');
    if (!lista.includes(e.item)) {
      const vivo = g.itens.find((i) => g.categoria !== 'bolsa' || !Mercado.vencido(i.item));
      e.item = (vivo || g.itens[0] || {}).item || lista[0] || '';
    }
    sel.value = e.item;
    Mercado.desenharUltimo();
  },

  desenharUltimo() {
    const e = Mercado.estado;
    const g = Mercado.grupo(e.serie);
    if (!g) return;
    Mercado.$('u-titulo').textContent = g.titulo;
    Mercado.$('u-data').textContent = `Último fechamento: ${UI.data(g.data)} · ${g.unidade}`
      + (g.situacao === 'indisponível' ? ' · fonte fora do ar agora, mostrando o último valor' : '');
    const casas = Mercado.casas(g.chave);
    Mercado.$('u-tabela').innerHTML = `<table><tbody>${g.itens.map((i) => `
      <tr data-item="${Mercado.esc(i.item)}" class="${i.item === e.item ? 'sel' : ''}" title="Ver o histórico">
        <td>${Mercado.esc(i.item)}</td>
        <td class="num"><b>${Mercado.num(i.valor, casas)}</b></td>
        <td class="num">${Mercado.variacao(i.variacao, i.tipo_variacao, g.chave)}</td>
      </tr>`).join('')}</tbody></table>`;
    Mercado.$('u-tabela').querySelectorAll('tr').forEach((tr) => tr.addEventListener('click', () => {
      e.item = tr.dataset.item;
      Mercado.$('f-item').value = e.item;
      Mercado.desenharUltimo();
      Mercado.carregarHistorico();
    }));
  },

  async carregarHistorico() {
    const e = Mercado.estado;
    const g = Mercado.grupo(e.serie);
    document.querySelectorAll('.mc-periodos button').forEach((b) =>
      b.classList.toggle('ativo', Number(b.dataset.dias) === e.dias));
    if (!g || !e.item) {
      Mercado.$('g-grafico').innerHTML = '<div class="mc-vazio">Ainda não há cotações gravadas. Tente atualizar em alguns minutos.</div>';
      return;
    }
    const de = Mercado.$('f-de').value;
    const ate = Mercado.$('f-ate').value;
    const params = new URLSearchParams({ grupo: e.serie, item: e.item });
    params.set('de', de || '2000-01-01');
    if (ate) params.set('ate', ate);
    Mercado.$('g-grafico').innerHTML = '<div class="mc-vazio">Carregando…</div>';
    try {
      const dados = await Mercado.pegar(`/mercado/historico?${params}`);
      e.linhas = dados.linhas.slice().reverse();  // mais antigo primeiro
    } catch (erro) {
      e.linhas = [];
      Mercado.$('g-grafico').innerHTML = `<div class="mc-vazio">${Mercado.esc(erro.message)}</div>`;
      return;
    }
    Mercado.$('g-titulo').textContent = `${g.titulo} · ${e.item}`;
    const periodo = de || ate ? `${de ? UI.data(de) : 'início'} a ${ate ? UI.data(ate) : 'hoje'}` : 'todo o histórico';
    Mercado.$('g-sub').textContent = `${g.unidade} · ${periodo} · ${e.linhas.length} fechamento(s)`;
    Mercado.$('g-fonte').textContent = `Fonte: ${g.fonte}. O histórico cresce a cada dia: o painel guarda todos os fechamentos que lê.`;
    Mercado.desenharNumeros();
    Mercado.desenharGraficoBolsa();
    Mercado.desenharTabelaHistorico();
  },

  desenharNumeros() {
    const e = Mercado.estado;
    const casas = Mercado.casas(e.serie);
    const l = e.linhas;
    if (!l.length) { Mercado.$('g-numeros').innerHTML = ''; return; }
    const valores = l.map((x) => x.valor);
    const ultimo = l[l.length - 1].valor;
    const primeiro = l[0].valor;
    const dif = ultimo - primeiro;
    const pct = primeiro ? (dif / primeiro) * 100 : 0;
    Mercado.$('g-numeros').innerHTML = `
      <div><small>Último</small><b>${Mercado.num(ultimo, casas)}</b></div>
      <div><small>No período</small><b class="mc-var ${Mercado.classe(dif)}">${dif > 0 ? '+' : ''}${Mercado.num(pct, 2)}%</b></div>
      <div><small>Máxima</small><b>${Mercado.num(Math.max(...valores), casas)}</b></div>
      <div><small>Mínima</small><b>${Mercado.num(Math.min(...valores), casas)}</b></div>`;
  },

  desenharGraficoBolsa() {
    const e = Mercado.estado;
    if (e.aba !== 'bolsas') return;
    Mercado.grafico(Mercado.$('g-grafico'), e.linhas, Mercado.casas(e.serie));
  },

  desenharTabelaHistorico() {
    const e = Mercado.estado;
    const casas = Mercado.casas(e.serie);
    if (!e.linhas.length) {
      Mercado.$('h-tabela').innerHTML = '<div class="mc-vazio">Nenhum fechamento nesse período.</div>';
      return;
    }
    Mercado.$('h-tabela').innerHTML = `<table><thead><tr><th>Data</th><th>Item</th>
      <th class="num">Cotação</th><th class="num">Variação</th></tr></thead><tbody>
      ${e.linhas.slice().reverse().map((x) => `<tr><td>${UI.data(x.data)}</td><td>${Mercado.esc(x.item)}</td>
        <td class="num">${Mercado.num(x.valor, casas)}</td>
        <td class="num">${Mercado.variacao(x.variacao, x.tipo_variacao, x.grupo)}</td></tr>`).join('')}
      </tbody></table>`;
  },

  baixarCsv() {
    const e = Mercado.estado;
    if (!e.linhas.length) return;
    const g = Mercado.grupo(e.serie);
    const br = (v) => (v === null || v === undefined ? '' : String(v).replace('.', ','));
    const linhas = [['Data', 'Série', 'Item', 'Cidade', 'Cotação', 'Variação', 'Tipo da variação', 'Unidade']];
    e.linhas.forEach((x) => linhas.push([UI.data(x.data), g.titulo, x.item, x.cidade || '', br(x.valor),
      br(x.variacao), x.tipo_variacao || '', g.unidade]));
    const csv = linhas.map((l) => l.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(';')).join('\r\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `cotacoes-${e.serie}-${e.item.replace(/[^\w]+/g, '-')}.csv`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  },

  /* ---------------------------------------------------------------- gráfico de linha (SVG) */
  grafico(area, linhas, casas) {
    if (!area) return;
    if (!linhas.length) {
      area.innerHTML = '<div class="mc-vazio">Nenhum fechamento nesse período.</div>';
      return;
    }
    const largura = Math.max(280, area.clientWidth || 600);
    const altura = window.innerWidth <= 640 ? 220 : 260;
    const m = { e: 58, d: 14, t: 12, b: 28 };
    const w = largura - m.e - m.d;
    const h = altura - m.t - m.b;
    const valores = linhas.map((l) => l.valor);
    let min = Math.min(...valores);
    let max = Math.max(...valores);
    if (min === max) { min -= Math.abs(min) * 0.01 || 1; max += Math.abs(max) * 0.01 || 1; }
    const folga = (max - min) * 0.08;
    min -= folga; max += folga;
    const passo = Mercado.passoBonito((max - min) / 4);
    const y0 = Math.floor(min / passo) * passo;
    const y1 = Math.ceil(max / passo) * passo;
    const x = (i) => m.e + (linhas.length === 1 ? w / 2 : (i / (linhas.length - 1)) * w);
    const y = (v) => m.t + h - ((v - y0) / (y1 - y0)) * h;
    const casasEixo = passo < 1 ? Math.min(4, Math.ceil(-Math.log10(passo))) : 0;

    let grade = '';
    for (let v = y0; v <= y1 + passo / 2; v += passo) {
      grade += `<line class="grade" x1="${m.e}" x2="${m.e + w}" y1="${y(v)}" y2="${y(v)}"/>
        <text class="eixo" x="${m.e - 8}" y="${y(v) + 4}" text-anchor="end">${Mercado.num(v, casasEixo)}</text>`;
    }
    const nRotulos = Math.min(linhas.length, largura < 480 ? 3 : 6);
    const indices = new Set();
    for (let k = 0; k < nRotulos; k++) indices.add(Math.round((k / Math.max(1, nRotulos - 1)) * (linhas.length - 1)));
    const rotulos = [...indices].map((i) => {
      const [, mm, dd] = linhas[i].data.split('-');
      const ancora = i === 0 ? 'start' : i === linhas.length - 1 ? 'end' : 'middle';
      return `<text class="eixo" x="${x(i)}" y="${altura - 8}" text-anchor="${linhas.length === 1 ? 'middle' : ancora}">${dd}/${mm}</text>`;
    }).join('');
    const pontos = linhas.map((l, i) => `${x(i).toFixed(1)},${y(l.valor).toFixed(1)}`);
    const caminho = `M${pontos.join('L')}`;
    const areaPath = `${caminho}L${x(linhas.length - 1).toFixed(1)},${m.t + h}L${x(0).toFixed(1)},${m.t + h}Z`;
    const ultimo = linhas.length - 1;

    area.innerHTML = `<svg viewBox="0 0 ${largura} ${altura}" role="img"
        aria-label="Gráfico de ${linhas.length} fechamentos, de ${UI.data(linhas[0].data)} a ${UI.data(linhas[ultimo].data)}">
        ${grade}${rotulos}
        <path class="area" d="${areaPath}"/>
        <path class="linha" d="${caminho}"/>
        ${linhas.length <= 40 ? linhas.map((l, i) => `<circle class="ponto" cx="${x(i)}" cy="${y(l.valor)}" r="${i === ultimo ? 4.5 : 3}"/>`).join('') : `<circle class="ponto" cx="${x(ultimo)}" cy="${y(linhas[ultimo].valor)}" r="4.5"/>`}
        <line class="mira oculto" y1="${m.t}" y2="${m.t + h}"/>
        <circle class="ponto destaque oculto" r="5"/>
        <rect x="${m.e}" y="${m.t}" width="${w}" height="${h}" fill="transparent" class="alvo"/>
      </svg><div class="mc-dica oculto"></div>`;

    const svg = area.querySelector('svg');
    const mira = svg.querySelector('.mira');
    const marca = svg.querySelector('.destaque');
    const dica = area.querySelector('.mc-dica');
    const mover = (ev) => {
      const caixa = svg.getBoundingClientRect();
      const px = ((ev.clientX - caixa.left) / caixa.width) * largura;
      const i = linhas.length === 1 ? 0
        : Math.max(0, Math.min(linhas.length - 1, Math.round(((px - m.e) / w) * (linhas.length - 1))));
      const l = linhas[i];
      mira.setAttribute('x1', x(i)); mira.setAttribute('x2', x(i));
      marca.setAttribute('cx', x(i)); marca.setAttribute('cy', y(l.valor));
      mira.classList.remove('oculto'); marca.classList.remove('oculto');
      dica.innerHTML = `${UI.data(l.data)} · <b>${Mercado.num(l.valor, casas)}</b>`
        + (l.variacao !== null && l.variacao !== undefined ? ` · ${Mercado.variacao(l.variacao, l.tipo_variacao, l.grupo)}` : '');
      dica.classList.remove('oculto');
      const esc = caixa.width / largura;
      let esquerda = x(i) * esc;
      esquerda = Math.max(70, Math.min(caixa.width - 70, esquerda));
      dica.style.left = `${esquerda}px`;
      dica.style.top = `${y(l.valor) * esc}px`;
    };
    const sair = () => { mira.classList.add('oculto'); marca.classList.add('oculto'); dica.classList.add('oculto'); };
    const alvo = svg.querySelector('.alvo');
    alvo.addEventListener('pointermove', mover);
    alvo.addEventListener('pointerdown', mover);
    alvo.addEventListener('pointerleave', sair);
  },

  passoBonito(bruto) {
    const pot = 10 ** Math.floor(Math.log10(bruto || 1));
    const n = bruto / pot;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * pot;
  },

  /* ---------------------------------------------------------------- preços por cidade */
  ligarCidades() {
    const e = Mercado.estado;
    Mercado.$('c-tipo').addEventListener('change', (ev) => { e.tipo = ev.target.value; Mercado.desenharCidades(); });
    Mercado.$('c-cidade').addEventListener('change', (ev) => { e.cidade = ev.target.value; Mercado.desenharCidades(); });
    Mercado.$('c-foco').addEventListener('change', (ev) => { e.foco = ev.target.checked; Mercado.desenharCidades(); });
    Mercado.$('c-data').addEventListener('change', async (ev) => { e.data = ev.target.value; await Mercado.carregarDataCidades(); });
    Mercado.$('ch-item').addEventListener('change', Mercado.desenharGraficoCidade);
  },

  gruposFisicos() {
    return (Mercado.resumo?.grupos || []).filter((g) => g.categoria === 'fisico');
  },

  montarCidades() {
    const r = Mercado.resumo;
    const e = Mercado.estado;
    Mercado.$('c-tipo').innerHTML = '<option value="">Todos os tipos</option>'
      + Mercado.gruposFisicos().map((g) => `<option value="${g.chave}">${Mercado.esc(g.titulo)}</option>`).join('');
    Mercado.$('c-tipo').value = e.tipo;
    Mercado.$('c-cidade').innerHTML = '<option value="">Todas as cidades</option>'
      + `<optgroup label="Região em destaque">${r.cidades_foco.map((c) => `<option>${Mercado.esc(c)}</option>`).join('')}</optgroup>`
      + `<optgroup label="Outras praças">${r.cidades.filter((c) => !r.cidades_foco.includes(c)).map((c) => `<option>${Mercado.esc(c)}</option>`).join('')}</optgroup>`;
    Mercado.$('c-cidade').value = e.cidade;
    if (e.data) {
      Mercado.carregarDataCidades();
    } else {
      e.linhasCidade = Mercado.gruposFisicos().flatMap((g) => g.itens);
      Mercado.desenharCidades();
    }
  },

  async carregarDataCidades() {
    const e = Mercado.estado;
    if (!e.data) {
      e.linhasCidade = Mercado.gruposFisicos().flatMap((g) => g.itens);
      Mercado.desenharCidades();
      return;
    }
    Mercado.$('c-lista').innerHTML = '<div class="mc-vazio">Carregando…</div>';
    const partes = await Promise.all(Mercado.gruposFisicos().map((g) =>
      Mercado.pegar(`/mercado/historico?${new URLSearchParams({ grupo: g.chave, de: e.data, ate: e.data })}`)
        .then((d) => d.linhas).catch(() => [])));
    e.linhasCidade = partes.flat();
    Mercado.desenharCidades();
  },

  rotuloItem(linha) {
    if (linha.grupo === 'agnocafe') return linha.item.split(' · ').slice(1).join(' · ');
    const coop = /\(([^)]+)\)/.exec(linha.item);
    if (linha.grupo === 'conilon_es') return linha.item.split(' · ').slice(1).join(' · ') || linha.item;
    return coop ? coop[1] : linha.item;
  },

  desenharCidades() {
    const r = Mercado.resumo;
    const e = Mercado.estado;
    if (!r) return;
    const titulos = Object.fromEntries(r.grupos.map((g) => [g.chave, g.titulo]));
    let linhas = e.linhasCidade.filter((l) => l.cidade);
    if (e.tipo) linhas = linhas.filter((l) => l.grupo === e.tipo);
    const porCidade = {};
    linhas.forEach((l) => { (porCidade[l.cidade] = porCidade[l.cidade] || []).push(l); });
    let cidades = [...r.cidades_foco, ...Object.keys(porCidade).filter((c) => !r.cidades_foco.includes(c))
      .sort((a, b) => a.localeCompare(b, 'pt-BR'))];
    if (e.foco) cidades = cidades.filter((c) => r.cidades_foco.includes(c));
    if (e.cidade) cidades = cidades.filter((c) => c === e.cidade);

    const dataTxt = e.data ? `em ${UI.data(e.data)}` : 'no último fechamento de cada fonte';
    Mercado.$('c-nota').textContent = `Preço da saca de 60 kg ${dataTxt}. Cidades da região em destaque aparecem primeiro, em laranja.`
      + (e.data ? '' : ' A AgnoCafé não publica data: vale o dia em que o painel leu.');

    if (!cidades.length) {
      Mercado.$('c-lista').innerHTML = '<div class="mc-vazio">Nenhuma cotação com esses filtros.</div>';
      return;
    }
    Mercado.$('c-lista').innerHTML = cidades.map((cidade) => {
      const itens = (porCidade[cidade] || []).slice().sort((a, b) =>
        r.grupos.findIndex((g) => g.chave === a.grupo) - r.grupos.findIndex((g) => g.chave === b.grupo));
      const foco = r.cidades_foco.includes(cidade);
      let corpo;
      if (!itens.length) {
        corpo = `<div class="mc-vazio">Nenhuma das fontes publicou cotação de ${Mercado.esc(cidade)}
          ${e.data ? 'nesse dia' : 'no último fechamento'}${e.tipo ? ' para esse tipo' : ''}.</div>`;
      } else {
        let grupoAtual = '';
        corpo = `<table><tbody>${itens.map((l) => {
          let cab = '';
          if (l.grupo !== grupoAtual) {
            grupoAtual = l.grupo;
            cab = `<tr><td class="tipo" colspan="3">${Mercado.esc(titulos[l.grupo] || l.grupo)} · ${UI.data(l.data)}</td></tr>`;
          }
          return `${cab}<tr><td>${Mercado.esc(Mercado.rotuloItem(l))}</td>
            <td class="num"><b>R$ ${Mercado.num(l.valor, 2)}</b></td>
            <td class="num">${l.variacao === null || l.variacao === undefined ? '' : Mercado.variacao(l.variacao, l.tipo_variacao, l.grupo)}</td></tr>`;
        }).join('')}</tbody></table>`;
      }
      return `<article class="mc-cidade ${foco ? 'foco' : ''}">
        <header><h3>${Mercado.esc(cidade)}</h3><small>${itens.length} cotação(ões)</small></header>
        ${corpo}
        <footer><small>${[...new Set(itens.map((l) => l.grupo === 'agnocafe' ? 'AgnoCafé' : 'Notícias Agrícolas'))].join(' · ')}</small>
          <button class="btn btn-sm" type="button" data-cidade="${Mercado.esc(cidade)}">📈 Histórico</button></footer>
      </article>`;
    }).join('');
    Mercado.$('c-lista').querySelectorAll('button[data-cidade]').forEach((b) =>
      b.addEventListener('click', () => Mercado.historicoCidade(b.dataset.cidade)));
  },

  async historicoCidade(cidade) {
    const quadro = Mercado.$('c-historico');
    quadro.classList.remove('oculto');
    Mercado.$('ch-titulo').textContent = `Histórico — ${cidade}`;
    Mercado.$('ch-grafico').innerHTML = '<div class="mc-vazio">Carregando…</div>';
    quadro.scrollIntoView({ behavior: 'smooth', block: 'start' });
    try {
      const d = await Mercado.pegar(`/mercado/historico?${new URLSearchParams({ cidade, de: Mercado.diasAtras(90) })}`);
      Mercado.linhasHistCidade = d.linhas.slice().reverse();
    } catch (erro) {
      Mercado.linhasHistCidade = [];
      Mercado.$('ch-grafico').innerHTML = `<div class="mc-vazio">${Mercado.esc(erro.message)}</div>`;
      return;
    }
    const titulos = Object.fromEntries(Mercado.resumo.grupos.map((g) => [g.chave, g.titulo]));
    const chaves = [...new Map(Mercado.linhasHistCidade.map((l) => [`${l.grupo}|${l.item}`,
      `${titulos[l.grupo] || l.grupo} — ${Mercado.rotuloItem(l)}`])).entries()];
    Mercado.$('ch-item').innerHTML = chaves.map(([k, t]) => `<option value="${Mercado.esc(k)}">${Mercado.esc(t)}</option>`).join('');
    Mercado.desenharGraficoCidade();
  },

  desenharGraficoCidade() {
    if (Mercado.estado.aba !== 'cidades' || !Mercado.linhasHistCidade) return;
    const chave = Mercado.$('ch-item').value;
    const linhas = Mercado.linhasHistCidade.filter((l) => `${l.grupo}|${l.item}` === chave);
    if (!chave) {
      Mercado.$('ch-grafico').innerHTML = '<div class="mc-vazio">Sem histórico para essa cidade ainda.</div>';
      return;
    }
    Mercado.grafico(Mercado.$('ch-grafico'), linhas, 2);
  },

  /* ---------------------------------------------------------------- notícias */
  ligarNoticias() {
    const e = Mercado.estado;
    let espera;
    Mercado.$('n-busca').addEventListener('input', (ev) => {
      clearTimeout(espera);
      espera = setTimeout(() => { e.busca = ev.target.value; Mercado.carregarNoticias(); }, 350);
    });
    Mercado.$('n-de').addEventListener('change', (ev) => { e.nde = ev.target.value; Mercado.carregarNoticias(); });
    Mercado.$('n-ate').addEventListener('change', (ev) => { e.nate = ev.target.value; Mercado.carregarNoticias(); });
  },

  chips(id, rotulo, opcoes, atual, aoEscolher) {
    const area = Mercado.$(id);
    area.innerHTML = `<span class="rotulo">${rotulo}</span>` + opcoes.map((o) =>
      `<button type="button" class="mc-chip ${o.valor === atual ? 'ativo' : ''} ${o.foco ? 'foco' : ''}"
        data-valor="${Mercado.esc(o.valor)}" aria-pressed="${o.valor === atual}">${Mercado.esc(o.texto)}</button>`).join('');
    area.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => aoEscolher(b.dataset.valor)));
  },

  async carregarNoticias() {
    const e = Mercado.estado;
    Mercado.noticiasCarregadas = true;
    const params = new URLSearchParams();
    if (e.cultura) params.set('cultura', e.cultura);
    if (e.regiao) params.set('regiao', e.regiao);
    if (e.busca) params.set('busca', e.busca);
    if (e.nde) params.set('de', e.nde);
    if (e.nate) params.set('ate', e.nate);
    const lista = Mercado.$('n-lista');
    if (!lista.children.length) lista.innerHTML = '<div class="mc-vazio">Buscando notícias…</div>';
    let dados;
    try {
      dados = await Mercado.pegar(`/mercado/noticias?${params}`);
    } catch (erro) {
      lista.innerHTML = `<div class="mc-vazio">${Mercado.esc(erro.message)}</div>`;
      return;
    }
    Mercado.chips('n-regioes', 'Região', [
      { valor: '', texto: 'Todas' },
      { valor: 'foco', texto: 'Patrocínio, Varginha, Araguari e Patos de Minas', foco: true },
      ...dados.regioes.map((r) => ({ valor: r, texto: r, foco: ['Patrocínio', 'Varginha', 'Araguari', 'Patos de Minas'].includes(r) })),
    ], e.regiao, (v) => { e.regiao = v; Mercado.carregarNoticias(); });
    Mercado.chips('n-culturas', 'Cultura', [{ valor: '', texto: 'Todas' },
      ...dados.culturas.map((c) => ({ valor: c, texto: c }))],
    e.cultura, (v) => { e.cultura = v; Mercado.carregarNoticias(); });

    const foraDoAr = Object.values(dados.fontes || {}).filter((s) => s !== 'ok').length;
    Mercado.$('n-nota').textContent = `${dados.itens.length} notícia(s)`
      + (dados.total ? ` de ${dados.total} guardadas (até 60 dias)` : '')
      + (dados.atualizado_em ? ` · atualizado ${Mercado.quando(dados.atualizado_em)}` : '')
      + (foraDoAr ? ` · ${foraDoAr} fonte(s) fora do ar agora` : '')
      + '. Notícias da região em destaque têm a borda laranja.';
    if (!dados.itens.length) {
      lista.innerHTML = '<div class="mc-vazio">Nenhuma notícia com esses filtros. Tente outra região ou cultura.</div>';
      return;
    }
    // café e região em destaque vêm primeiro entre as do mesmo dia
    const dia = (n) => (n.quando || '').slice(0, 10);
    const itens = dados.itens.slice().sort((a, b) => {
      if (dia(a) !== dia(b)) return dia(a) < dia(b) ? 1 : -1;
      const pa = (a.foco ? 2 : 0) + (a.culturas.includes('Café') ? 1 : 0);
      const pb = (b.foco ? 2 : 0) + (b.culturas.includes('Café') ? 1 : 0);
      if (pa !== pb) return pb - pa;
      return (a.quando || '') < (b.quando || '') ? 1 : -1;
    });
    lista.innerHTML = itens.map((n) => `
      <a class="mc-noticia ${n.foco ? 'foco' : ''}" href="${Mercado.esc(n.link)}" target="_blank" rel="noopener noreferrer nofollow">
        <div class="mc-meta"><b>${Mercado.esc(n.fonte)}</b><span>${Mercado.esc(Mercado.quando(n.quando))}</span></div>
        <h3>${Mercado.esc(n.titulo)}</h3>
        ${n.resumo ? `<p>${Mercado.esc(n.resumo)}</p>` : ''}
        <div class="mc-meta">
          ${n.culturas.map((c) => `<span class="mc-etq ${c === 'Café' ? 'cafe' : ''}">${Mercado.esc(c)}</span>`).join('')}
          ${n.regioes.map((r) => `<span class="mc-etq regiao">📍 ${Mercado.esc(r)}</span>`).join('')}
        </div>
      </a>`).join('');
  },
};

document.addEventListener('DOMContentLoaded', Mercado.iniciar);
