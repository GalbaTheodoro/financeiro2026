/* WMS — Lotes: o café que está no armazém, lote por lote.

   Cada lote mostra o dono, a peneira e o padrão da entrada, onde está
   (quadra e pilha, com o que resta em cada uma), o saldo de hoje e a amostra.

   "Histórico" mostra tudo o que aconteceu com o lote; "Mudar local" abre a
   remoção já com o lote escolhido.

   O botão "Classificar" abre a amostra do lote na tela de Amostras — e cria a
   amostra na primeira vez, já preenchida com o dono, o lote, as sacas e o
   armazém. Cada lote tem a sua amostra; depois o botão vira "Amostra nº". */
const WMSLotes = {
  _lotes: [],
  _filtros: { armazem_id: '', depositante_id: '', busca: '', com_saldo: true },

  async tela() {
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';
    try {
      await WMSLotes.carregar();
    } catch (e) {
      alvo.innerHTML = `<div class="cartao"><div class="vazio">${UI.escapar(e.message)}</div></div>`;
    }
  },

  async carregar() {
    const eid = Estado.empresaId;
    const [armazens, lotes] = await Promise.all([
      Api.get('/api/wms/armazens', { empresa_id: eid }),
      Api.get('/api/wms/lotes', { empresa_id: eid, ...WMSLotes._filtros }),
    ]);
    WMS._armazens = armazens;
    WMSLotes._lotes = lotes;
    WMSLotes.desenhar();
  },

  desenhar() {
    const lotes = WMSLotes._lotes;
    const f = WMSLotes._filtros;
    const sacas = lotes.reduce((s, l) => s + Number(l.saldo_sacas || 0), 0);
    const peso = lotes.reduce((s, l) => s + Number(l.saldo_peso || 0), 0);
    const classificados = lotes.filter((l) => l.amostra && l.amostra.situacao === 'CLASSIFICADA').length;
    const semAmostra = lotes.filter((l) => !l.amostra).length;

    document.getElementById('pagina').innerHTML = `
      <div class="grade g4" style="margin-bottom:12px">
        ${WMS.cartao('Lotes', String(lotes.length), f.com_saldo ? 'com saldo no filtro' : 'no filtro', 'azul')}
        ${WMS.cartao('Sacas', UI.numero(sacas, 2), 'saldo de hoje', 'verde')}
        ${WMS.cartao('Peso', `${UI.numero(peso, 0)} kg`, 'saldo de hoje', '')}
        ${WMS.cartao('Classificados', `${classificados} de ${lotes.length}`,
          semAmostra ? `${semAmostra} sem amostra ainda` : 'todos com amostra', semAmostra ? 'ambar' : '')}
      </div>
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Lotes do armazém</h3>
            <div class="mini">onde está cada lote, quanto sobra e a classificação — "Classificar" abre a amostra do lote</div></div>
          <div class="espaco">
            <button class="btn" id="wms-saldo">Saldo do armazém</button>
            <button class="btn" id="wms-exportar">Exportar</button>
          </div>
        </div>
        <div class="cartao-corpo">
          <div class="linha-campos" data-nao-suja>
            ${UI.campo('Armazém', UI.select('armazem_id',
              WMS._armazens.map((a) => ({ valor: a.id, rotulo: a.nome })), f.armazem_id, { vazio: 'Todos' }))}
            ${UI.campo('Cliente', UI.select('depositante_id',
              WMS.depositantes().map((p) => ({ valor: p.id, rotulo: p.nome })), f.depositante_id, { vazio: 'Todos' }))}
            ${UI.campo('Procurar', `<input name="busca" value="${UI.escapar(f.busca)}" placeholder="lote, peneira, padrão">`)}
            <label class="campo">Mostrar
              <span class="espaco" style="margin-top:6px">
                <input type="checkbox" name="com_saldo" ${f.com_saldo ? 'checked' : ''}>
                <span class="mini">só lotes com saldo</span>
              </span>
            </label>
          </div>
          <div id="lista-wms" style="margin-top:12px">${UI.tabela({
            vazio: 'Nenhum lote neste filtro. Os lotes nascem ao fechar a guia de entrada (ou a transferência).',
            colunas: [
              { titulo: 'Lote', chave: 'lote', valor: (l) => `<b>${UI.escapar(l.codigo)}</b>
                <div class="mini">${l.lote_origem_codigo ? `transferido do ${UI.escapar(l.lote_origem_codigo)}`
                  : l.servico_numero ? `resultado do serviço ${l.servico_numero}`
                  : l.guia_numero ? `guia de entrada ${l.guia_numero}` : ''} · ${UI.data(l.data_entrada)}</div>` },
              { titulo: 'Cliente', valor: (l) => `${UI.escapar(l.depositante_nome)}
                <div class="mini">${UI.escapar(l.armazem_nome)}</div>` },
              { titulo: 'Peneira / padrão', valor: (l) => `${UI.escapar(l.peneira || '—')}
                <div class="mini">${UI.escapar(l.padrao || '')}</div>` },
              { titulo: 'Onde está', valor: (l) => WMSLotes.posicoes(l) },
              { titulo: 'Saldo', classe: 'direita', chave: 'saldo', valor: (l) => `<b>${UI.numero(l.saldo_sacas, 2)} sc</b>
                <div class="mini">${UI.numero(l.saldo_peso, 0)} kg · entrou ${UI.numero(l.sacas, 0)}</div>
                ${Number(l.saldo_outros_armazens) ? `<div class="mini">+ ${UI.numero(l.saldo_outros_armazens, 2)} sc em outro armazém</div>` : ''}` },
              { titulo: 'Amostra', valor: (l) => WMSLotes.resumoAmostra(l.amostra) },
              { titulo: '', classe: 'direita', valor: (l, i) => `
                <button class="btn btn-mini" data-historico="${i}">Histórico</button>
                ${Number(l.saldo_sacas) > 0.004 ? `<button class="btn btn-mini" data-mudar="${i}">Mudar local</button>` : ''}
                <button class="btn btn-mini ${l.amostra ? '' : 'btn-primario'}" data-classificar="${i}">${
                  l.amostra ? `Amostra nº ${String(l.amostra.numero).padStart(5, '0')}` : 'Classificar'}</button>` },
            ],
            linhas: lotes,
            rodape: lotes.length ? {
              lote: `<b>${lotes.length} lote(s)</b>`,
              saldo: `<b>${UI.numero(sacas, 2)} sc</b>`,
            } : null,
          })}</div>
        </div>
      </div>`;
    WMSLotes.ligar();
  },

  posicoes(l) {
    const com = (l.posicoes || []).filter((p) => Number(p.sacas_disponiveis) > 0.004);
    if (!com.length) return '<span class="mini">—</span>';
    return com.map((p) => `<span class="lote-posicao">${UI.escapar(p.quadra_nome)}${
      p.pilha ? `/${UI.escapar(p.pilha)}` : ''} <b>${UI.numero(p.sacas_disponiveis, 0)}</b></span>`).join(' ');
  },

  resumoAmostra(a) {
    if (!a) return '<span class="mini">sem amostra</span>';
    if (a.situacao !== 'CLASSIFICADA') {
      return `<span class="tag tag-parcial">A classificar</span>`;
    }
    const partes = [a.tipo ? `tipo ${a.tipo}` : '', a.bebida || '',
      a.pontuacao ? `${UI.numero(a.pontuacao, 2)} pts` : ''].filter(Boolean);
    return `<span class="tag tag-pago">Classificada</span>
      <div class="mini">${UI.escapar(partes.join(' · '))}</div>
      ${a.padrao ? `<div class="mini">${UI.escapar(a.padrao)}</div>` : ''}`;
  },

  ligar() {
    const pagina = document.getElementById('pagina');
    pagina.querySelector('#wms-saldo').onclick = () => WMS.saldo();
    pagina.querySelector('#wms-exportar').onclick = () => UI.exportarTabela('wms-lotes', '#lista-wms table');
    ['armazem_id', 'depositante_id'].forEach((nome) => {
      const campo = pagina.querySelector(`[name="${nome}"]`);
      campo.onchange = () => { WMSLotes._filtros[nome] = campo.value; WMSLotes.carregar(); };
    });
    const saldo = pagina.querySelector('[name="com_saldo"]');
    saldo.onchange = () => { WMSLotes._filtros.com_saldo = saldo.checked; WMSLotes.carregar(); };
    const busca = pagina.querySelector('[name="busca"]');
    let tempo = null;
    busca.oninput = () => {
      clearTimeout(tempo);
      tempo = setTimeout(() => { WMSLotes._filtros.busca = busca.value; WMSLotes.carregar(); }, 400);
    };
    pagina.querySelectorAll('[data-historico]').forEach((b) => {
      b.onclick = () => WMSRemocao.historico(WMSLotes._lotes[Number(b.dataset.historico)].id);
    });
    pagina.querySelectorAll('[data-mudar]').forEach((b) => {
      b.onclick = () => WMSRemocao.nova(WMSLotes._lotes[Number(b.dataset.mudar)].id);
    });
    pagina.querySelectorAll('[data-classificar]').forEach((b) => {
      b.onclick = () => WMSLotes.classificar(WMSLotes._lotes[Number(b.dataset.classificar)]);
    });
  },

  /* Abre (ou cria) a amostra do lote e vai direto para a ficha dela. */
  async classificar(lote) {
    try {
      const r = await Api.post(`/api/wms/lotes/${lote.id}/amostra`);
      if (r.nova) UI.sucesso(`Amostra nº ${String(r.numero).padStart(5, '0')} criada para o lote ${lote.codigo}.`);
      Amostras._abrirDepois = r.amostra_id;
      Amostras._aba = 'amostras';
      if (location.hash === '#/amostras') App.navegar();
      else App.irPara('/amostras');
    } catch (e) {
      UI.erro(e.message);
    }
  },
};
