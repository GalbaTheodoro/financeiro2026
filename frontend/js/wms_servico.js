/* WMS — Guia de serviço (tela Serviços): liga, rebenefício, catação...

   Cabeçalho: número, data, data de início e de fim, armazém, cliente,
   serviço, produto, valor cobrado e observação.

   Despejo: os lotes do cliente naquele armazém, uma linha por posição (quadra
   + pilha) com o que resta; em cada linha, quantas sacas entram no serviço —
   vários lotes, e pode ser só uma parte de cada.

   Resultado: os lotes que saem do serviço — um ou vários —, cada um com
   peneira, padrão, sacas, peso e os locais onde ficou.

   Embaixo do cabeçalho aparece a conta: despejo → resultado = quebra.
   "Fechar guia e gerar lotes" tira o despejo do saldo e cria os lotes
   resultado ("S7/1", "S7/2"...). */
const WMSServico = {
  _dados: null,
  _guia: null,
  _disp: [],
  _quadras: [],
  _filtroLote: '',
  _filtros: { de: '', ate: '', armazem_id: '', cliente_id: '', status: '', busca: '' },

  async tela() {
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';
    try {
      await WMSServico.carregar();
    } catch (e) {
      alvo.innerHTML = `<div class="cartao"><div class="vazio">${UI.escapar(e.message)}</div></div>`;
    }
  },

  async carregar() {
    const eid = Estado.empresaId;
    const [armazens, quadras, dados] = await Promise.all([
      Api.get('/api/wms/armazens', { empresa_id: eid }),
      Api.get('/api/wms/quadras', { empresa_id: eid }),
      Api.get('/api/wms/guias-servico', { empresa_id: eid, ...WMSServico._filtros }),
    ]);
    WMS._armazens = armazens;
    WMSServico._quadras = quadras;
    WMSServico._dados = dados;
    WMSServico.desenhar();
  },

  /* ------------------------------------------------------------- a lista */
  desenhar() {
    const d = WMSServico._dados || { guias: [], resumo: {} };
    const r = d.resumo || {};
    const f = WMSServico._filtros;
    const quebra = Number(r.despejo_sacas || 0) - Number(r.resultado_sacas || 0);
    document.getElementById('pagina').innerHTML = `
      <div class="grade g4" style="margin-bottom:12px">
        ${WMS.cartao('Guias', String(r.guias || 0), r.abertas ? `${r.abertas} aberta(s)` : 'no filtro abaixo', 'azul')}
        ${WMS.cartao('Despejo', `${UI.numero(r.despejo_sacas, 2)} sc`, 'entrou nos serviços fechados', '')}
        ${WMS.cartao('Resultado', `${UI.numero(r.resultado_sacas, 2)} sc`,
          `quebra ${UI.numero(quebra, 2)} sc`, 'verde')}
        ${WMS.cartao('Valor dos serviços', UI.moeda(r.valor), 'cobrado dos clientes', 'ambar')}
      </div>
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Guias de serviço</h3>
            <div class="mini">liga, rebenefício, catação... — despeja um ou vários lotes (pode ser parte) e gera um ou vários lotes resultado</div></div>
          <div class="espaco">
            <button class="btn" id="wms-saldo">Saldo do armazém</button>
            <button class="btn" id="wms-exportar">Exportar</button>
            <button class="btn btn-primario" id="wms-novo">Nova guia de serviço</button>
          </div>
        </div>
        <div class="cartao-corpo">
          <div class="linha-campos" data-nao-suja>
            ${UI.campo('De', `<input type="date" name="de" value="${f.de}">`)}
            ${UI.campo('Até', `<input type="date" name="ate" value="${f.ate}">`)}
            ${UI.campo('Armazém', UI.select('armazem_id',
              WMS._armazens.map((a) => ({ valor: a.id, rotulo: a.nome })), f.armazem_id, { vazio: 'Todos' }))}
            ${UI.campo('Cliente', UI.select('cliente_id',
              WMS.depositantes().map((p) => ({ valor: p.id, rotulo: p.nome })), f.cliente_id, { vazio: 'Todos' }))}
            ${UI.campo('Situação', UI.select('status',
              Object.entries(WMSEntrada.STATUS).map(([v, r2]) => ({ valor: v, rotulo: r2 })),
              f.status, { vazio: 'Abertas e fechadas' }))}
            ${UI.campo('Procurar', `<input name="busca" value="${UI.escapar(f.busca)}" placeholder="número, serviço, observação">`)}
          </div>
          <div id="lista-wms" style="margin-top:12px">${UI.tabela({
            vazio: 'Nenhuma guia de serviço neste filtro.',
            colunas: [
              { titulo: 'Nº', chave: 'numero', valor: (g) => `<b>${g.numero}</b>` },
              { titulo: 'Período', valor: (g) => `${UI.data(g.data_inicio || g.data)}${
                g.data_fim ? ` a ${UI.data(g.data_fim)}` : ''}<div class="mini">guia de ${UI.data(g.data)}</div>` },
              { titulo: 'Cliente', valor: (g) => `${UI.escapar(g.cliente_nome)}
                <div class="mini">${UI.escapar(g.armazem_nome)}</div>` },
              { titulo: 'Serviço', valor: (g) => `<b>${UI.escapar(g.servico || '—')}</b>
                ${Number(g.valor) ? `<div class="mini">${UI.moeda(g.valor)}</div>` : ''}` },
              { titulo: 'Despejo → resultado', valor: (g) => `<span class="mini">${UI.escapar((g.lotes_despejo || []).join(', ') || '—')}
                → <b>${UI.escapar((g.lotes_resultado || []).join(', ') || (g.status === 'ABERTA' ? 'ao fechar' : '—'))}</b></span>` },
              { titulo: 'Sacas', classe: 'direita', chave: 'sacas', valor: (g) => `${UI.numero(g.despejo_sacas, 2)} → <b>${UI.numero(g.resultado_sacas, 2)}</b>
                <div class="mini">quebra ${UI.numero(g.quebra_sacas, 2)}</div>` },
              { titulo: 'Situação', valor: (g) => WMSEntrada.tag(g.status) },
              { titulo: '', classe: 'direita', valor: (g, i) =>
                `<button class="btn btn-mini" data-abrir="${i}">${g.status === 'ABERTA' ? 'Editar' : 'Ver'}</button>` },
            ],
            linhas: d.guias,
          })}</div>
        </div>
      </div>`;
    WMSServico.ligar();
  },

  ligar() {
    const pagina = document.getElementById('pagina');
    pagina.querySelector('#wms-novo').onclick = () => WMSServico.nova();
    pagina.querySelector('#wms-saldo').onclick = () => WMS.saldo();
    pagina.querySelector('#wms-exportar').onclick = () => UI.exportarTabela('wms-guias-servico', '#lista-wms table');
    ['de', 'ate', 'armazem_id', 'cliente_id', 'status'].forEach((nome) => {
      const campo = pagina.querySelector(`[name="${nome}"]`);
      campo.onchange = () => { WMSServico._filtros[nome] = campo.value; WMSServico.carregar(); };
    });
    const busca = pagina.querySelector('[name="busca"]');
    let tempo = null;
    busca.oninput = () => {
      clearTimeout(tempo);
      tempo = setTimeout(() => { WMSServico._filtros.busca = busca.value; WMSServico.carregar(); }, 400);
    };
    pagina.querySelectorAll('[data-abrir]').forEach((b) => {
      b.onclick = () => WMSServico.abrir(WMSServico._dados.guias[Number(b.dataset.abrir)].id);
    });
  },

  /* ------------------------------------------------------------- o editor */
  resultadoVazio() {
    return { peneira: '', padrao: '', safra: '', sacas: 0, peso: 0, unidade_id: '',
      locais: [{ quadra_id: '', pilha: '', sacas: 0, peso: 0 }] };
  },

  async nova() {
    const armazens = WMS.armazensAtivos();
    if (!armazens.length) return UI.erro('Cadastre primeiro o armazém (tela Entrada > Armazéns).');
    WMSServico._guia = {
      id: null, numero: null, status: 'ABERTA', data: UI.hoje(), data_inicio: UI.hoje(), data_fim: '',
      armazem_id: armazens.length === 1 ? armazens[0].id : '', cliente_id: '', servico: '',
      produto_id: '', valor: 0, observacao: '', despejos: [], resultados: [WMSServico.resultadoVazio()],
    };
    WMSServico._filtroLote = '';
    await WMSServico.editor();
  },

  async abrir(id) {
    try { WMSServico._guia = await Api.get(`/api/wms/guias-servico/${id}`); } catch (e) { return UI.erro(e.message); }
    if (!WMSServico._guia.resultados.length) WMSServico._guia.resultados = [WMSServico.resultadoVazio()];
    WMSServico._filtroLote = '';
    await WMSServico.editor();
  },

  async editor() {
    const g = WMSServico._guia;
    UI.abrirModal({
      titulo: g.id ? `Guia de serviço nº ${g.numero}` : 'Nova guia de serviço',
      largo: true, corpo: '<div id="servico-editor"></div>', botoes: [],
      aoSalvar: g.status === 'ABERTA' ? () => WMSServico.salvar(false) : null,
    });
    await WMSServico.carregarDisponivel();
    WMSServico.render();
  },

  editavel() { return WMSServico._guia.status === 'ABERTA'; },

  async carregarDisponivel() {
    const g = WMSServico._guia;
    WMSServico._disp = [];
    if (!WMSServico.editavel() || !g.armazem_id || !g.cliente_id) return;
    try {
      WMSServico._disp = await Api.get('/api/wms/posicoes-disponiveis', {
        empresa_id: Estado.empresaId, armazem_id: g.armazem_id, cliente_id: g.cliente_id,
      });
    } catch (e) { UI.erro(e.message); }
  },

  linhasDespejo() {
    const g = WMSServico._guia;
    const porPos = {};
    (g.despejos || []).forEach((i) => { porPos[i.posicao_id] = i; });
    const linhas = WMSServico._disp.map((d) => ({ ...d, item: porPos[d.posicao_id] }));
    (g.despejos || []).forEach((i) => {
      if (!linhas.some((l) => String(l.posicao_id) === String(i.posicao_id))) {
        linhas.push({ posicao_id: i.posicao_id, lote_codigo: i.lote_codigo, peneira: i.peneira, padrao: i.padrao,
          quadra_nome: i.quadra_nome, pilha: i.pilha, sacas_disponiveis: null, peso_disponivel: null, item: i });
      }
    });
    return linhas;
  },

  v(n, casas = 2) { return Number(n) ? UI.numero(n, casas) : ''; },

  render() {
    const g = WMSServico._guia;
    const ed = WMSServico.editavel();
    const dis = ed ? '' : 'disabled';
    const deps = WMS.depositantes().map((p) => ({ valor: p.id, rotulo: p.nome }));
    const unidades = Api.unidadesAtivas().map((u) => ({ valor: u.id, rotulo: u.codigo }));
    const quadras = WMSServico._quadras
      .filter((q) => String(q.armazem_id) === String(g.armazem_id) && q.ativo)
      .map((q) => ({ valor: q.id, rotulo: q.nome }));
    const filtro = WMSServico._filtroLote.trim().toUpperCase();
    const linhas = WMSServico.linhasDespejo().filter((l) => !filtro
      || String(l.lote_codigo).toUpperCase().includes(filtro)
      || String(l.quadra_nome).toUpperCase().includes(filtro)
      || String(l.padrao || '').toUpperCase().includes(filtro));
    const servicos = (WMSServico._dados?.servicos || []).map((s) => `<option value="${UI.escapar(s)}">`).join('');

    document.getElementById('servico-editor').innerHTML = `
      ${g.status !== 'ABERTA' ? `<div class="ok-caixa" style="margin-bottom:12px">
        Guia ${WMSEntrada.STATUS[g.status].toLowerCase()}${g.status === 'FECHADA'
          ? ` — gerou o(s) lote(s) <b>${UI.escapar((g.lotes_resultado || []).join(', '))}</b>. Para mudar, reabra a guia (só dá se os lotes resultado não foram usados).`
          : '.'}</div>` : ''}
      <div class="linha-campos servico-cab">
        ${UI.campo('Número', `<input value="${g.numero || 'automático'}" disabled>`)}
        ${UI.campo('Data', `<input type="date" name="data" value="${g.data || ''}" ${dis}>`)}
        ${UI.campo('Data início', `<input type="date" name="data_inicio" value="${g.data_inicio || ''}" ${dis}>`)}
        ${UI.campo('Data fim', `<input type="date" name="data_fim" value="${g.data_fim || ''}" ${dis}>`, 'vazio = o dia em que fechar')}
        ${UI.campo('Armazém *', UI.select('armazem_id',
          WMS._armazens.filter((a) => a.ativo || String(a.id) === String(g.armazem_id))
            .map((a) => ({ valor: a.id, rotulo: a.nome })), g.armazem_id, { vazio: 'Escolha', attr: dis }))}
        ${UI.campo('Cliente *', UI.select('cliente_id', deps, g.cliente_id, { vazio: 'Escolha', attr: dis }), 'dono do café')}
        ${UI.campo('Serviço', `<input name="servico" list="servico-lista" maxlength="80" value="${UI.escapar(g.servico || '')}" placeholder="liga, rebenefício..." ${dis}>
          <datalist id="servico-lista">${servicos}</datalist>`)}
        ${UI.campo('Produto', UI.select('produto_id',
          Api.produtosAtivos().map((p) => ({ valor: p.id, rotulo: `${p.codigo} — ${p.nome}` })),
          g.produto_id, { vazio: 'o do despejo', attr: dis }))}
        ${UI.campo('Valor do serviço (R$)', `<input name="valor" inputmode="decimal" value="${WMSServico.v(g.valor)}" ${dis}>`)}
        ${UI.campo('Observação', `<input name="observacao" maxlength="500" value="${UI.escapar(g.observacao || '')}" ${dis}>`)}
      </div>

      <div id="servico-conta" class="guia-conferencia"></div>

      <div class="saida-lotes-topo">
        <h4 style="margin:0">Despejo — o que entra no serviço</h4>
        ${ed && WMSServico.linhasDespejo().length ? `<input name="filtro_lote" data-nao-suja placeholder="procurar lote, quadra, padrão"
          value="${UI.escapar(WMSServico._filtroLote)}" style="max-width:260px">` : ''}
      </div>
      ${ed && (!g.armazem_id || !g.cliente_id)
        ? '<div class="vazio">Escolha o armazém e o cliente para ver os lotes dele.</div>'
        : !linhas.length ? `<div class="vazio">${ed ? 'Este cliente não tem café com posição neste armazém.' : 'Nada despejado.'}</div>`
          : `<div class="tabela-wrap"><table class="tabela-simples saida-tabela servico-despejo">
          <thead><tr><th>Lote</th><th>Quadra</th><th>Pilha</th>${ed ? '<th style="text-align:right">Disponível</th>' : ''}
            <th style="text-align:right">Despejar (sacas)</th><th style="text-align:right">Peso (kg)</th>${ed ? '<th></th>' : ''}</tr></thead>
          <tbody>${linhas.map((l, idx, todas) => {
            const novo = idx === 0 || todas[idx - 1].lote_codigo !== l.lote_codigo;
            return `<tr data-pos="${l.posicao_id}" class="${novo ? 'saida-novo-lote' : ''}">
              <td>${novo ? `<b>${UI.escapar(l.lote_codigo)}</b>
                <div class="mini">${UI.escapar([l.peneira ? `pen. ${l.peneira}` : '', l.padrao || ''].filter(Boolean).join(' · '))}</div>` : ''}</td>
              <td>${UI.escapar(l.quadra_nome)}</td><td>${UI.escapar(l.pilha || '—')}</td>
              ${ed ? `<td class="direita">${l.sacas_disponiveis != null ? `${UI.numero(l.sacas_disponiveis, 2)} sc
                <div class="mini">${UI.numero(l.peso_disponivel, 0)} kg</div>` : '—'}</td>` : ''}
              <td class="direita"><input name="sacas" inputmode="decimal" value="${WMSServico.v(l.item?.sacas)}" style="width:95px;text-align:right" ${dis}></td>
              <td class="direita"><input name="peso" inputmode="decimal" value="${WMSServico.v(l.item?.peso)}" placeholder="${ed ? 'proporcional' : ''}" style="width:105px;text-align:right" ${dis}></td>
              ${ed ? `<td><button type="button" class="btn btn-mini" data-tudo="${l.posicao_id}" ${l.sacas_disponiveis ? '' : 'disabled'}>Tudo</button></td>` : ''}
            </tr>`;
          }).join('')}</tbody></table></div>`}

      <h4 style="margin:18px 0 8px">Resultado — os lotes que saem do serviço</h4>
      ${!quadras.length && ed ? `<div class="ok-caixa" style="margin-bottom:10px">${g.armazem_id
        ? 'Este armazém ainda não tem quadras. Cadastre em Entrada &gt; Quadras.' : 'Escolha o armazém para ver as quadras.'}</div>` : ''}
      ${(g.resultados || []).map((r, i) => `
        <div class="guia-lote" data-resultado="${i}">
          <div class="guia-lote-topo">
            <b>Lote ${r.codigo ? UI.escapar(r.codigo) : `S${g.numero || '—'}/${i + 1}`}</b>
            ${ed && g.resultados.length > 1 ? `<button type="button" class="btn btn-mini" data-tirar-resultado="${i}">Remover lote</button>` : ''}
          </div>
          <div class="linha-campos">
            ${UI.campo('Peneira', `<input name="peneira" maxlength="20" value="${UI.escapar(r.peneira || '')}" placeholder="ex.: 17/18" ${dis}>`)}
            ${UI.campo('Padrão', `<input name="padrao" maxlength="60" value="${UI.escapar(r.padrao || '')}" placeholder="ex.: liga fina" ${dis}>`)}
            ${UI.campo('Safra', `<input name="safra" maxlength="9" value="${UI.escapar(r.safra || '')}" placeholder="${ed ? 'a dos lotes despejados' : ''}" ${dis}>`)}
            ${UI.campo('Sacas *', `<input name="sacas" inputmode="decimal" value="${WMSServico.v(r.sacas)}" ${dis}>`)}
            ${UI.campo('Peso (kg)', `<input name="peso" inputmode="decimal" value="${WMSServico.v(r.peso)}" placeholder="${ed ? 'do despejo' : ''}" ${dis}>`)}
            ${UI.campo('Unidade', UI.select('unidade_id', unidades, r.unidade_id, { vazio: '—', attr: dis }))}
          </div>
          <table class="tabela-simples guia-locais-tabela" style="margin-top:6px">
            <thead><tr><th>Quadra</th><th>Pilha</th><th style="text-align:right">Sacas</th><th style="text-align:right">Peso (kg)</th><th></th></tr></thead>
            <tbody>${(r.locais || []).map((x, j) => `
              <tr data-local="${j}">
                <td>${UI.select('quadra_id', quadras.length ? quadras
                  : (x.quadra_id ? [{ valor: x.quadra_id, rotulo: x.quadra_nome || '?' }] : []), x.quadra_id, { vazio: 'Quadra', attr: dis })}</td>
                <td><input name="pilha" maxlength="20" value="${UI.escapar(x.pilha || '')}" style="text-transform:uppercase;width:90px" ${dis}></td>
                <td class="direita"><input name="sacas" inputmode="decimal" value="${WMSServico.v(x.sacas)}" style="width:95px;text-align:right" ${dis}></td>
                <td class="direita"><input name="peso" inputmode="decimal" value="${WMSServico.v(x.peso)}" placeholder="${ed ? 'proporcional' : ''}" style="width:105px;text-align:right" ${dis}></td>
                <td>${ed ? `<button type="button" class="btn btn-mini" data-tirar-local="${i}:${j}">×</button>` : ''}</td>
              </tr>`).join('')}</tbody>
          </table>
          <div class="guia-lote-rodape">
            ${ed ? `<button type="button" class="btn btn-mini" data-por-local="${i}">+ local</button>` : '<span></span>'}
            <span class="mini" data-conf-resultado="${i}"></span>
          </div>
        </div>`).join('')}
      ${ed ? '<button type="button" class="btn" id="servico-mais-lote">+ Adicionar lote resultado</button>' : ''}`;

    WMSServico.botoes();
    WMSServico.ligarEditor();
    WMSServico.conta();
  },

  botoes() {
    const g = WMSServico._guia;
    const b = [];
    if (g.status === 'ABERTA') {
      if (g.id) b.push({ rotulo: 'Cancelar guia', classe: 'btn-perigo', acao: () => WMSServico.cancelar() });
      b.push({ rotulo: 'Salvar', acao: () => WMSServico.salvar(false) });
      b.push({ rotulo: 'Fechar guia e gerar lotes', classe: 'btn-primario', acao: () => WMSServico.salvar(true) });
    } else {
      if (g.status === 'FECHADA') b.push({ rotulo: 'Reabrir guia', acao: () => WMSServico.reabrir() });
      b.push({ rotulo: 'Fechar janela', classe: 'btn-primario', acao: () => UI.fecharModal() });
    }
    UI.trocarBotoes(b);
  },

  ler() {
    const g = WMSServico._guia;
    if (!WMSServico.editavel()) return g;
    const area = document.getElementById('servico-editor');
    const cab = area.querySelector('.servico-cab');
    const campo = (raiz, n) => raiz.querySelector(`[name="${n}"]`)?.value ?? '';
    ['data', 'data_inicio', 'data_fim', 'armazem_id', 'cliente_id', 'servico', 'produto_id', 'observacao']
      .forEach((n) => { g[n] = campo(cab, n); });
    g.valor = WMS.numero(campo(cab, 'valor'));
    const itens = {};
    (g.despejos || []).forEach((i) => { itens[i.posicao_id] = { ...i }; });
    area.querySelectorAll('.servico-despejo tr[data-pos]').forEach((tr) => {
      const pid = Number(tr.dataset.pos);
      const sacas = WMS.numero(tr.querySelector('[name="sacas"]').value);
      const peso = WMS.numero(tr.querySelector('[name="peso"]').value);
      if (sacas > 0) itens[pid] = { ...(itens[pid] || {}), posicao_id: pid, sacas, peso };
      else delete itens[pid];
    });
    g.despejos = Object.values(itens);
    g.resultados = [...area.querySelectorAll('[data-resultado]')].map((caixa) => {
      const grade = caixa.querySelector('.linha-campos');
      return {
        peneira: campo(grade, 'peneira'), padrao: campo(grade, 'padrao'), safra: campo(grade, 'safra'),
        sacas: WMS.numero(campo(grade, 'sacas')), peso: WMS.numero(campo(grade, 'peso')),
        unidade_id: campo(grade, 'unidade_id'),
        locais: [...caixa.querySelectorAll('[data-local]')].map((tr) => ({
          quadra_id: campo(tr, 'quadra_id'), pilha: campo(tr, 'pilha'),
          sacas: WMS.numero(campo(tr, 'sacas')), peso: WMS.numero(campo(tr, 'peso')),
        })),
      };
    });
    return g;
  },

  /* Despejo → resultado = quebra; e a conta de cada lote resultado. */
  conta() {
    const g = WMSServico.ler();
    const area = document.getElementById('servico-editor');
    const disp = {};
    WMSServico._disp.forEach((d) => { disp[d.posicao_id] = d; });
    const sacasD = g.despejos.reduce((s, i) => s + Number(i.sacas || 0), 0);
    let pesoD = 0;
    g.despejos.forEach((i) => {
      if (Number(i.peso)) pesoD += Number(i.peso);
      else if (disp[i.posicao_id] && Number(disp[i.posicao_id].sacas_disponiveis)) {
        const d = disp[i.posicao_id];
        pesoD += Number(d.peso_disponivel) / Number(d.sacas_disponiveis) * Number(i.sacas);
      }
    });
    const sacasR = g.resultados.reduce((s, r) => s + Number(r.sacas || 0), 0);
    const lotes = new Set(g.despejos.map((i) => disp[i.posicao_id]?.lote_codigo || i.lote_codigo));
    const quebra = sacasD - sacasR;
    area.querySelector('#servico-conta').innerHTML = `
      <span>Despejo: <b>${UI.numero(sacasD, 2)} sc</b>${pesoD ? ` (${UI.numero(pesoD, 0)} kg)` : ''} de ${lotes.size} lote(s)</span>
      <span>→ Resultado: <b>${UI.numero(sacasR, 2)} sc</b> em ${g.resultados.filter((r) => r.sacas > 0).length} lote(s)</span>
      <span class="${quebra < -0.004 ? 'negativo' : ''}">· Quebra: <b>${UI.numero(quebra, 2)} sc</b>${
        sacasD ? ` (${UI.numero(quebra / sacasD * 100, 1)}%)` : ''}${quebra < -0.004 ? ' — o resultado passa do despejo' : ''}</span>`;
    area.querySelectorAll('.servico-despejo tr[data-pos]').forEach((tr) => {
      const d = disp[tr.dataset.pos];
      const sc = WMS.numero(tr.querySelector('[name="sacas"]').value);
      tr.classList.toggle('saida-marcada', sc > 0);
      tr.classList.toggle('saida-passou', !!d && sc > Number(d.sacas_disponiveis) + 0.004);
    });
    g.resultados.forEach((r, i) => {
      const sc = r.locais.reduce((s, x) => s + Number(x.sacas || 0), 0);
      const alvo = area.querySelector(`[data-conf-resultado="${i}"]`);
      if (alvo) {
        alvo.innerHTML = `<span class="${Math.abs(sc - r.sacas) < 0.011 && sc ? 'positivo' : 'negativo'}">
          locais: ${UI.numero(sc, 2)} de ${UI.numero(r.sacas, 2)} sacas</span>`;
      }
    });
  },

  ligarEditor() {
    if (!WMSServico.editavel()) return;
    const area = document.getElementById('servico-editor');
    area.oninput = (e) => { if (e.target.name !== 'filtro_lote') WMSServico.conta(); };
    area.onfocusin = (e) => {
      if (e.target.matches('input[inputmode="decimal"]') && e.target.value) e.target.select();
    };
    const redesenhar = (mexer) => { WMSServico.ler(); mexer(WMSServico._guia); UI._sujo = true; WMSServico.render(); };
    const cab = area.querySelector('.servico-cab');
    ['armazem_id', 'cliente_id'].forEach((n) => {
      cab.querySelector(`[name="${n}"]`).onchange = async () => {
        const g = WMSServico.ler();
        g.despejos = [];
        UI._sujo = true;
        await WMSServico.carregarDisponivel();
        WMSServico.render();
      };
    });
    const filtro = area.querySelector('[name="filtro_lote"]');
    if (filtro) {
      let tempo = null;
      filtro.oninput = () => {
        clearTimeout(tempo);
        tempo = setTimeout(() => {
          WMSServico.ler();
          WMSServico._filtroLote = filtro.value;
          WMSServico.render();
          const novo = document.querySelector('#servico-editor [name="filtro_lote"]');
          if (novo) { novo.focus(); novo.setSelectionRange(novo.value.length, novo.value.length); }
        }, 300);
      };
    }
    area.querySelectorAll('[data-tudo]').forEach((b) => {
      b.onclick = () => {
        const d = WMSServico._disp.find((x) => String(x.posicao_id) === b.dataset.tudo);
        const tr = b.closest('tr');
        tr.querySelector('[name="sacas"]').value = UI.numero(d.sacas_disponiveis, 2);
        tr.querySelector('[name="peso"]').value = d.peso_disponivel ? UI.numero(d.peso_disponivel, 2) : '';
        UI._sujo = true;
        WMSServico.conta();
      };
    });
    area.querySelector('#servico-mais-lote').onclick = () => redesenhar((g) => g.resultados.push(WMSServico.resultadoVazio()));
    area.querySelectorAll('[data-tirar-resultado]').forEach((b) => {
      b.onclick = () => redesenhar((g) => g.resultados.splice(Number(b.dataset.tirarResultado), 1));
    });
    area.querySelectorAll('[data-por-local]').forEach((b) => {
      b.onclick = () => redesenhar((g) => g.resultados[Number(b.dataset.porLocal)].locais
        .push({ quadra_id: '', pilha: '', sacas: 0, peso: 0 }));
    });
    area.querySelectorAll('[data-tirar-local]').forEach((b) => {
      b.onclick = () => redesenhar((g) => {
        const [i, j] = b.dataset.tirarLocal.split(':').map(Number);
        g.resultados[i].locais.splice(j, 1);
      });
    });
    // resultado com um local só: as sacas do lote vão direto para o local
    area.querySelectorAll('[data-resultado]').forEach((caixa) => {
      const sacas = caixa.querySelector('.linha-campos [name="sacas"]');
      sacas.addEventListener('change', () => {
        const locais = caixa.querySelectorAll('[data-local] [name="sacas"]');
        if (locais.length === 1 && !locais[0].value) { locais[0].value = sacas.value; WMSServico.conta(); }
      });
    });
  },

  corpoParaApi() {
    const g = WMSServico.ler();
    const id = (v) => (v ? Number(v) : null);
    return {
      empresa_id: Estado.empresaId, data: g.data, data_inicio: g.data_inicio || null, data_fim: g.data_fim || null,
      armazem_id: id(g.armazem_id), cliente_id: id(g.cliente_id), servico: g.servico,
      produto_id: id(g.produto_id), valor: g.valor || 0, observacao: g.observacao,
      despejos: g.despejos.map((i) => ({ posicao_id: Number(i.posicao_id), sacas: i.sacas, peso: i.peso || 0 })),
      resultados: g.resultados.map((r) => ({
        peneira: r.peneira, padrao: r.padrao, safra: r.safra, sacas: r.sacas, peso: r.peso, unidade_id: id(r.unidade_id),
        locais: r.locais.map((x) => ({ quadra_id: id(x.quadra_id), pilha: x.pilha, sacas: x.sacas, peso: x.peso })),
      })),
    };
  },

  async salvar(fechar) {
    const g = WMSServico._guia;
    const corpo = WMSServico.corpoParaApi();
    try {
      let salva = g.id ? await Api.put(`/api/wms/guias-servico/${g.id}`, corpo)
        : await Api.post('/api/wms/guias-servico', corpo);
      WMSServico._guia = salva;
      if (!salva.resultados.length) salva.resultados = [WMSServico.resultadoVazio()];
      UI.modalSalvo();
      if (fechar) {
        try {
          salva = await Api.post(`/api/wms/guias-servico/${salva.id}/fechar`);
        } catch (e) {
          await WMSServico.carregarDisponivel();
          WMSServico.render();
          WMSServico.carregar();
          return UI.erro(e.message);
        }
        UI.fecharModal();
        UI.sucesso(`Guia de serviço ${salva.numero} fechada: gerou ${(salva.lotes_resultado || []).join(', ')} (quebra ${UI.numero(salva.quebra_sacas, 2)} sc).`);
      } else {
        await WMSServico.carregarDisponivel();
        WMSServico.render();
        UI.sucesso(`Guia de serviço ${salva.numero} salva (aberta).`);
      }
      await WMSServico.carregar();
    } catch (e) {
      UI.erro(e.message);
    }
  },

  async reabrir() {
    const g = WMSServico._guia;
    if (!await UI.confirmar(`Reabrir a guia de serviço ${g.numero}? Os lotes resultado somem e o despejo volta para os lotes de origem até ela ser fechada de novo.`, 'Reabrir')) {
      return WMSServico.abrir(g.id);
    }
    try {
      await Api.post(`/api/wms/guias-servico/${g.id}/reabrir`);
      UI.sucesso(`Guia de serviço ${g.numero} reaberta.`);
      await WMSServico.carregar();
    } catch (e) { UI.erro(e.message); }
    await WMSServico.abrir(g.id);
  },

  cancelar() {
    const g = WMSServico._guia;
    const corpo = UI.abrirModal({
      titulo: `Cancelar a guia de serviço ${g.numero}`,
      corpo: `<p style="margin-top:0">A guia fica na lista como cancelada e não mexe em nenhum lote.</p>
        ${UI.campo('Motivo *', '<input name="motivo" maxlength="200" placeholder="ex.: serviço não foi feito">')}`,
      botoes: [
        { rotulo: 'Voltar', acao: () => WMSServico.abrir(g.id) },
        { rotulo: 'Cancelar guia', classe: 'btn-perigo', acao: async () => {
          try {
            await Api.post(`/api/wms/guias-servico/${g.id}/cancelar`, { motivo: corpo.querySelector('[name="motivo"]').value });
            UI.modalSalvo();
            UI.fecharModal();
            UI.sucesso('Guia de serviço cancelada.');
            await WMSServico.carregar();
          } catch (e) { UI.erro(e.message); }
        } },
      ],
    });
  },
};
