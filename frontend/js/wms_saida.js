/* WMS — Guia de saída (tela Saídas).

   Cabeçalho: data, número, armazém, cliente (dono do café), contrato (de venda
   ou corretagem), destinatário e destino, documento, placa e motorista.

   Embaixo aparecem os lotes que o cliente tem naquele armazém, uma linha por
   posição (quadra + pilha) com o que resta nela. Em cada linha se digita
   quantas sacas saem — pode ser só uma parte — ou se aperta "Tudo". As sacas
   e o peso da guia são a soma disso.

   "Salvar" grava o rascunho. "Fechar guia" confere que cada pilha e o saldo do
   lote aguentam a saída e tira do saldo. "Reabrir" devolve. */
const WMSSaida = {
  _dados: null,
  _contratos: null,
  _guia: null,
  _disp: [],            // posições disponíveis do cliente no armazém
  _filtroLote: '',
  _filtros: { de: '', ate: '', armazem_id: '', cliente_id: '', status: '', busca: '' },

  async tela() {
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';
    try {
      await WMSSaida.carregar();
    } catch (e) {
      alvo.innerHTML = `<div class="cartao"><div class="vazio">${UI.escapar(e.message)}</div></div>`;
    }
  },

  async carregar() {
    const eid = Estado.empresaId;
    const [armazens, dados] = await Promise.all([
      Api.get('/api/wms/armazens', { empresa_id: eid }),
      Api.get('/api/wms/guias-saida', { empresa_id: eid, ...WMSSaida._filtros }),
    ]);
    WMS._armazens = armazens;
    WMSSaida._dados = dados;
    WMSSaida.desenhar();
  },

  /* ------------------------------------------------------------- a lista */
  desenhar() {
    const d = WMSSaida._dados || { guias: [], resumo: {} };
    const r = d.resumo || {};
    const f = WMSSaida._filtros;
    document.getElementById('pagina').innerHTML = `
      <div class="grade g4" style="margin-bottom:12px">
        ${WMS.cartao('Guias', String(r.guias || 0), 'no filtro abaixo', 'azul')}
        ${WMS.cartao('Abertas', String(r.abertas || 0), 'ainda não tiraram do saldo', r.abertas ? 'ambar' : '')}
        ${WMS.cartao('Sacas', UI.numero(r.sacas, 2), 'que saíram', 'verde')}
        ${WMS.cartao('Peso', `${UI.numero(r.peso_kg, 0)} kg`, 'somado das guias', '')}
      </div>
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Guias de saída</h3>
            <div class="mini">escolha o cliente, o lote e de que quadra/pilha sai — pode ser só uma parte; ao fechar, sai do saldo</div></div>
          <div class="espaco">
            <button class="btn" id="wms-saldo">Saldo do armazém</button>
            <button class="btn" id="wms-exportar">Exportar</button>
            <button class="btn btn-primario" id="wms-novo">Nova guia de saída</button>
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
            ${UI.campo('Procurar', `<input name="busca" value="${UI.escapar(f.busca)}" placeholder="número, destino, documento, placa">`)}
          </div>
          <div id="lista-wms" style="margin-top:12px">${UI.tabela({
            vazio: 'Nenhuma guia de saída neste filtro.',
            colunas: [
              { titulo: 'Nº', chave: 'numero', valor: (g) => `<b>${g.numero}</b>` },
              { titulo: 'Data', valor: (g) => UI.data(g.data) },
              { titulo: 'Cliente', valor: (g) => UI.escapar(g.cliente_nome) },
              { titulo: 'Destino', valor: (g) => `${UI.escapar(g.destinatario_nome || '—')}
                ${g.destino ? `<div class="mini">${UI.escapar(g.destino)}</div>` : ''}` },
              { titulo: 'Contrato', valor: (g) => UI.escapar(g.contrato_numero || '—') },
              { titulo: 'Lotes', valor: (g) => `<span class="mini">${UI.escapar((g.lotes || []).join(', ') || '—')}</span>` },
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
    WMSSaida.ligar();
  },

  ligar() {
    const pagina = document.getElementById('pagina');
    pagina.querySelector('#wms-novo').onclick = () => WMSSaida.nova();
    pagina.querySelector('#wms-saldo').onclick = () => WMS.saldo();
    pagina.querySelector('#wms-exportar').onclick = () =>
      UI.exportarTabela('wms-guias-saida', '#lista-wms table');
    ['de', 'ate', 'armazem_id', 'cliente_id', 'status'].forEach((nome) => {
      const campo = pagina.querySelector(`[name="${nome}"]`);
      campo.onchange = () => { WMSSaida._filtros[nome] = campo.value; WMSSaida.carregar(); };
    });
    const busca = pagina.querySelector('[name="busca"]');
    let tempo = null;
    busca.oninput = () => {
      clearTimeout(tempo);
      tempo = setTimeout(() => { WMSSaida._filtros.busca = busca.value; WMSSaida.carregar(); }, 400);
    };
    pagina.querySelectorAll('[data-abrir]').forEach((b) => {
      b.onclick = () => WMSSaida.abrir(WMSSaida._dados.guias[Number(b.dataset.abrir)].id);
    });
  },

  /* ------------------------------------------------------------- o editor */
  async nova() {
    const armazens = WMS.armazensAtivos();
    if (!armazens.length) return UI.erro('Cadastre primeiro o armazém (tela Entrada > Armazéns).');
    WMSSaida._guia = {
      id: null, numero: null, status: 'ABERTA', data: UI.hoje(),
      armazem_id: armazens.length === 1 ? armazens[0].id : '',
      cliente_id: '', destinatario_id: '', destino: '', contrato_id: '',
      documento: '', placa: '', motorista: '', observacao: '', itens: [],
    };
    WMSSaida._filtroLote = '';
    await WMSSaida.editor();
  },

  async abrir(id) {
    try {
      WMSSaida._guia = await Api.get(`/api/wms/guias-saida/${id}`);
    } catch (e) { return UI.erro(e.message); }
    WMSSaida._filtroLote = '';
    await WMSSaida.editor();
  },

  async editor() {
    if (!WMSSaida._contratos) {
      WMSSaida._contratos = await Api.get('/api/wms/contratos-saida', { empresa_id: Estado.empresaId })
        .catch(() => []);
    }
    const g = WMSSaida._guia;
    UI.abrirModal({
      titulo: g.id ? `Guia de saída nº ${g.numero}` : 'Nova guia de saída',
      largo: true, corpo: '<div id="saida-editor"></div>', botoes: [],
      aoSalvar: g.status === 'ABERTA' ? () => WMSSaida.salvar(false) : null,
    });
    await WMSSaida.carregarDisponivel();
    WMSSaida.render();
  },

  editavel() {
    return WMSSaida._guia.status === 'ABERTA';
  },

  async carregarDisponivel() {
    const g = WMSSaida._guia;
    WMSSaida._disp = [];
    if (!WMSSaida.editavel() || !g.armazem_id || !g.cliente_id) return;
    try {
      WMSSaida._disp = await Api.get('/api/wms/posicoes-disponiveis', {
        empresa_id: Estado.empresaId, armazem_id: g.armazem_id, cliente_id: g.cliente_id,
      });
    } catch (e) { UI.erro(e.message); }
  },

  /* As linhas da tabela: tudo o que está disponível, mais o que a guia já tem. */
  linhas() {
    const g = WMSSaida._guia;
    const porPos = {};
    (g.itens || []).forEach((i) => { porPos[i.posicao_id] = i; });
    const linhas = WMSSaida._disp.map((d) => ({ ...d, item: porPos[d.posicao_id] }));
    (g.itens || []).forEach((i) => {
      if (!linhas.some((l) => String(l.posicao_id) === String(i.posicao_id))) {
        linhas.push({
          posicao_id: i.posicao_id, lote_codigo: i.lote_codigo, peneira: i.peneira, padrao: i.padrao,
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
    const g = WMSSaida._guia;
    const ed = WMSSaida.editavel();
    const dis = ed ? '' : 'disabled';
    const deps = WMS.depositantes().map((p) => ({ valor: p.id, rotulo: p.nome }));
    const contratos = (WMSSaida._contratos || []).map((c) => ({
      valor: c.id,
      rotulo: `${c.numero} — ${c.comprador_nome || c.vendedor_nome || ''} · ${UI.numero(c.quantidade, 0)} (embarcado ${UI.numero(c.sacas_embarcadas, 0)} sc)`,
    }));
    const filtro = WMSSaida._filtroLote.trim().toUpperCase();
    const linhas = WMSSaida.linhas().filter((l) => !filtro
      || String(l.lote_codigo).toUpperCase().includes(filtro)
      || String(l.quadra_nome).toUpperCase().includes(filtro)
      || String(l.padrao || '').toUpperCase().includes(filtro));

    const area = document.getElementById('saida-editor');
    area.innerHTML = `
      ${g.status !== 'ABERTA' ? `<div class="ok-caixa" style="margin-bottom:12px">
        Guia ${WMSEntrada.STATUS[g.status].toLowerCase()}${g.status === 'FECHADA'
          ? ' — o café já saiu do saldo. Para mudar alguma coisa, reabra a guia.' : '.'}</div>` : ''}
      <div class="linha-campos saida-cab">
        ${UI.campo('Data', `<input type="date" name="data" value="${g.data || ''}" ${dis}>`)}
        ${UI.campo('Número', `<input value="${g.numero || 'automático'}" disabled>`)}
        ${UI.campo('Armazém *', UI.select('armazem_id',
          WMS._armazens.filter((a) => a.ativo || String(a.id) === String(g.armazem_id))
            .map((a) => ({ valor: a.id, rotulo: a.nome })), g.armazem_id, { vazio: 'Escolha', attr: dis }))}
        ${UI.campo('Cliente *', UI.select('cliente_id', deps, g.cliente_id, { vazio: 'Escolha', attr: dis }),
          'dono do café que vai sair')}
        ${UI.campo('Contrato', UI.select('contrato_id', contratos, g.contrato_id, { vazio: '— sem contrato —', attr: dis }),
          'venda ou corretagem')}
        ${UI.campo('Destinatário', UI.select('destinatario_id', deps, g.destinatario_id, { vazio: '—', attr: dis }),
          'quem recebe')}
        ${UI.campo('Destino', `<input name="destino" maxlength="200" value="${UI.escapar(g.destino || '')}" placeholder="local / cidade" ${dis}>`)}
        ${UI.campo('Documento', `<input name="documento" maxlength="40" value="${UI.escapar(g.documento || '')}" placeholder="nota, romaneio" ${dis}>`)}
        ${UI.campo('Placa', `<input name="placa" maxlength="10" style="text-transform:uppercase" value="${UI.escapar(g.placa || '')}" ${dis}>`)}
        ${UI.campo('Motorista', `<input name="motorista" maxlength="120" value="${UI.escapar(g.motorista || '')}" ${dis}>`)}
        ${UI.campo('Observação', `<input name="observacao" maxlength="300" value="${UI.escapar(g.observacao || '')}" ${dis}>`)}
      </div>

      <div id="saida-total" class="guia-conferencia"></div>

      <div class="saida-lotes-topo">
        <h4 style="margin:0">${ed ? 'Lotes do cliente — de onde sai' : 'O que saiu'}</h4>
        ${ed && WMSSaida.linhas().length ? `<input name="filtro_lote" data-nao-suja placeholder="procurar lote, quadra, padrão"
          value="${UI.escapar(WMSSaida._filtroLote)}" style="max-width:260px">` : ''}
      </div>
      ${ed && (!g.armazem_id || !g.cliente_id)
        ? '<div class="vazio">Escolha o armazém e o cliente para ver os lotes dele.</div>'
        : !linhas.length
          ? `<div class="vazio">${ed ? 'Este cliente não tem café com posição neste armazém.' : 'Nenhum item.'}</div>`
          : `<div class="tabela-wrap"><table class="tabela-simples saida-tabela">
          <thead><tr>
            <th>Lote</th><th>Quadra</th><th>Pilha</th>
            ${ed ? '<th style="text-align:right">Disponível</th>' : ''}
            <th style="text-align:right">Sai (sacas)</th><th style="text-align:right">Peso (kg)</th>${ed ? '<th></th>' : ''}
          </tr></thead>
          <tbody>${linhas.map((l, idx, todas) => {
            const novoLote = idx === 0 || todas[idx - 1].lote_codigo !== l.lote_codigo;
            return `<tr data-pos="${l.posicao_id}" class="${novoLote ? 'saida-novo-lote' : ''} ${l.item && Number(l.item.sacas) ? 'saida-marcada' : ''}">
              <td>${novoLote ? `<b>${UI.escapar(l.lote_codigo)}</b>
                <div class="mini">${UI.escapar([l.peneira ? `pen. ${l.peneira}` : '', l.padrao || ''].filter(Boolean).join(' · '))}${
                  l.saldo_lote != null ? `${l.peneira || l.padrao ? ' · ' : ''}saldo ${UI.numero(l.saldo_lote, 2)} sc` : ''}</div>` : ''}</td>
              <td>${UI.escapar(l.quadra_nome)}</td>
              <td>${UI.escapar(l.pilha || '—')}</td>
              ${ed ? `<td class="direita">${l.sacas_disponiveis != null ? `${UI.numero(l.sacas_disponiveis, 2)} sc
                <div class="mini">${UI.numero(l.peso_disponivel, 0)} kg</div>` : '—'}</td>` : ''}
              <td class="direita"><input name="sacas" inputmode="decimal" value="${WMSSaida.v(l.item?.sacas)}" style="width:100px;text-align:right" ${dis}></td>
              <td class="direita"><input name="peso" inputmode="decimal" value="${WMSSaida.v(l.item?.peso)}" style="width:110px;text-align:right" placeholder="${ed ? 'proporcional' : ''}" ${dis}></td>
              ${ed ? `<td><button type="button" class="btn btn-mini" data-tudo="${l.posicao_id}" ${l.sacas_disponiveis ? '' : 'disabled'}>Tudo</button></td>` : ''}
            </tr>`;
          }).join('')}</tbody></table></div>`}`;

    WMSSaida.botoes();
    WMSSaida.ligarEditor(area);
    WMSSaida.somar();
  },

  botoes() {
    const g = WMSSaida._guia;
    const b = [];
    if (g.status === 'ABERTA') {
      if (g.id) b.push({ rotulo: 'Cancelar guia', classe: 'btn-perigo', acao: () => WMSSaida.cancelar() });
      b.push({ rotulo: 'Salvar', acao: () => WMSSaida.salvar(false) });
      b.push({ rotulo: 'Fechar guia e tirar do saldo', classe: 'btn-primario', acao: () => WMSSaida.salvar(true) });
    } else {
      if (g.status === 'FECHADA') b.push({ rotulo: 'Reabrir guia', acao: () => WMSSaida.reabrir() });
      b.push({ rotulo: 'Fechar janela', classe: 'btn-primario', acao: () => UI.fecharModal() });
    }
    UI.trocarBotoes(b);
  },

  /* Lê da tela: o cabeçalho e as linhas com sacas. As linhas que o filtro
     escondeu continuam valendo — ficam guardadas no estado. */
  ler() {
    const g = WMSSaida._guia;
    if (!WMSSaida.editavel()) return g;
    const area = document.getElementById('saida-editor');
    const cab = area.querySelector('.saida-cab');
    ['data', 'armazem_id', 'cliente_id', 'destinatario_id', 'destino', 'contrato_id',
      'documento', 'placa', 'motorista', 'observacao'].forEach((n) => {
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
    const g = WMSSaida.ler();
    const area = document.getElementById('saida-editor');
    const sacas = g.itens.reduce((s, i) => s + Number(i.sacas || 0), 0);
    const peso = g.itens.reduce((s, i) => s + Number(i.peso || 0), 0);
    const disp = {};
    WMSSaida._disp.forEach((d) => { disp[d.posicao_id] = d; });
    const lotes = new Set(g.itens.map((i) => disp[i.posicao_id]?.lote_codigo || i.lote_codigo));
    const passou = g.itens.filter((i) => disp[i.posicao_id]
      && Number(i.sacas) > Number(disp[i.posicao_id].sacas_disponiveis) + 0.004);
    area.querySelector('#saida-total').innerHTML = sacas
      ? `<span>Saindo: <b>${UI.numero(sacas, 2)} sacas</b>${peso ? ` · ${UI.numero(peso, 0)} kg digitados` : ''}
         em ${lotes.size} lote(s) e ${g.itens.length} posição(ões)</span>
         ${passou.length ? `<span class="negativo">· ${passou.length} linha(s) acima do disponível</span>` : ''}`
      : '<span class="mini">Digite em cada linha quantas sacas saem daquela quadra/pilha — ou aperte "Tudo".</span>';
    area.querySelectorAll('tr[data-pos]').forEach((tr) => {
      const d = disp[tr.dataset.pos];
      const sc = WMS.numero(tr.querySelector('[name="sacas"]').value);
      tr.classList.toggle('saida-marcada', sc > 0);
      tr.classList.toggle('saida-passou', !!d && sc > Number(d.sacas_disponiveis) + 0.004);
    });
  },

  ligarEditor(area) {
    if (!WMSSaida.editavel()) return;
    area.oninput = (e) => { if (e.target.name !== 'filtro_lote') WMSSaida.somar(); };
    area.onfocusin = (e) => {
      if (e.target.matches('input[inputmode="decimal"]') && e.target.value) e.target.select();
    };
    const cab = area.querySelector('.saida-cab');
    // trocar armazém ou cliente muda os lotes que podem sair
    ['armazem_id', 'cliente_id'].forEach((n) => {
      cab.querySelector(`[name="${n}"]`).onchange = async () => {
        const g = WMSSaida.ler();
        g.itens = [];
        UI._sujo = true;
        await WMSSaida.carregarDisponivel();
        WMSSaida.render();
      };
    });
    // o contrato preenche quem recebe e para onde vai
    cab.querySelector('[name="contrato_id"]').onchange = (e) => {
      const c = (WMSSaida._contratos || []).find((x) => String(x.id) === e.target.value);
      const g = WMSSaida.ler();
      if (c) {
        if (c.comprador_id && !g.destinatario_id) g.destinatario_id = c.comprador_id;
        if (c.local_descarga && !g.destino) g.destino = c.local_descarga;
      }
      UI._sujo = true;
      WMSSaida.render();
    };
    const filtro = area.querySelector('[name="filtro_lote"]');
    if (filtro) {
      let tempo = null;
      filtro.oninput = () => {
        clearTimeout(tempo);
        tempo = setTimeout(() => {
          WMSSaida.ler();
          WMSSaida._filtroLote = filtro.value;
          WMSSaida.render();
          const novo = document.querySelector('#saida-editor [name="filtro_lote"]');
          if (novo) { novo.focus(); novo.setSelectionRange(novo.value.length, novo.value.length); }
        }, 300);
      };
    }
    area.querySelectorAll('[data-tudo]').forEach((b) => {
      b.onclick = () => {
        const d = WMSSaida._disp.find((x) => String(x.posicao_id) === b.dataset.tudo);
        const tr = b.closest('tr');
        if (!d || !tr) return;
        tr.querySelector('[name="sacas"]').value = UI.numero(d.sacas_disponiveis, 2);
        tr.querySelector('[name="peso"]').value = d.peso_disponivel ? UI.numero(d.peso_disponivel, 2) : '';
        UI._sujo = true;
        WMSSaida.somar();
      };
    });
  },

  corpoParaApi() {
    const g = WMSSaida.ler();
    const id = (v) => (v ? Number(v) : null);
    return {
      empresa_id: Estado.empresaId,
      data: g.data,
      armazem_id: id(g.armazem_id),
      cliente_id: id(g.cliente_id),
      destinatario_id: id(g.destinatario_id),
      destino: g.destino,
      contrato_id: id(g.contrato_id),
      documento: g.documento,
      placa: g.placa ? String(g.placa).toUpperCase() : '',
      motorista: g.motorista,
      observacao: g.observacao,
      itens: g.itens.map((i) => ({ posicao_id: Number(i.posicao_id), sacas: i.sacas, peso: i.peso || 0 })),
    };
  },

  async salvar(fechar) {
    const g = WMSSaida._guia;
    const corpo = WMSSaida.corpoParaApi();
    try {
      let salva = g.id
        ? await Api.put(`/api/wms/guias-saida/${g.id}`, corpo)
        : await Api.post('/api/wms/guias-saida', corpo);
      WMSSaida._guia = salva;
      UI.modalSalvo();
      if (fechar) {
        try {
          salva = await Api.post(`/api/wms/guias-saida/${salva.id}/fechar`);
        } catch (e) {
          await WMSSaida.carregarDisponivel();
          WMSSaida.render();
          WMSSaida.carregar();
          return UI.erro(e.message);
        }
        UI.fecharModal();
        UI.sucesso(`Guia de saída ${salva.numero} fechada: ${UI.numero(salva.sacas, 2)} sacas saíram do saldo.`);
      } else {
        await WMSSaida.carregarDisponivel();
        WMSSaida.render();
        UI.sucesso(`Guia de saída ${salva.numero} salva (aberta).`);
      }
      await WMSSaida.carregar();
    } catch (e) {
      UI.erro(e.message);
    }
  },

  async reabrir() {
    const g = WMSSaida._guia;
    if (!await UI.confirmar(`Reabrir a guia de saída ${g.numero}? As sacas voltam para o saldo até ela ser fechada de novo.`, 'Reabrir')) {
      return WMSSaida.abrir(g.id);
    }
    try {
      await Api.post(`/api/wms/guias-saida/${g.id}/reabrir`);
      UI.sucesso(`Guia de saída ${g.numero} reaberta.`);
      await WMSSaida.carregar();
    } catch (e) {
      UI.erro(e.message);
    }
    await WMSSaida.abrir(g.id);
  },

  cancelar() {
    const g = WMSSaida._guia;
    const corpo = UI.abrirModal({
      titulo: `Cancelar a guia de saída ${g.numero}`,
      corpo: `<p style="margin-top:0">A guia fica na lista como cancelada e não tira nada do saldo.</p>
        ${UI.campo('Motivo *', '<input name="motivo" maxlength="200" placeholder="ex.: carga não veio">')}`,
      botoes: [
        { rotulo: 'Voltar', acao: () => WMSSaida.abrir(g.id) },
        { rotulo: 'Cancelar guia', classe: 'btn-perigo', acao: async () => {
          try {
            await Api.post(`/api/wms/guias-saida/${g.id}/cancelar`, { motivo: corpo.querySelector('[name="motivo"]').value });
            UI.modalSalvo();
            UI.fecharModal();
            UI.sucesso('Guia de saída cancelada.');
            await WMSSaida.carregar();
          } catch (e) { UI.erro(e.message); }
        } },
      ],
    });
  },
};
