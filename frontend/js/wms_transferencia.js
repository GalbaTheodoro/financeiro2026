/* WMS — Guia de transferência (tela Transferências): troca de dono do lote.

   Cabeçalho: data, número, armazém, cliente (dono atual) e cliente novo.
   Embaixo aparecem os lotes do cliente naquele armazém, uma linha por posição
   (quadra + pilha) com o que resta nela; em cada linha se digita quantas sacas
   passam para o cliente novo — pode ser só uma parte — ou se aperta "Tudo".

   Ao fechar, cada lote de origem gera um lote novo do cliente novo com o
   número do lote de origem + "T" (1/1 -> 1/1T; se já existir, 1/1T2...), nas
   mesmas quadras e pilhas. "Reabrir" desfaz, enquanto o lote novo não saiu. */
const WMSTransf = {
  _dados: null,
  _guia: null,
  _disp: [],            // posições disponíveis do cliente no armazém
  _filtroLote: '',
  _filtros: { de: '', ate: '', armazem_id: '', cliente_id: '', status: '', busca: '' },

  async tela() {
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';
    try {
      await WMSTransf.carregar();
    } catch (e) {
      alvo.innerHTML = `<div class="cartao"><div class="vazio">${UI.escapar(e.message)}</div></div>`;
    }
  },

  async carregar() {
    const eid = Estado.empresaId;
    const [armazens, dados] = await Promise.all([
      Api.get('/api/wms/armazens', { empresa_id: eid }),
      Api.get('/api/wms/guias-transferencia', { empresa_id: eid, ...WMSTransf._filtros }),
    ]);
    WMS._armazens = armazens;
    WMSTransf._dados = dados;
    WMSTransf.desenhar();
  },

  /* ------------------------------------------------------------- a lista */
  desenhar() {
    const d = WMSTransf._dados || { guias: [], resumo: {} };
    const r = d.resumo || {};
    const f = WMSTransf._filtros;
    document.getElementById('pagina').innerHTML = `
      <div class="grade g4" style="margin-bottom:12px">
        ${WMS.cartao('Guias', String(r.guias || 0), 'no filtro abaixo', 'azul')}
        ${WMS.cartao('Abertas', String(r.abertas || 0), 'ainda não geraram o lote novo', r.abertas ? 'ambar' : '')}
        ${WMS.cartao('Sacas', UI.numero(r.sacas, 2), 'que mudaram de dono', 'verde')}
        ${WMS.cartao('Peso', `${UI.numero(r.peso_kg, 0)} kg`, 'somado das guias', '')}
      </div>
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Guias de transferência</h3>
            <div class="mini">o café muda de dono sem sair do lugar — escolha os lotes (pode ser parte); ao fechar, nasce o lote novo com T no fim</div></div>
          <div class="espaco">
            <button class="btn" id="wms-saldo">Saldo do armazém</button>
            <button class="btn" id="wms-exportar">Exportar</button>
            <button class="btn btn-primario" id="wms-novo">Nova guia de transferência</button>
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
            ${UI.campo('Procurar', `<input name="busca" value="${UI.escapar(f.busca)}" placeholder="número, documento">`)}
          </div>
          <div id="lista-wms" style="margin-top:12px">${UI.tabela({
            vazio: 'Nenhuma guia de transferência neste filtro.',
            colunas: [
              { titulo: 'Nº', chave: 'numero', valor: (g) => `<b>${g.numero}</b>` },
              { titulo: 'Data', valor: (g) => UI.data(g.data) },
              { titulo: 'De → Para', valor: (g) => `${UI.escapar(g.cliente_nome)}
                <div class="mini">→ ${UI.escapar(g.cliente_novo_nome)}</div>` },
              { titulo: 'Lotes', valor: (g) => `<span class="mini">${UI.escapar((g.lotes || []).join(', ') || '—')}${
                (g.lotes_novos || []).length ? ` → <b>${UI.escapar(g.lotes_novos.join(', '))}</b>` : ''}</span>` },
              { titulo: 'Sacas', classe: 'direita', chave: 'sacas', valor: (g) => `<b>${UI.numero(g.sacas, 2)}</b>` },
              { titulo: 'Peso (kg)', classe: 'direita', chave: 'peso', valor: (g) => UI.numero(g.peso, 0) },
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
    WMSTransf.ligar();
  },

  ligar() {
    const pagina = document.getElementById('pagina');
    pagina.querySelector('#wms-novo').onclick = () => WMSTransf.nova();
    pagina.querySelector('#wms-saldo').onclick = () => WMS.saldo();
    pagina.querySelector('#wms-exportar').onclick = () =>
      UI.exportarTabela('wms-guias-transferencia', '#lista-wms table');
    ['de', 'ate', 'armazem_id', 'cliente_id', 'status'].forEach((nome) => {
      const campo = pagina.querySelector(`[name="${nome}"]`);
      campo.onchange = () => { WMSTransf._filtros[nome] = campo.value; WMSTransf.carregar(); };
    });
    const busca = pagina.querySelector('[name="busca"]');
    let tempo = null;
    busca.oninput = () => {
      clearTimeout(tempo);
      tempo = setTimeout(() => { WMSTransf._filtros.busca = busca.value; WMSTransf.carregar(); }, 400);
    };
    pagina.querySelectorAll('[data-abrir]').forEach((b) => {
      b.onclick = () => WMSTransf.abrir(WMSTransf._dados.guias[Number(b.dataset.abrir)].id);
    });
  },

  /* ------------------------------------------------------------- o editor */
  async nova() {
    const armazens = WMS.armazensAtivos();
    if (!armazens.length) return UI.erro('Cadastre primeiro o armazém (tela Entrada > Armazéns).');
    WMSTransf._guia = {
      id: null, numero: null, status: 'ABERTA', data: UI.hoje(),
      armazem_id: armazens.length === 1 ? armazens[0].id : '',
      cliente_id: '', cliente_novo_id: '', documento: '', observacao: '', itens: [],
    };
    WMSTransf._filtroLote = '';
    await WMSTransf.editor();
  },

  async abrir(id) {
    try {
      WMSTransf._guia = await Api.get(`/api/wms/guias-transferencia/${id}`);
    } catch (e) { return UI.erro(e.message); }
    WMSTransf._filtroLote = '';
    await WMSTransf.editor();
  },

  async editor() {
    const g = WMSTransf._guia;
    UI.abrirModal({
      titulo: g.id ? `Guia de transferência nº ${g.numero}` : 'Nova guia de transferência',
      largo: true, corpo: '<div id="transf-editor"></div>', botoes: [],
      aoSalvar: g.status === 'ABERTA' ? () => WMSTransf.salvar(false) : null,
    });
    await WMSTransf.carregarDisponivel();
    WMSTransf.render();
  },

  editavel() {
    return WMSTransf._guia.status === 'ABERTA';
  },

  async carregarDisponivel() {
    const g = WMSTransf._guia;
    WMSTransf._disp = [];
    if (!WMSTransf.editavel() || !g.armazem_id || !g.cliente_id) return;
    try {
      WMSTransf._disp = await Api.get('/api/wms/posicoes-disponiveis', {
        empresa_id: Estado.empresaId, armazem_id: g.armazem_id, cliente_id: g.cliente_id,
      });
    } catch (e) { UI.erro(e.message); }
  },

  /* As linhas da tabela: tudo o que está disponível, mais o que a guia já tem. */
  linhas() {
    const g = WMSTransf._guia;
    const porPos = {};
    (g.itens || []).forEach((i) => { porPos[i.posicao_id] = i; });
    const linhas = WMSTransf._disp.map((d) => ({ ...d, item: porPos[d.posicao_id] }));
    (g.itens || []).forEach((i) => {
      if (!linhas.some((l) => String(l.posicao_id) === String(i.posicao_id))) {
        linhas.push({
          posicao_id: i.posicao_id, lote_codigo: i.lote_codigo, lote_novo_codigo: i.lote_novo_codigo,
          peneira: i.peneira, padrao: i.padrao,
          quadra_nome: i.quadra_nome, pilha: i.pilha, sacas_disponiveis: null, peso_disponivel: null,
          saldo_lote: null, item: i,
        });
      }
    });
    return linhas;
  },

  v(n, casas = 2) {
    return Number(n) ? UI.numero(n, casas) : '';
  },

  render() {
    const g = WMSTransf._guia;
    const ed = WMSTransf.editavel();
    const dis = ed ? '' : 'disabled';
    const deps = WMS.depositantes().map((p) => ({ valor: p.id, rotulo: p.nome }));
    const filtro = WMSTransf._filtroLote.trim().toUpperCase();
    const linhas = WMSTransf.linhas().filter((l) => !filtro
      || String(l.lote_codigo).toUpperCase().includes(filtro)
      || String(l.quadra_nome).toUpperCase().includes(filtro)
      || String(l.padrao || '').toUpperCase().includes(filtro));

    const area = document.getElementById('transf-editor');
    area.innerHTML = `
      ${g.status !== 'ABERTA' ? `<div class="ok-caixa" style="margin-bottom:12px">
        Guia ${WMSEntrada.STATUS[g.status].toLowerCase()}${g.status === 'FECHADA'
          ? ` — gerou o(s) lote(s) <b>${UI.escapar((g.lotes_novos || []).join(', '))}</b> do cliente novo. Para mudar, reabra a guia (só dá se o lote novo não saiu).`
          : '.'}</div>` : ''}
      <div class="linha-campos transf-cab">
        ${UI.campo('Data', `<input type="date" name="data" value="${g.data || ''}" ${dis}>`)}
        ${UI.campo('Número', `<input value="${g.numero || 'automático'}" disabled>`)}
        ${UI.campo('Armazém *', UI.select('armazem_id',
          WMS._armazens.filter((a) => a.ativo || String(a.id) === String(g.armazem_id))
            .map((a) => ({ valor: a.id, rotulo: a.nome })), g.armazem_id, { vazio: 'Escolha', attr: dis }))}
        ${UI.campo('Cliente *', UI.select('cliente_id', deps, g.cliente_id, { vazio: 'Escolha', attr: dis }),
          'dono atual do café')}
        ${UI.campo('Cliente novo *', UI.select('cliente_novo_id', deps, g.cliente_novo_id, { vazio: 'Escolha', attr: dis }),
          'quem passa a ser o dono')}
        ${UI.campo('Documento', `<input name="documento" maxlength="40" value="${UI.escapar(g.documento || '')}" placeholder="contrato, autorização" ${dis}>`)}
        ${UI.campo('Observação', `<input name="observacao" maxlength="300" value="${UI.escapar(g.observacao || '')}" ${dis}>`)}
      </div>

      <div id="transf-total" class="guia-conferencia"></div>

      <div class="saida-lotes-topo">
        <h4 style="margin:0">${ed ? 'Lotes do cliente — o que muda de dono' : 'O que foi transferido'}</h4>
        ${ed && WMSTransf.linhas().length ? `<input name="filtro_lote" data-nao-suja placeholder="procurar lote, quadra, padrão"
          value="${UI.escapar(WMSTransf._filtroLote)}" style="max-width:260px">` : ''}
      </div>
      ${ed && (!g.armazem_id || !g.cliente_id)
        ? '<div class="vazio">Escolha o armazém e o cliente para ver os lotes dele.</div>'
        : !linhas.length
          ? `<div class="vazio">${ed ? 'Este cliente não tem café com posição neste armazém.' : 'Nenhum item.'}</div>`
          : `<div class="tabela-wrap"><table class="tabela-simples saida-tabela">
          <thead><tr>
            <th>Lote</th><th>Quadra</th><th>Pilha</th>
            ${ed ? '<th style="text-align:right">Disponível</th>' : ''}
            <th style="text-align:right">Transferir (sacas)</th><th style="text-align:right">Peso (kg)</th>${ed ? '<th></th>' : ''}
          </tr></thead>
          <tbody>${linhas.map((l, idx, todas) => {
            const novoLote = idx === 0 || todas[idx - 1].lote_codigo !== l.lote_codigo;
            return `<tr data-pos="${l.posicao_id}" class="${novoLote ? 'saida-novo-lote' : ''} ${l.item && Number(l.item.sacas) ? 'saida-marcada' : ''}">
              <td>${novoLote ? `<b>${UI.escapar(l.lote_codigo)}</b>
                <div class="mini">${UI.escapar([l.peneira ? `pen. ${l.peneira}` : '', l.padrao || ''].filter(Boolean).join(' · '))}${
                  l.saldo_lote != null ? `${l.peneira || l.padrao ? ' · ' : ''}saldo ${UI.numero(l.saldo_lote, 2)} sc` : ''}</div>
                <div class="mini positivo">→ ${l.lote_novo_codigo ? `lote novo <b>${UI.escapar(l.lote_novo_codigo)}</b>` : `vira ${UI.escapar(l.lote_codigo)}T no cliente novo`}</div>` : ''}</td>
              <td>${UI.escapar(l.quadra_nome)}</td>
              <td>${UI.escapar(l.pilha || '—')}</td>
              ${ed ? `<td class="direita">${l.sacas_disponiveis != null ? `${UI.numero(l.sacas_disponiveis, 2)} sc
                <div class="mini">${UI.numero(l.peso_disponivel, 0)} kg</div>` : '—'}</td>` : ''}
              <td class="direita"><input name="sacas" inputmode="decimal" value="${WMSTransf.v(l.item?.sacas)}" style="width:100px;text-align:right" ${dis}></td>
              <td class="direita"><input name="peso" inputmode="decimal" value="${WMSTransf.v(l.item?.peso)}" style="width:110px;text-align:right" placeholder="${ed ? 'proporcional' : ''}" ${dis}></td>
              ${ed ? `<td><button type="button" class="btn btn-mini" data-tudo="${l.posicao_id}" ${l.sacas_disponiveis ? '' : 'disabled'}>Tudo</button></td>` : ''}
            </tr>`;
          }).join('')}</tbody></table></div>`}`;

    WMSTransf.botoes();
    WMSTransf.ligarEditor(area);
    WMSTransf.somar();
  },

  botoes() {
    const g = WMSTransf._guia;
    const b = [];
    if (g.status === 'ABERTA') {
      if (g.id) b.push({ rotulo: 'Cancelar guia', classe: 'btn-perigo', acao: () => WMSTransf.cancelar() });
      b.push({ rotulo: 'Salvar', acao: () => WMSTransf.salvar(false) });
      b.push({ rotulo: 'Fechar guia e gerar lote novo', classe: 'btn-primario', acao: () => WMSTransf.salvar(true) });
    } else {
      if (g.status === 'FECHADA') b.push({ rotulo: 'Reabrir guia', acao: () => WMSTransf.reabrir() });
      b.push({ rotulo: 'Fechar janela', classe: 'btn-primario', acao: () => UI.fecharModal() });
    }
    UI.trocarBotoes(b);
  },

  /* Lê da tela: o cabeçalho e as linhas com sacas. As linhas que o filtro
     escondeu continuam valendo — ficam guardadas no estado. */
  ler() {
    const g = WMSTransf._guia;
    if (!WMSTransf.editavel()) return g;
    const area = document.getElementById('transf-editor');
    const cab = area.querySelector('.transf-cab');
    ['data', 'armazem_id', 'cliente_id', 'cliente_novo_id', 'documento', 'observacao'].forEach((n) => {
      g[n] = cab.querySelector(`[name="${n}"]`)?.value ?? '';
    });
    const itens = {};
    (g.itens || []).forEach((i) => { itens[i.posicao_id] = { ...i }; });
    area.querySelectorAll('tr[data-pos]').forEach((tr) => {
      const pid = Number(tr.dataset.pos);
      const sacas = WMS.numero(tr.querySelector('[name="sacas"]').value);
      const peso = WMS.numero(tr.querySelector('[name="peso"]').value);
      if (sacas > 0) itens[pid] = { ...(itens[pid] || {}), posicao_id: pid, sacas, peso };
      else delete itens[pid];
    });
    g.itens = Object.values(itens);
    return g;
  },

  somar() {
    const g = WMSTransf.ler();
    const area = document.getElementById('transf-editor');
    const sacas = g.itens.reduce((s, i) => s + Number(i.sacas || 0), 0);
    const peso = g.itens.reduce((s, i) => s + Number(i.peso || 0), 0);
    const disp = {};
    WMSTransf._disp.forEach((d) => { disp[d.posicao_id] = d; });
    const lotes = new Set(g.itens.map((i) => disp[i.posicao_id]?.lote_codigo || i.lote_codigo));
    const passou = g.itens.filter((i) => disp[i.posicao_id]
      && Number(i.sacas) > Number(disp[i.posicao_id].sacas_disponiveis) + 0.004);
    area.querySelector('#transf-total').innerHTML = sacas
      ? `<span>Transferindo: <b>${UI.numero(sacas, 2)} sacas</b>${peso ? ` · ${UI.numero(peso, 0)} kg digitados` : ''}
         em ${lotes.size} lote(s) e ${g.itens.length} posição(ões)</span>
         ${passou.length ? `<span class="negativo">· ${passou.length} linha(s) acima do disponível</span>` : ''}`
      : '<span class="mini">Digite em cada linha quantas sacas daquela quadra/pilha passam para o cliente novo — ou aperte "Tudo".</span>';
    area.querySelectorAll('tr[data-pos]').forEach((tr) => {
      const d = disp[tr.dataset.pos];
      const sc = WMS.numero(tr.querySelector('[name="sacas"]').value);
      tr.classList.toggle('saida-marcada', sc > 0);
      tr.classList.toggle('saida-passou', !!d && sc > Number(d.sacas_disponiveis) + 0.004);
    });
  },

  ligarEditor(area) {
    if (!WMSTransf.editavel()) return;
    area.oninput = (e) => { if (e.target.name !== 'filtro_lote') WMSTransf.somar(); };
    area.onfocusin = (e) => {
      if (e.target.matches('input[inputmode="decimal"]') && e.target.value) e.target.select();
    };
    const cab = area.querySelector('.transf-cab');
    // trocar armazém ou cliente muda os lotes que podem sair
    ['armazem_id', 'cliente_id'].forEach((n) => {
      cab.querySelector(`[name="${n}"]`).onchange = async () => {
        const g = WMSTransf.ler();
        g.itens = [];
        UI._sujo = true;
        await WMSTransf.carregarDisponivel();
        WMSTransf.render();
      };
    });
    const filtro = area.querySelector('[name="filtro_lote"]');
    if (filtro) {
      let tempo = null;
      filtro.oninput = () => {
        clearTimeout(tempo);
        tempo = setTimeout(() => {
          WMSTransf.ler();
          WMSTransf._filtroLote = filtro.value;
          WMSTransf.render();
          const novo = document.querySelector('#transf-editor [name="filtro_lote"]');
          if (novo) { novo.focus(); novo.setSelectionRange(novo.value.length, novo.value.length); }
        }, 300);
      };
    }
    area.querySelectorAll('[data-tudo]').forEach((b) => {
      b.onclick = () => {
        const d = WMSTransf._disp.find((x) => String(x.posicao_id) === b.dataset.tudo);
        const tr = b.closest('tr');
        if (!d || !tr) return;
        tr.querySelector('[name="sacas"]').value = UI.numero(d.sacas_disponiveis, 2);
        tr.querySelector('[name="peso"]').value = d.peso_disponivel ? UI.numero(d.peso_disponivel, 2) : '';
        UI._sujo = true;
        WMSTransf.somar();
      };
    });
  },

  corpoParaApi() {
    const g = WMSTransf.ler();
    const id = (v) => (v ? Number(v) : null);
    return {
      empresa_id: Estado.empresaId,
      data: g.data,
      armazem_id: id(g.armazem_id),
      cliente_id: id(g.cliente_id),
      cliente_novo_id: id(g.cliente_novo_id),
      documento: g.documento,
      observacao: g.observacao,
      itens: g.itens.map((i) => ({ posicao_id: Number(i.posicao_id), sacas: i.sacas, peso: i.peso || 0 })),
    };
  },

  async salvar(fechar) {
    const g = WMSTransf._guia;
    const corpo = WMSTransf.corpoParaApi();
    try {
      let salva = g.id
        ? await Api.put(`/api/wms/guias-transferencia/${g.id}`, corpo)
        : await Api.post('/api/wms/guias-transferencia', corpo);
      WMSTransf._guia = salva;
      UI.modalSalvo();
      if (fechar) {
        try {
          salva = await Api.post(`/api/wms/guias-transferencia/${salva.id}/fechar`);
        } catch (e) {
          await WMSTransf.carregarDisponivel();
          WMSTransf.render();
          WMSTransf.carregar();
          return UI.erro(e.message);
        }
        UI.fecharModal();
        UI.sucesso(`Guia de transferência ${salva.numero} fechada: lote(s) ${(salva.lotes_novos || []).join(', ')} do ${salva.cliente_novo_nome}.`);
      } else {
        await WMSTransf.carregarDisponivel();
        WMSTransf.render();
        UI.sucesso(`Guia de transferência ${salva.numero} salva (aberta).`);
      }
      await WMSTransf.carregar();
    } catch (e) {
      UI.erro(e.message);
    }
  },

  async reabrir() {
    const g = WMSTransf._guia;
    if (!await UI.confirmar(`Reabrir a guia de transferência ${g.numero}? O lote novo some e o café volta para o cliente de origem até ela ser fechada de novo.`, 'Reabrir')) {
      return WMSTransf.abrir(g.id);
    }
    try {
      await Api.post(`/api/wms/guias-transferencia/${g.id}/reabrir`);
      UI.sucesso(`Guia de transferência ${g.numero} reaberta.`);
      await WMSTransf.carregar();
    } catch (e) {
      UI.erro(e.message);
    }
    await WMSTransf.abrir(g.id);
  },

  cancelar() {
    const g = WMSTransf._guia;
    const corpo = UI.abrirModal({
      titulo: `Cancelar a guia de transferência ${g.numero}`,
      corpo: `<p style="margin-top:0">A guia fica na lista como cancelada e não muda o dono de nada.</p>
        ${UI.campo('Motivo *', '<input name="motivo" maxlength="200" placeholder="ex.: negócio desfeito">')}`,
      botoes: [
        { rotulo: 'Voltar', acao: () => WMSTransf.abrir(g.id) },
        { rotulo: 'Cancelar guia', classe: 'btn-perigo', acao: async () => {
          try {
            await Api.post(`/api/wms/guias-transferencia/${g.id}/cancelar`, { motivo: corpo.querySelector('[name="motivo"]').value });
            UI.modalSalvo();
            UI.fecharModal();
            UI.sucesso('Guia de transferência cancelada.');
            await WMSTransf.carregar();
          } catch (e) { UI.erro(e.message); }
        } },
      ],
    });
  },
};
