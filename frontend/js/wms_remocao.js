/* WMS — Remoção: mudar o lote de lugar, com histórico.

   Na lista ficam todas as remoções feitas (o histórico), com quem fez e de
   onde para onde. "Nova remoção": escolhe-se o lote, aparecem todos os locais
   dele (quadra + pilha, com o que resta) e, em cada um, quantas sacas vão e
   para que quadra/pilha. Pode ser só uma parte. Para outro armazém vai o lote
   inteiro. Confirmar já muda — não tem rascunho; errou, estorna.

   Aqui também mora o histórico do lote (WMSRemocao.historico), que a tela de
   Lotes abre pelo botão "Histórico". */
const WMSRemocao = {
  _dados: null,
  _filtros: { de: '', ate: '', armazem_id: '', busca: '' },
  _lotes: [],
  _quadras: [],
  _form: null,     // { lote, posicoes, armazem_destino_id, linhas: {posicao_id: {...}} }

  async tela() {
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';
    try {
      await WMSRemocao.carregar();
    } catch (e) {
      alvo.innerHTML = `<div class="cartao"><div class="vazio">${UI.escapar(e.message)}</div></div>`;
    }
  },

  async carregar() {
    const eid = Estado.empresaId;
    const [armazens, dados] = await Promise.all([
      Api.get('/api/wms/armazens', { empresa_id: eid }),
      Api.get('/api/wms/remocoes', { empresa_id: eid, ...WMSRemocao._filtros }),
    ]);
    WMS._armazens = armazens;
    WMSRemocao._dados = dados;
    WMSRemocao.desenhar();
  },

  /* ---------------------------------------------------------- o histórico */
  desenhar() {
    const d = WMSRemocao._dados || { remocoes: [], resumo: {} };
    const r = d.resumo || {};
    const f = WMSRemocao._filtros;
    document.getElementById('pagina').innerHTML = `
      <div class="grade g4" style="margin-bottom:12px">
        ${WMS.cartao('Remoções', String(r.remocoes || 0), 'ativas no filtro', 'azul')}
        ${WMS.cartao('Sacas', UI.numero(r.sacas, 2), 'que mudaram de lugar', 'verde')}
        ${WMS.cartao('Lotes', String(r.lotes || 0), 'que mudaram de lugar', '')}
        ${WMS.cartao('Estornadas', String(d.remocoes.filter((x) => x.status === 'ESTORNADA').length),
          'continuam no histórico', '')}
      </div>
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Remoções — mudança de local</h3>
            <div class="mini">escolha o lote, veja os locais dele e mude de quadra/pilha — tudo fica no histórico</div></div>
          <div class="espaco">
            <button class="btn" id="wms-exportar">Exportar</button>
            <button class="btn btn-primario" id="wms-novo">Nova remoção</button>
          </div>
        </div>
        <div class="cartao-corpo">
          <div class="linha-campos" data-nao-suja>
            ${UI.campo('De', `<input type="date" name="de" value="${f.de}">`)}
            ${UI.campo('Até', `<input type="date" name="ate" value="${f.ate}">`)}
            ${UI.campo('Armazém', UI.select('armazem_id',
              WMS._armazens.map((a) => ({ valor: a.id, rotulo: a.nome })), f.armazem_id, { vazio: 'Todos' }))}
            ${UI.campo('Lote', `<input name="busca" value="${UI.escapar(f.busca)}" placeholder="número do lote">`)}
          </div>
          <div id="lista-wms" style="margin-top:12px">${UI.tabela({
            vazio: 'Nenhuma remoção neste filtro. Use "Nova remoção" para mudar um lote de lugar.',
            colunas: [
              { titulo: 'Nº', chave: 'numero', valor: (g) => `<b>${g.numero}</b>` },
              { titulo: 'Data', valor: (g) => UI.data(g.data) },
              { titulo: 'Lote', valor: (g) => `<b>${UI.escapar(g.lote_codigo)}</b>
                <div class="mini">${UI.escapar(g.depositante_nome)}</div>` },
              { titulo: 'Mudança', valor: (g) => `${g.armazem_origem_id !== g.armazem_destino_id
                ? `<div class="mini forte">${UI.escapar(g.armazem_origem_nome)} → ${UI.escapar(g.armazem_destino_nome)}</div>` : ''}
                ${g.itens.map((i) => `<div class="mini">${UI.escapar(i.de)} → <b>${UI.escapar(i.para)}</b>: ${UI.numero(i.sacas, 2)} sc</div>`).join('')}
                ${g.observacao ? `<div class="mini">${UI.escapar(g.observacao)}</div>` : ''}` },
              { titulo: 'Sacas', classe: 'direita', chave: 'sacas', valor: (g) => `<b>${UI.numero(g.sacas, 2)}</b>` },
              { titulo: 'Situação', valor: (g) => (g.status === 'ATIVA'
                ? '<span class="tag tag-pago">Feita</span>' : '<span class="tag tag-cancelado">Estornada</span>')
                + (g.usuario_nome ? `<div class="mini">${UI.escapar(g.usuario_nome)}</div>` : '') },
              { titulo: '', classe: 'direita', valor: (g, i) => `
                <button class="btn btn-mini" data-historico="${g.lote_id}">Histórico</button>
                ${g.pode_estornar ? `<button class="btn btn-mini" data-estornar="${i}">Estornar</button>` : ''}` },
            ],
            linhas: d.remocoes,
            rodape: d.remocoes.length ? { numero: `<b>${r.remocoes}</b>`, sacas: `<b>${UI.numero(r.sacas, 2)}</b>` } : null,
          })}</div>
        </div>
      </div>`;
    WMSRemocao.ligar();
  },

  ligar() {
    const pagina = document.getElementById('pagina');
    pagina.querySelector('#wms-novo').onclick = () => WMSRemocao.nova();
    pagina.querySelector('#wms-exportar').onclick = () => UI.exportarTabela('wms-remocoes', '#lista-wms table');
    ['de', 'ate', 'armazem_id'].forEach((nome) => {
      const campo = pagina.querySelector(`[name="${nome}"]`);
      campo.onchange = () => { WMSRemocao._filtros[nome] = campo.value; WMSRemocao.carregar(); };
    });
    const busca = pagina.querySelector('[name="busca"]');
    let tempo = null;
    busca.oninput = () => {
      clearTimeout(tempo);
      tempo = setTimeout(() => { WMSRemocao._filtros.busca = busca.value; WMSRemocao.carregar(); }, 400);
    };
    pagina.querySelectorAll('[data-historico]').forEach((b) => {
      b.onclick = () => WMSRemocao.historico(Number(b.dataset.historico));
    });
    pagina.querySelectorAll('[data-estornar]').forEach((b) => {
      b.onclick = () => WMSRemocao.estornar(WMSRemocao._dados.remocoes[Number(b.dataset.estornar)]);
    });
  },

  async estornar(g) {
    if (!await UI.confirmar(`Estornar a remoção nº ${g.numero} do lote ${g.lote_codigo}? O café volta para os locais de antes (a remoção fica no histórico como estornada).`, 'Estornar')) return;
    try {
      await Api.post(`/api/wms/remocoes/${g.id}/estornar`);
      UI.sucesso(`Remoção nº ${g.numero} estornada.`);
      await WMSRemocao.carregar();
    } catch (e) { UI.erro(e.message); }
  },

  /* ------------------------------------------------------- nova remoção */
  async nova(loteId = null) {
    const eid = Estado.empresaId;
    try {
      const [lotes, quadras, armazens] = await Promise.all([
        Api.get('/api/wms/lotes', { empresa_id: eid, com_saldo: true }),
        Api.get('/api/wms/quadras', { empresa_id: eid }),
        Api.get('/api/wms/armazens', { empresa_id: eid }),
      ]);
      WMSRemocao._lotes = lotes;
      WMSRemocao._quadras = quadras.filter((q) => q.ativo);
      WMS._armazens = armazens;
    } catch (e) { return UI.erro(e.message); }
    if (!WMSRemocao._lotes.length) return UI.erro('Nenhum lote com saldo para mudar de lugar.');
    WMSRemocao._form = { lote: null, posicoes: [], armazem_destino_id: '', linhas: {}, historico: null };
    UI.abrirModal({
      titulo: 'Nova remoção — mudar o lote de lugar',
      largo: true,
      corpo: '<div id="remocao-editor"></div>',
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        { rotulo: 'Confirmar mudança de local', classe: 'btn-primario', acao: () => WMSRemocao.confirmar() },
      ],
      aoSalvar: () => WMSRemocao.confirmar(),
    });
    if (loteId) await WMSRemocao.escolherLote(loteId);
    else WMSRemocao.render();
  },

  async escolherLote(loteId) {
    const f = WMSRemocao._form;
    if (!loteId) {
      Object.assign(f, { lote: null, posicoes: [], linhas: {}, historico: null });
      return WMSRemocao.render();
    }
    try {
      const [loc, hist] = await Promise.all([
        Api.get(`/api/wms/lotes/${loteId}/locais`),
        Api.get(`/api/wms/lotes/${loteId}/historico`),
      ]);
      f.lote = loc.lote;
      f.posicoes = loc.posicoes;
      f.armazem_destino_id = loc.lote.armazem_id;
      f.linhas = {};
      f.historico = hist;
    } catch (e) { UI.erro(e.message); }
    WMSRemocao.render();
  },

  quadrasDoDestino() {
    const f = WMSRemocao._form;
    return WMSRemocao._quadras.filter((q) => String(q.armazem_id) === String(f.armazem_destino_id))
      .map((q) => ({ valor: q.id, rotulo: q.nome }));
  },

  render() {
    const f = WMSRemocao._form;
    const area = document.getElementById('remocao-editor');
    const lotes = WMSRemocao._lotes.map((l) => ({
      valor: l.id,
      rotulo: `${l.codigo} — ${l.depositante_nome} · ${l.armazem_nome} (${UI.numero(l.saldo_sacas, 0)} sc)`,
    }));
    const outroArmazem = f.lote && String(f.armazem_destino_id) !== String(f.lote.armazem_id);
    const quadras = f.lote ? WMSRemocao.quadrasDoDestino() : [];
    area.innerHTML = `
      <div class="linha-campos remocao-cab">
        ${UI.campo('Lote *', UI.select('lote_id', lotes, f.lote?.id || '', { vazio: 'Escolha o lote' }))}
        ${f.lote ? UI.campo('Armazém de destino', UI.select('armazem_destino_id',
          WMS._armazens.filter((a) => a.ativo || a.id === f.lote.armazem_id)
            .map((a) => ({ valor: a.id, rotulo: a.id === f.lote.armazem_id ? `${a.nome} (o mesmo)` : a.nome })),
          f.armazem_destino_id, { vazio: false }), 'outro armazém = vai o lote inteiro') : ''}
        ${f.lote ? UI.campo('Data', `<input type="date" name="data" value="${f.data || UI.hoje()}">`) : ''}
        ${f.lote ? UI.campo('Observação', `<input name="observacao" maxlength="300" value="${UI.escapar(f.observacao || '')}" placeholder="motivo, ex.: arrumação da quadra">`) : ''}
      </div>
      ${!f.lote ? '<div class="vazio">Escolha o lote para ver os locais dele.</div>' : `
        <div class="guia-conferencia" style="margin-top:12px">
          <span><b>${UI.escapar(f.lote.codigo)}</b> · ${UI.escapar(f.lote.depositante_nome)} · ${UI.escapar(f.lote.armazem_nome)}
            ${f.lote.peneira ? ` · peneira ${UI.escapar(f.lote.peneira)}` : ''}${f.lote.padrao ? ` · ${UI.escapar(f.lote.padrao)}` : ''}</span>
          <span id="remocao-total"></span>
        </div>
        ${outroArmazem ? `<div class="ok-caixa" style="margin-top:10px">Para outro armazém vai o <b>lote inteiro</b>:
          todas as linhas já estão com tudo o que resta — escolha só a quadra e a pilha de destino.</div>` : ''}
        ${!quadras.length ? '<div class="ok-caixa" style="margin-top:10px">O armazém de destino não tem quadras. Cadastre em Entrada &gt; Quadras.</div>' : ''}
        <h4 style="margin:16px 0 8px">Locais do lote — o que muda de lugar</h4>
        <div class="tabela-wrap"><table class="tabela-simples saida-tabela remocao-tabela">
          <thead><tr><th>Local hoje</th><th style="text-align:right">Tem</th><th style="text-align:right">Mover (sacas)</th>
            <th></th><th>Para quadra</th><th>Pilha</th><th style="text-align:right">Peso (kg)</th></tr></thead>
          <tbody>${f.posicoes.map((p) => {
            const l = f.linhas[p.posicao_id] || {};
            return `<tr data-pos="${p.posicao_id}">
              <td><b>${UI.escapar(p.quadra_nome)}</b>${p.pilha ? ` / ${UI.escapar(p.pilha)}` : ''}</td>
              <td class="direita">${UI.numero(p.sacas_disponiveis, 2)} sc<div class="mini">${UI.numero(p.peso_disponivel, 0)} kg</div></td>
              <td class="direita"><input name="sacas" inputmode="decimal" value="${l.sacas ? UI.numero(l.sacas, 2) : ''}" style="width:95px;text-align:right" ${outroArmazem ? 'readonly' : ''}></td>
              <td>${outroArmazem ? '' : `<button type="button" class="btn btn-mini" data-tudo="${p.posicao_id}">Tudo</button>`}</td>
              <td>${UI.select('quadra_destino_id', quadras, l.quadra_destino_id || '', { vazio: 'Quadra' })}</td>
              <td><input name="pilha_destino" maxlength="20" value="${UI.escapar(l.pilha_destino || '')}" style="width:80px;text-transform:uppercase"></td>
              <td class="direita"><input name="peso" inputmode="decimal" value="${l.peso ? UI.numero(l.peso, 2) : ''}" placeholder="proporcional" style="width:105px;text-align:right" ${outroArmazem ? 'readonly' : ''}></td>
            </tr>`;
          }).join('')}</tbody></table></div>
        ${quadras.length > 1 && f.posicoes.length > 1 ? `<div class="espaco" style="margin-top:8px">
          <span class="mini">Mandar tudo para a mesma quadra:</span>
          ${UI.select('quadra_todas', quadras, '', { vazio: 'escolha', attr: 'data-nao-suja' })}
        </div>` : ''}
        ${WMSRemocao.blocoHistorico(f.historico)}`}`;
    WMSRemocao.ligarEditor(area, outroArmazem);
    WMSRemocao.somar();
  },

  ler() {
    const f = WMSRemocao._form;
    const area = document.getElementById('remocao-editor');
    if (!f || !area || !f.lote) return f;
    f.data = area.querySelector('[name="data"]')?.value || UI.hoje();
    f.observacao = area.querySelector('[name="observacao"]')?.value || '';
    f.linhas = {};
    area.querySelectorAll('tr[data-pos]').forEach((tr) => {
      f.linhas[tr.dataset.pos] = {
        posicao_id: Number(tr.dataset.pos),
        sacas: WMS.numero(tr.querySelector('[name="sacas"]').value),
        peso: WMS.numero(tr.querySelector('[name="peso"]').value),
        quadra_destino_id: tr.querySelector('[name="quadra_destino_id"]').value,
        pilha_destino: tr.querySelector('[name="pilha_destino"]').value,
      };
    });
    return f;
  },

  somar() {
    const f = WMSRemocao.ler();
    const alvo = document.getElementById('remocao-total');
    if (!alvo || !f?.lote) return;
    const linhas = Object.values(f.linhas).filter((l) => l.sacas > 0);
    const sacas = linhas.reduce((s, l) => s + l.sacas, 0);
    alvo.innerHTML = sacas
      ? `· mudando <b>${UI.numero(sacas, 2)} sacas</b> de ${linhas.length} local(is)`
      : '· digite quantas sacas mudam de lugar em cada local';
    document.querySelectorAll('#remocao-editor tr[data-pos]').forEach((tr) => {
      const p = f.posicoes.find((x) => String(x.posicao_id) === tr.dataset.pos);
      const sc = WMS.numero(tr.querySelector('[name="sacas"]').value);
      tr.classList.toggle('saida-marcada', sc > 0);
      tr.classList.toggle('saida-passou', !!p && sc > Number(p.sacas_disponiveis) + 0.004);
    });
  },

  ligarEditor(area, outroArmazem) {
    area.oninput = () => WMSRemocao.somar();
    area.onfocusin = (e) => {
      if (e.target.matches('input[inputmode="decimal"]') && e.target.value) e.target.select();
    };
    const lote = area.querySelector('[name="lote_id"]');
    lote.onchange = () => WMSRemocao.escolherLote(lote.value ? Number(lote.value) : null);
    const destino = area.querySelector('[name="armazem_destino_id"]');
    if (destino) {
      destino.onchange = () => {
        const f = WMSRemocao.ler();
        f.armazem_destino_id = Number(destino.value);
        const outro = String(f.armazem_destino_id) !== String(f.lote.armazem_id);
        // outro armazém: vai tudo; e as quadras de antes não valem mais
        f.posicoes.forEach((p) => {
          const l = f.linhas[p.posicao_id] || {};
          f.linhas[p.posicao_id] = { ...l, quadra_destino_id: '',
            sacas: outro ? p.sacas_disponiveis : l.sacas, peso: outro ? p.peso_disponivel : l.peso };
        });
        UI._sujo = true;
        WMSRemocao.render();
      };
    }
    area.querySelectorAll('[data-tudo]').forEach((b) => {
      b.onclick = () => {
        const p = WMSRemocao._form.posicoes.find((x) => String(x.posicao_id) === b.dataset.tudo);
        const tr = b.closest('tr');
        tr.querySelector('[name="sacas"]').value = UI.numero(p.sacas_disponiveis, 2);
        tr.querySelector('[name="peso"]').value = p.peso_disponivel ? UI.numero(p.peso_disponivel, 2) : '';
        UI._sujo = true;
        WMSRemocao.somar();
      };
    });
    const todas = area.querySelector('[name="quadra_todas"]');
    if (todas) {
      todas.onchange = () => {
        area.querySelectorAll('tr[data-pos] [name="quadra_destino_id"]').forEach((s) => { s.value = todas.value; });
        UI._sujo = true;
      };
    }
    if (outroArmazem) WMSRemocao.somar();
  },

  async confirmar() {
    const f = WMSRemocao.ler();
    if (!f?.lote) return UI.erro('Escolha o lote.');
    const itens = Object.values(f.linhas).filter((l) => l.sacas > 0).map((l) => ({
      posicao_id: l.posicao_id, sacas: l.sacas, peso: l.peso || 0,
      quadra_destino_id: l.quadra_destino_id ? Number(l.quadra_destino_id) : null,
      pilha_destino: l.pilha_destino,
    }));
    if (!itens.length) return UI.erro('Digite quantas sacas mudam de lugar e para onde.');
    try {
      const r = await Api.post('/api/wms/remocoes', {
        empresa_id: Estado.empresaId, lote_id: f.lote.id, data: f.data,
        armazem_destino_id: Number(f.armazem_destino_id) || null,
        observacao: f.observacao, itens,
      });
      UI.modalSalvo();
      UI.fecharModal();
      UI.sucesso(`Remoção nº ${r.numero} feita: ${UI.numero(r.sacas, 2)} sacas do lote ${r.lote_codigo} mudaram de lugar.`);
      if (WMS._tipo === 'REMOCAO' && location.hash === '#/wms-remocoes') await WMSRemocao.carregar();
      else if (location.hash === '#/wms-lotes') await WMSLotes.carregar();
    } catch (e) {
      UI.erro(e.message);
    }
  },

  /* ---------------------------------------------------- histórico do lote */
  ICONES: { ENTRADA: '↘', TRANSFERENCIA_RECEBIDA: '⇄', TRANSFERENCIA_ENVIADA: '⇄', SAIDA: '↗', REMOCAO: '⇆',
    DESPEJO: '⚙', RESULTADO: '⚙' },

  blocoHistorico(h) {
    if (!h) return '';
    return `<h4 style="margin:18px 0 8px">Histórico do lote</h4>
      <div class="historico-lote">${h.eventos.map((e) => `
        <div class="historico-evento ${e.situacao === 'ESTORNADA' ? 'estornado' : ''}">
          <span class="historico-icone sinal-${e.sinal === '+' ? 'mais' : e.sinal === '-' ? 'menos' : 'igual'}">${WMSRemocao.ICONES[e.tipo] || '•'}</span>
          <div class="historico-texto">
            <div><b>${UI.escapar(e.titulo)}</b>${e.situacao === 'ESTORNADA' ? ' <span class="tag tag-cancelado">Estornada</span>' : ''}</div>
            <div class="mini">${UI.data(e.data)}${e.detalhe ? ` · ${UI.escapar(e.detalhe)}` : ''}</div>
          </div>
          <span class="historico-sacas sinal-${e.sinal === '+' ? 'mais' : e.sinal === '-' ? 'menos' : 'igual'}">${
            e.sinal === '=' ? '' : e.sinal}${UI.numero(e.sacas, 2)} sc</span>
        </div>`).join('') || '<div class="vazio">Nada ainda.</div>'}</div>`;
  },

  async historico(loteId) {
    let h;
    try { h = await Api.get(`/api/wms/lotes/${loteId}/historico`); } catch (e) { return UI.erro(e.message); }
    UI.abrirModal({
      titulo: `Histórico do lote ${h.lote.codigo}`,
      largo: true,
      corpo: `<div class="guia-conferencia">
          <span><b>${UI.escapar(h.lote.codigo)}</b> · ${UI.escapar(h.lote.depositante_nome)} · ${UI.escapar(h.lote.armazem_nome)}
          ${h.lote.peneira ? ` · peneira ${UI.escapar(h.lote.peneira)}` : ''}${h.lote.padrao ? ` · ${UI.escapar(h.lote.padrao)}` : ''}</span>
        </div>
        <div style="margin-top:10px"><span class="mini forte">Onde está hoje: </span>${h.locais_hoje.length
          ? h.locais_hoje.map((l) => `<span class="lote-posicao">${UI.escapar(l.lugar)} <b>${UI.numero(l.sacas, 0)}</b></span>`).join(' ')
          : '<span class="mini">nada — o lote já saiu todo</span>'}</div>
        ${WMSRemocao.blocoHistorico(h)}`,
      botoes: [
        { rotulo: 'Mudar de local', acao: () => { UI.fecharModal(); WMSRemocao.nova(h.lote.id); } },
        { rotulo: 'Fechar', classe: 'btn-primario', acao: () => UI.fecharModal() },
      ],
    });
  },
};
