/* WMS — Guia de entrada (tela Entrada) e cadastro de quadras.

   A guia tem três níveis, e a tela mostra os três de uma vez:

     Cabeçalho  data, número, armazém, cliente, cliente de origem, contrato de
                compra, produto, unidade, peso total e sacas (do ticket)
     Lotes      15/1, 15/2... com peneira, padrão, sacas, peso, unidade e
                valor por saca
     Locais     dentro de cada lote: quadra, pilha, sacas e peso

   Enquanto a guia está ABERTA, "Salvar" grava o rascunho. "Fechar guia" confere
   os totais e gera os lotes com as posições no armazém — a partir daí o café
   aparece no saldo e nas telas de Saídas, Transferências e Remoção. */
const WMSEntrada = {
  _dados: null,
  _quadras: [],
  _contratos: null,
  _guia: null,          // a guia aberta no editor (estado da tela)
  _filtros: { de: '', ate: '', armazem_id: '', cliente_id: '', status: '', busca: '' },

  STATUS: { ABERTA: 'Aberta', FECHADA: 'Fechada', CANCELADA: 'Cancelada' },

  async tela() {
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';
    try {
      await WMSEntrada.carregar();
    } catch (e) {
      alvo.innerHTML = `<div class="cartao"><div class="vazio">${UI.escapar(e.message)}</div></div>`;
    }
  },

  async carregar() {
    const eid = Estado.empresaId;
    const [armazens, quadras, dados] = await Promise.all([
      Api.get('/api/wms/armazens', { empresa_id: eid }),
      Api.get('/api/wms/quadras', { empresa_id: eid }),
      Api.get('/api/wms/guias-entrada', { empresa_id: eid, ...WMSEntrada._filtros }),
    ]);
    WMS._armazens = armazens;
    WMSEntrada._quadras = quadras;
    WMSEntrada._dados = dados;
    WMSEntrada.desenhar();
  },

  /* ------------------------------------------------------------- a lista */
  desenhar() {
    const d = WMSEntrada._dados || { guias: [], resumo: {} };
    const r = d.resumo || {};
    const f = WMSEntrada._filtros;
    const semArmazem = !WMS._armazens.length;
    const semQuadra = !semArmazem && !WMSEntrada._quadras.length;
    document.getElementById('pagina').innerHTML = `
      <div class="grade g4" style="margin-bottom:12px">
        ${WMS.cartao('Guias', String(r.guias || 0), 'no filtro abaixo', 'azul')}
        ${WMS.cartao('Abertas', String(r.abertas || 0), 'ainda não geraram lotes', r.abertas ? 'ambar' : '')}
        ${WMS.cartao('Sacas', UI.numero(r.sacas, 2), 'recebidas', 'verde')}
        ${WMS.cartao('Peso', `${UI.numero(r.peso_kg, 0)} kg`, 'somado das guias', '')}
      </div>
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Guias de entrada</h3>
            <div class="mini">o caminhão descarregou: lance a guia com os lotes e onde cada um ficou — ao fechar, os lotes entram no saldo</div></div>
          <div class="espaco">
            <button class="btn" id="wms-quadras">Quadras</button>
            <button class="btn" id="wms-armazens">Armazéns</button>
            <button class="btn" id="wms-saldo">Saldo do armazém</button>
            <button class="btn" id="wms-exportar">Exportar</button>
            <button class="btn btn-primario" id="wms-novo">Nova guia de entrada</button>
          </div>
        </div>
        <div class="cartao-corpo">
          ${semArmazem ? `<div class="ok-caixa" style="margin-bottom:12px">Comece cadastrando o
            armazém (botão <b>Armazéns</b>) e as quadras dele (botão <b>Quadras</b>).</div>` : ''}
          ${semQuadra ? `<div class="ok-caixa" style="margin-bottom:12px">Cadastre as quadras do
            armazém (botão <b>Quadras</b>) — é nelas que os lotes ficam guardados.</div>` : ''}
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
            ${UI.campo('Procurar', `<input name="busca" value="${UI.escapar(f.busca)}" placeholder="número, documento, placa">`)}
          </div>
          <div id="lista-wms" style="margin-top:12px">${UI.tabela({
            vazio: 'Nenhuma guia neste filtro. Use "Nova guia de entrada" quando o caminhão descarregar.',
            colunas: [
              { titulo: 'Nº', chave: 'numero', valor: (g) => `<b>${g.numero}</b>` },
              { titulo: 'Data', valor: (g) => UI.data(g.data) },
              { titulo: 'Cliente', valor: (g) => `${UI.escapar(g.cliente_nome)}
                ${g.cliente_origem_nome ? `<div class="mini">origem: ${UI.escapar(g.cliente_origem_nome)}</div>` : ''}` },
              { titulo: 'Armazém', valor: (g) => UI.escapar(g.armazem_nome) },
              { titulo: 'Contrato', valor: (g) => UI.escapar(g.contrato_numero || '—') },
              { titulo: 'Lotes', classe: 'direita', valor: (g) => g.qtd_lotes },
              { titulo: 'Sacas', classe: 'direita', chave: 'sacas', valor: (g) => `<b>${UI.numero(g.sacas, 2)}</b>` },
              { titulo: 'Peso (kg)', classe: 'direita', chave: 'peso', valor: (g) => UI.numero(g.peso_total, 0) },
              { titulo: 'Situação', valor: (g) => WMSEntrada.tag(g.status) },
              { titulo: '', classe: 'direita', valor: (g, i) =>
                `<button class="btn btn-mini" data-abrir="${i}">${g.status === 'ABERTA' ? 'Editar' : 'Ver'}</button>` },
            ],
            linhas: d.guias,
            rodape: d.guias.length ? {
              numero: `<b>${r.guias}</b>`,
              sacas: `<b>${UI.numero(r.sacas, 2)}</b>`,
              peso: `<b>${UI.numero(r.peso_kg, 0)}</b>`,
            } : null,
          })}</div>
        </div>
      </div>`;
    WMSEntrada.ligar();
  },

  tag(status) {
    const classe = { ABERTA: 'tag-parcial', FECHADA: 'tag-pago', CANCELADA: 'tag-cancelado' }[status] || '';
    return `<span class="tag ${classe}">${WMSEntrada.STATUS[status] || status}</span>`;
  },

  ligar() {
    const pagina = document.getElementById('pagina');
    pagina.querySelector('#wms-novo').onclick = () => WMSEntrada.nova();
    pagina.querySelector('#wms-quadras').onclick = () => WMSEntrada.listaQuadras();
    pagina.querySelector('#wms-armazens').onclick = () => WMS.listaArmazens();
    pagina.querySelector('#wms-saldo').onclick = () => WMS.saldo();
    pagina.querySelector('#wms-exportar').onclick = () =>
      UI.exportarTabela('wms-guias-entrada', '#lista-wms table');
    ['de', 'ate', 'armazem_id', 'cliente_id', 'status'].forEach((nome) => {
      const campo = pagina.querySelector(`[name="${nome}"]`);
      campo.onchange = () => { WMSEntrada._filtros[nome] = campo.value; WMSEntrada.carregar(); };
    });
    const busca = pagina.querySelector('[name="busca"]');
    let tempo = null;
    busca.oninput = () => {
      clearTimeout(tempo);
      tempo = setTimeout(() => { WMSEntrada._filtros.busca = busca.value; WMSEntrada.carregar(); }, 400);
    };
    pagina.querySelectorAll('[data-abrir]').forEach((b) => {
      b.onclick = () => WMSEntrada.abrir(WMSEntrada._dados.guias[Number(b.dataset.abrir)].id);
    });
  },

  /* ------------------------------------------------------------- o editor */
  loteVazio() {
    return { peneira: '', padrao: '', sacas: 0, peso: 0, unidade_id: '', valor_unitario: 0,
      locais: [{ quadra_id: '', pilha: '', sacas: 0, peso: 0 }] };
  },

  async nova() {
    const armazens = WMS.armazensAtivos();
    if (!armazens.length) {
      UI.erro('Cadastre primeiro o armazém.');
      return WMS.formularioArmazem(null);
    }
    if (!WMS.depositantes().length) return UI.erro('Cadastre o cliente em Cadastros > Parceiros.');
    WMSEntrada._guia = {
      id: null, numero: null, status: 'ABERTA', data: UI.hoje(),
      armazem_id: armazens.length === 1 ? armazens[0].id : '',
      cliente_id: '', cliente_origem_id: '', contrato_id: '', produto_id: '', unidade_id: '',
      peso_total: 0, sacas: 0, documento: '', placa: '', motorista: '', observacao: '',
      lotes: [WMSEntrada.loteVazio()],
    };
    await WMSEntrada.editor();
  },

  async abrir(id) {
    try {
      WMSEntrada._guia = await Api.get(`/api/wms/guias-entrada/${id}`);
    } catch (e) { return UI.erro(e.message); }
    await WMSEntrada.editor();
  },

  async editor() {
    if (!WMSEntrada._contratos) {
      WMSEntrada._contratos = await Api.get('/api/wms/contratos-compra', { empresa_id: Estado.empresaId })
        .catch(() => []);
    }
    const g = WMSEntrada._guia;
    const titulo = g.id ? `Guia de entrada nº ${g.numero}` : 'Nova guia de entrada';
    UI.abrirModal({
      titulo, largo: true, corpo: '<div id="guia-editor"></div>', botoes: [],
      aoSalvar: g.status === 'ABERTA' ? () => WMSEntrada.salvar(false) : null,
    });
    WMSEntrada.render();
  },

  editavel() {
    return WMSEntrada._guia.status === 'ABERTA';
  },

  opcoesQuadras(armazemId) {
    return WMSEntrada._quadras
      .filter((q) => String(q.armazem_id) === String(armazemId) && q.ativo)
      .map((q) => ({ valor: q.id, rotulo: q.nome }));
  },

  /* Valor num campo de número: vazio quando é zero, no jeito brasileiro. */
  v(n, casas = 2) {
    return Number(n) ? UI.numero(n, casas) : '';
  },

  render() {
    const g = WMSEntrada._guia;
    const ed = WMSEntrada.editavel();
    const dis = ed ? '' : 'disabled';
    const deps = WMS.depositantes().map((p) => ({ valor: p.id, rotulo: p.nome }));
    const unidades = Api.unidadesAtivas().map((u) => ({ valor: u.id, rotulo: u.codigo }));
    const contratos = (WMSEntrada._contratos || []).map((c) => ({
      valor: c.id,
      rotulo: `${c.numero} — ${c.vendedor_nome || 'sem vendedor'} · ${UI.numero(c.quantidade, 0)} (recebido ${UI.numero(c.sacas_recebidas, 0)} sc)`,
    }));
    const quadras = WMSEntrada.opcoesQuadras(g.armazem_id);

    const area = document.getElementById('guia-editor');
    area.innerHTML = `
      ${g.status !== 'ABERTA' ? `<div class="ok-caixa" style="margin-bottom:12px">
        Guia ${WMSEntrada.STATUS[g.status].toLowerCase()}${g.status === 'FECHADA'
          ? ' — os lotes já estão no saldo do armazém. Para mudar alguma coisa, reabra a guia (só dá se nada saiu ainda).'
          : '.'}</div>` : ''}
      <div class="linha-campos guia-cab">
        ${UI.campo('Data', `<input type="date" name="data" value="${g.data || ''}" ${dis}>`)}
        ${UI.campo('Número', `<input value="${g.numero || 'automático'}" disabled>`)}
        ${UI.campo('Armazém *', UI.select('armazem_id',
          WMS._armazens.filter((a) => a.ativo || String(a.id) === String(g.armazem_id))
            .map((a) => ({ valor: a.id, rotulo: a.nome })), g.armazem_id, { vazio: 'Escolha', attr: dis }))}
        ${UI.campo('Cliente *', UI.select('cliente_id', deps, g.cliente_id, { vazio: 'Escolha', attr: dis }),
          'dono do café no armazém')}
        ${UI.campo('Cliente origem', UI.select('cliente_origem_id', deps, g.cliente_origem_id, { vazio: '—', attr: dis }),
          'de quem o café veio')}
        ${UI.campo('Contrato', UI.select('contrato_id', contratos, g.contrato_id, { vazio: '— sem contrato —', attr: dis }),
          'contrato de compra')}
        ${UI.campo('Produto', UI.select('produto_id',
          Api.produtosAtivos().map((p) => ({ valor: p.id, rotulo: `${p.codigo} — ${p.nome}` })),
          g.produto_id, { vazio: '—', attr: dis }))}
        ${UI.campo('Unidade', UI.select('unidade_id', unidades, g.unidade_id, { vazio: '—', attr: dis }))}
        ${UI.campo('Total peso (kg) *', `<input name="peso_total" inputmode="decimal" value="${WMSEntrada.v(g.peso_total)}" ${dis}>`)}
        ${UI.campo('Sacas *', `<input name="sacas" inputmode="decimal" value="${WMSEntrada.v(g.sacas)}" ${dis}>`)}
        ${UI.campo('Documento', `<input name="documento" maxlength="40" value="${UI.escapar(g.documento || '')}" placeholder="nota, ticket" ${dis}>`)}
        ${UI.campo('Placa', `<input name="placa" maxlength="10" style="text-transform:uppercase" value="${UI.escapar(g.placa || '')}" ${dis}>`)}
        ${UI.campo('Motorista', `<input name="motorista" maxlength="120" value="${UI.escapar(g.motorista || '')}" ${dis}>`)}
        ${UI.campo('Observação', `<input name="observacao" maxlength="300" value="${UI.escapar(g.observacao || '')}" ${dis}>`)}
      </div>

      <div id="guia-conferencia" class="guia-conferencia"></div>

      <h4 style="margin:16px 0 8px">Lotes da entrada</h4>
      ${!quadras.length && ed ? `<div class="ok-caixa" style="margin-bottom:10px">${g.armazem_id
        ? 'Este armazém ainda não tem quadras. Cadastre pelo botão <b>Quadras</b> da tela.'
        : 'Escolha o armazém para ver as quadras.'}</div>` : ''}
      ${(g.lotes || []).map((l, i) => `
        <div class="guia-lote" data-lote="${i}">
          <div class="guia-lote-topo">
            <b>Lote ${g.numero || '—'}/${i + 1}</b>
            ${ed && g.lotes.length > 1 ? `<button type="button" class="btn btn-mini" data-tirar-lote="${i}">Remover lote</button>` : ''}
          </div>
          <div class="linha-campos">
            ${UI.campo('Peneira', `<input name="peneira" maxlength="20" value="${UI.escapar(l.peneira || '')}" placeholder="ex.: 17/18" ${dis}>`)}
            ${UI.campo('Padrão', `<input name="padrao" maxlength="60" value="${UI.escapar(l.padrao || '')}" placeholder="ex.: tipo 6 bebida dura" ${dis}>`)}
            ${UI.campo('Sacas *', `<input name="sacas" inputmode="decimal" value="${WMSEntrada.v(l.sacas)}" ${dis}>`)}
            ${UI.campo('Peso (kg)', `<input name="peso" inputmode="decimal" value="${WMSEntrada.v(l.peso)}" ${dis}>`)}
            ${UI.campo('Unidade', UI.select('unidade_id', unidades, l.unidade_id, { vazio: '—', attr: dis }))}
            ${UI.campo('Valor por saca (R$)', `<input name="valor_unitario" inputmode="decimal" value="${WMSEntrada.v(l.valor_unitario)}" ${dis}>`)}
          </div>
          <div class="guia-locais">
            <div class="mini forte" style="margin:8px 0 4px">Locais do lote</div>
            <table class="tabela-simples guia-locais-tabela">
              <thead><tr><th>Quadra</th><th>Pilha</th><th style="text-align:right">Sacas</th><th style="text-align:right">Peso (kg)</th><th></th></tr></thead>
              <tbody>
              ${(l.locais || []).map((x, j) => `
                <tr data-local="${j}">
                  <td>${UI.select('quadra_id', quadras.length ? quadras
                    : (x.quadra_id ? [{ valor: x.quadra_id, rotulo: x.quadra_nome || '?' }] : []),
                    x.quadra_id, { vazio: 'Quadra', attr: dis })}</td>
                  <td><input name="pilha" maxlength="20" value="${UI.escapar(x.pilha || '')}" style="text-transform:uppercase;width:90px" ${dis}></td>
                  <td class="direita"><input name="sacas" inputmode="decimal" value="${WMSEntrada.v(x.sacas)}" style="width:100px;text-align:right" ${dis}></td>
                  <td class="direita"><input name="peso" inputmode="decimal" value="${WMSEntrada.v(x.peso)}" style="width:110px;text-align:right" placeholder="${ed ? 'proporcional' : ''}" ${dis}></td>
                  <td>${ed ? `<button type="button" class="btn btn-mini" data-tirar-local="${i}:${j}" title="Tirar este local">×</button>` : ''}</td>
                </tr>`).join('')}
              </tbody>
            </table>
            <div class="guia-lote-rodape">
              ${ed ? `<button type="button" class="btn btn-mini" data-por-local="${i}">+ local</button>` : '<span></span>'}
              <span class="mini" data-conf-lote="${i}"></span>
            </div>
          </div>
        </div>`).join('')}
      ${ed ? '<button type="button" class="btn" id="guia-mais-lote">+ Adicionar lote</button>' : ''}`;

    WMSEntrada.botoes();
    WMSEntrada.ligarEditor(area);
    WMSEntrada.conferir();
  },

  botoes() {
    const g = WMSEntrada._guia;
    const b = [];
    if (g.status === 'ABERTA') {
      if (g.id) b.push({ rotulo: 'Cancelar guia', classe: 'btn-perigo', acao: () => WMSEntrada.cancelar() });
      b.push({ rotulo: 'Salvar', acao: () => WMSEntrada.salvar(false) });
      b.push({ rotulo: 'Fechar guia e gerar lotes', classe: 'btn-primario', acao: () => WMSEntrada.salvar(true) });
    } else {
      if (g.status === 'FECHADA') b.push({ rotulo: 'Reabrir guia', acao: () => WMSEntrada.reabrir() });
      b.push({ rotulo: 'Fechar janela', classe: 'btn-primario', acao: () => UI.fecharModal() });
    }
    UI.trocarBotoes(b);
  },

  /* Lê da tela para o estado — antes de redesenhar e antes de salvar. */
  ler() {
    const g = WMSEntrada._guia;
    if (!WMSEntrada.editavel()) return g;
    const area = document.getElementById('guia-editor');
    const cab = area.querySelector('.guia-cab');
    const campo = (raiz, nome) => raiz.querySelector(`[name="${nome}"]`)?.value ?? '';
    ['data', 'armazem_id', 'cliente_id', 'cliente_origem_id', 'contrato_id', 'produto_id',
      'unidade_id', 'documento', 'placa', 'motorista', 'observacao'].forEach((n) => { g[n] = campo(cab, n); });
    g.peso_total = WMS.numero(campo(cab, 'peso_total'));
    g.sacas = WMS.numero(campo(cab, 'sacas'));
    g.lotes = [...area.querySelectorAll('[data-lote]')].map((caixa) => ({
      peneira: campo(caixa, 'peneira'),
      padrao: campo(caixa, 'padrao'),
      sacas: WMS.numero(campo(caixa, 'sacas')),
      peso: WMS.numero(campo(caixa, 'peso')),
      unidade_id: campo(caixa, 'unidade_id'),
      valor_unitario: WMS.numero(campo(caixa, 'valor_unitario')),
      locais: [...caixa.querySelectorAll('[data-local]')].map((tr) => ({
        quadra_id: campo(tr, 'quadra_id'),
        pilha: campo(tr, 'pilha'),
        sacas: WMS.numero(campo(tr, 'sacas')),
        peso: WMS.numero(campo(tr, 'peso')),
      })),
    }));
    return g;
  },

  /* Mostra, enquanto digita, se as contas batem — as mesmas do servidor. */
  conferir() {
    const g = WMSEntrada.ler();
    const area = document.getElementById('guia-editor');
    const bate = (a, b) => Math.abs(a - b) < 0.011;
    const sacasLotes = g.lotes.reduce((s, l) => s + Number(l.sacas || 0), 0);
    const pesoLotes = g.lotes.reduce((s, l) => s + Number(l.peso || 0), 0);
    const valor = g.lotes.reduce((s, l) => s + Number(l.sacas || 0) * Number(l.valor_unitario || 0), 0);
    const ok = g.sacas > 0 && bate(sacasLotes, g.sacas) && bate(pesoLotes, g.peso_total);
    area.querySelector('#guia-conferencia').innerHTML = `
      <span class="${bate(sacasLotes, g.sacas) ? 'positivo' : 'negativo'}">
        Lotes: <b>${UI.numero(sacasLotes, 2)}</b> de ${UI.numero(g.sacas, 2)} sacas</span>
      <span class="${bate(pesoLotes, g.peso_total) ? 'positivo' : 'negativo'}">
        · <b>${UI.numero(pesoLotes, 0)}</b> de ${UI.numero(g.peso_total, 0)} kg</span>
      <span>· valor dos lotes <b>${UI.moeda(valor)}</b></span>
      ${ok ? '<span class="positivo">· ✓ bate com o cabeçalho</span>' : ''}`;
    g.lotes.forEach((l, i) => {
      const sc = l.locais.reduce((s, x) => s + Number(x.sacas || 0), 0);
      const alvo = area.querySelector(`[data-conf-lote="${i}"]`);
      if (alvo) {
        alvo.innerHTML = `<span class="${bate(sc, l.sacas) && sc ? 'positivo' : 'negativo'}">
          locais: ${UI.numero(sc, 2)} de ${UI.numero(l.sacas, 2)} sacas</span>
          · total do lote ${UI.moeda(Number(l.sacas || 0) * Number(l.valor_unitario || 0))}`;
      }
    });
  },

  /* Peso a partir das sacas, quando a unidade diz quantos quilos tem a saca. */
  pesoSugerido(sacas, unidadeId) {
    const u = Api.unidadesAtivas().find((x) => String(x.id) === String(unidadeId));
    const kg = u ? Number(u.peso_conversao || 0) : 0;
    return kg && sacas ? Math.round(sacas * kg * 100) / 100 : 0;
  },

  ligarEditor(area) {
    if (!WMSEntrada.editavel()) return;
    area.oninput = () => WMSEntrada.conferir();
    // número já preenchido (ex.: peso sugerido) fica selecionado ao entrar no
    // campo: o que for digitado substitui, em vez de grudar no fim
    area.onfocusin = (e) => {
      if (e.target.matches('input[inputmode="decimal"]') && e.target.value) e.target.select();
    };
    const redesenhar = (mexer) => { WMSEntrada.ler(); mexer(WMSEntrada._guia); UI._sujo = true; WMSEntrada.render(); };

    // armazém muda as quadras disponíveis
    area.querySelector('.guia-cab [name="armazem_id"]').onchange = () => redesenhar(() => {});
    // o contrato preenche origem, produto e unidade
    area.querySelector('.guia-cab [name="contrato_id"]').onchange = (e) => {
      const c = (WMSEntrada._contratos || []).find((x) => String(x.id) === e.target.value);
      redesenhar((g) => {
        if (!c) return;
        if (c.vendedor_id && !g.cliente_origem_id) g.cliente_origem_id = c.vendedor_id;
        if (c.produto_id && !g.produto_id) g.produto_id = c.produto_id;
        if (c.unidade_id && !g.unidade_id) g.unidade_id = c.unidade_id;
        g.lotes.forEach((l) => { if (!l.unidade_id) l.unidade_id = g.unidade_id; });
      });
    };
    // a unidade do cabeçalho vale para os lotes que ainda não têm a sua
    area.querySelector('.guia-cab [name="unidade_id"]').onchange = () => {
      redesenhar((g) => g.lotes.forEach((l) => { if (!l.unidade_id) l.unidade_id = g.unidade_id; }));
    };
    // sacas com peso vazio: sugere pela unidade (saca de 60 kg etc.)
    const sugerir = (raiz, unidadeId) => {
      const sacas = raiz.querySelector('[name="sacas"]');
      const peso = raiz.querySelector('[name="peso"], [name="peso_total"]');
      sacas.addEventListener('change', () => {
        if (peso.value) return;
        const kg = WMSEntrada.pesoSugerido(WMS.numero(sacas.value), unidadeId());
        if (kg) { peso.value = UI.numero(kg, 2); WMSEntrada.conferir(); }
      });
    };
    const cab = area.querySelector('.guia-cab');
    sugerir(cab, () => cab.querySelector('[name="unidade_id"]').value);
    area.querySelectorAll('[data-lote]').forEach((caixa) => {
      const grade = caixa.querySelector('.linha-campos');
      sugerir(grade, () => grade.querySelector('[name="unidade_id"]').value || cab.querySelector('[name="unidade_id"]').value);
    });

    area.querySelector('#guia-mais-lote').onclick = () => redesenhar((g) => {
      const novo = WMSEntrada.loteVazio();
      novo.unidade_id = g.unidade_id || '';
      g.lotes.push(novo);
    });
    area.querySelectorAll('[data-tirar-lote]').forEach((b) => {
      b.onclick = () => redesenhar((g) => g.lotes.splice(Number(b.dataset.tirarLote), 1));
    });
    area.querySelectorAll('[data-por-local]').forEach((b) => {
      b.onclick = () => redesenhar((g) => g.lotes[Number(b.dataset.porLocal)].locais
        .push({ quadra_id: '', pilha: '', sacas: 0, peso: 0 }));
    });
    area.querySelectorAll('[data-tirar-local]').forEach((b) => {
      b.onclick = () => redesenhar((g) => {
        const [i, j] = b.dataset.tirarLocal.split(':').map(Number);
        g.lotes[i].locais.splice(j, 1);
      });
    });
  },

  corpoParaApi() {
    const g = WMSEntrada.ler();
    const id = (v) => (v ? Number(v) : null);
    return {
      empresa_id: Estado.empresaId,
      data: g.data,
      armazem_id: id(g.armazem_id),
      cliente_id: id(g.cliente_id),
      cliente_origem_id: id(g.cliente_origem_id),
      contrato_id: id(g.contrato_id),
      produto_id: id(g.produto_id),
      unidade_id: id(g.unidade_id),
      peso_total: g.peso_total,
      sacas: g.sacas,
      documento: g.documento,
      placa: g.placa ? String(g.placa).toUpperCase() : '',
      motorista: g.motorista,
      observacao: g.observacao,
      lotes: g.lotes.map((l) => ({
        peneira: l.peneira, padrao: l.padrao, sacas: l.sacas, peso: l.peso,
        unidade_id: id(l.unidade_id), valor_unitario: l.valor_unitario,
        locais: l.locais.map((x) => ({ quadra_id: id(x.quadra_id), pilha: x.pilha, sacas: x.sacas, peso: x.peso })),
      })),
    };
  },

  async salvar(fechar) {
    const g = WMSEntrada._guia;
    const corpo = WMSEntrada.corpoParaApi();
    try {
      let salva = g.id
        ? await Api.put(`/api/wms/guias-entrada/${g.id}`, corpo)
        : await Api.post('/api/wms/guias-entrada', corpo);
      WMSEntrada._guia = salva;
      UI.modalSalvo();
      if (fechar) {
        try {
          salva = await Api.post(`/api/wms/guias-entrada/${salva.id}/fechar`);
        } catch (e) {
          // o rascunho ficou gravado; a tela continua aberta para acertar
          WMSEntrada.render();
          WMSEntrada.carregar();
          return UI.erro(e.message);
        }
        UI.fecharModal();
        UI.sucesso(`Guia ${salva.numero} fechada: ${salva.qtd_lotes} lote(s) no saldo do armazém.`);
      } else {
        WMSEntrada.render();
        UI.sucesso(`Guia ${salva.numero} salva (aberta).`);
      }
      await WMSEntrada.carregar();
    } catch (e) {
      UI.erro(e.message);
    }
  },

  async reabrir() {
    const g = WMSEntrada._guia;
    if (!await UI.confirmar(`Reabrir a guia ${g.numero}? Os lotes dela saem do saldo até ela ser fechada de novo.`, 'Reabrir')) {
      return WMSEntrada.abrir(g.id);
    }
    try {
      await Api.post(`/api/wms/guias-entrada/${g.id}/reabrir`);
      UI.sucesso(`Guia ${g.numero} reaberta.`);
      await WMSEntrada.carregar();
      await WMSEntrada.abrir(g.id);
    } catch (e) {
      UI.erro(e.message);
      await WMSEntrada.abrir(g.id);
    }
  },

  cancelar() {
    const g = WMSEntrada._guia;
    const corpo = UI.abrirModal({
      titulo: `Cancelar a guia ${g.numero}`,
      corpo: `<p style="margin-top:0">A guia fica na lista como cancelada e não gera lote nenhum.</p>
        ${UI.campo('Motivo *', '<input name="motivo" maxlength="200" placeholder="ex.: lançada em dobro">')}`,
      botoes: [
        { rotulo: 'Voltar', acao: () => WMSEntrada.abrir(g.id) },
        { rotulo: 'Cancelar guia', classe: 'btn-perigo', acao: async () => {
          try {
            await Api.post(`/api/wms/guias-entrada/${g.id}/cancelar`, { motivo: corpo.querySelector('[name="motivo"]').value });
            UI.modalSalvo();
            UI.fecharModal();
            UI.sucesso('Guia cancelada.');
            await WMSEntrada.carregar();
          } catch (e) { UI.erro(e.message); }
        } },
      ],
    });
  },

  /* -------------------------------------------------------------- quadras */
  listaQuadras() {
    const quadras = WMSEntrada._quadras;
    UI.abrirModal({
      titulo: 'Quadras do armazém',
      largo: true,
      corpo: `${WMSEntrada.mapa()}
        ${UI.tabela({
          vazio: 'Nenhuma quadra cadastrada ainda.',
          colunas: [
            { titulo: 'Armazém', valor: (q) => UI.escapar(q.armazem_nome) },
            { titulo: 'Quadra', valor: (q) => `<b>${UI.escapar(q.nome)}</b>` },
            { titulo: 'X', classe: 'direita', valor: (q) => UI.numero(q.x, 2) },
            { titulo: 'Y', classe: 'direita', valor: (q) => UI.numero(q.y, 2) },
            { titulo: 'Sacas hoje', classe: 'direita', valor: (q) => UI.numero(q.sacas_atuais, 2) },
            { titulo: 'Situação', valor: (q) => (q.ativo ? 'Ativa' : '<span class="tag tag-cancelado">Inativa</span>') },
            { titulo: '', classe: 'direita', valor: (q, i) => `<button class="btn btn-mini" data-editar-quadra="${i}">Editar</button>` },
          ],
          linhas: quadras,
        })}`,
      botoes: [
        { rotulo: 'Fechar', acao: () => UI.fecharModal() },
        { rotulo: 'Nova quadra', classe: 'btn-primario', acao: () => WMSEntrada.formularioQuadra(null) },
      ],
    });
    document.querySelectorAll('[data-editar-quadra]').forEach((b) => {
      b.onclick = () => WMSEntrada.formularioQuadra(quadras[Number(b.dataset.editarQuadra)]);
    });
  },

  /* Planta simples: cada quadra no seu X,Y, com as sacas que entraram nela. */
  mapa() {
    const porArmazem = {};
    WMSEntrada._quadras.filter((q) => q.ativo).forEach((q) => {
      (porArmazem[q.armazem_nome] = porArmazem[q.armazem_nome] || []).push(q);
    });
    const nomes = Object.keys(porArmazem);
    if (!nomes.length) return '';
    return `<div class="mini" style="margin-bottom:6px">Planta pelas coordenadas X e Y de cada quadra, com as sacas que estão nela hoje:</div>
      <div class="guia-mapas">${nomes.map((nome) => {
        const qs = porArmazem[nome];
        const xs = qs.map((q) => Number(q.x)); const ys = qs.map((q) => Number(q.y));
        const minX = Math.min(...xs); const maxX = Math.max(...xs);
        const minY = Math.min(...ys); const maxY = Math.max(...ys);
        const passo = 64; const pad = 8;
        const larg = (maxX - minX + 1) * passo + pad * 2;
        const alt = (maxY - minY + 1) * passo + pad * 2;
        const caixas = qs.map((q) => {
          const x = pad + (Number(q.x) - minX) * passo;
          const y = pad + (Number(q.y) - minY) * passo;
          const ocupada = Number(q.sacas_atuais) > 0.004;
          return `<g><rect x="${x + 3}" y="${y + 3}" width="${passo - 6}" height="${passo - 6}" rx="6"
              class="${ocupada ? 'quadra-ocupada' : 'quadra-livre'}"></rect>
            <text x="${x + passo / 2}" y="${y + passo / 2 - 3}" text-anchor="middle" class="quadra-nome">${UI.escapar(q.nome)}</text>
            <text x="${x + passo / 2}" y="${y + passo / 2 + 13}" text-anchor="middle" class="quadra-sacas">${ocupada ? `${UI.numero(q.sacas_atuais, 0)} sc` : 'livre'}</text></g>`;
        }).join('');
        return `<div class="guia-mapa"><div class="mini forte">${UI.escapar(nome)}</div>
          <svg viewBox="0 0 ${larg} ${alt}" width="${Math.min(larg, 640)}" style="max-width:100%">${caixas}</svg></div>`;
      }).join('')}</div>`;
  },

  formularioQuadra(q) {
    const v = q || { armazem_id: WMS.armazensAtivos().length === 1 ? WMS.armazensAtivos()[0].id : '', nome: '', x: '', y: '', ativo: true };
    if (!WMS._armazens.length) {
      UI.erro('Cadastre primeiro o armazém.');
      return WMS.formularioArmazem(null);
    }
    UI.abrirModal({
      titulo: q ? `Quadra ${q.nome}` : 'Nova quadra',
      corpo: `<div class="linha-campos">
        ${UI.campo('Armazém *', UI.select('armazem_id',
          WMS._armazens.map((a) => ({ valor: a.id, rotulo: a.nome })), v.armazem_id, { vazio: 'Escolha' }))}
        ${UI.campo('Nome *', `<input name="nome" maxlength="40" style="text-transform:uppercase" value="${UI.escapar(v.nome)}" placeholder="ex.: A1">`)}
        ${UI.campo('X', `<input name="x" inputmode="decimal" value="${v.x === '' ? '' : UI.numero(v.x, 2)}">`, 'coluna / posição na planta')}
        ${UI.campo('Y', `<input name="y" inputmode="decimal" value="${v.y === '' ? '' : UI.numero(v.y, 2)}">`, 'linha / posição na planta')}
        <label class="campo">Situação
          <span class="espaco" style="margin-top:6px">
            <input type="checkbox" name="ativo" ${v.ativo ? 'checked' : ''}> <span class="mini">ativa</span>
          </span>
        </label>
      </div>`,
      botoes: [
        { rotulo: 'Voltar', acao: () => WMSEntrada.listaQuadras() },
        { rotulo: 'Salvar', classe: 'btn-primario', acao: () => WMSEntrada.salvarQuadra(q) },
      ],
      aoSalvar: () => WMSEntrada.salvarQuadra(q),
    });
  },

  async salvarQuadra(q) {
    const corpo = document.getElementById('modal-corpo');
    const f = UI.lerFormulario(corpo);
    const dados = {
      empresa_id: Estado.empresaId,
      armazem_id: f.armazem_id ? Number(f.armazem_id) : null,
      nome: f.nome,
      x: WMS.numero(f.x),
      y: WMS.numero(f.y),
      ativo: !!f.ativo,
    };
    try {
      if (q) await Api.put(`/api/wms/quadras/${q.id}`, dados);
      else await Api.post('/api/wms/quadras', dados);
      UI.modalSalvo();
      UI.sucesso('Quadra salva.');
      WMSEntrada._quadras = await Api.get('/api/wms/quadras', { empresa_id: Estado.empresaId });
      WMSEntrada.listaQuadras();
      if (WMS._tipo === 'ENTRADA') WMSEntrada.desenhar();
    } catch (e) {
      UI.erro(e.message);
    }
  },
};
