/* WMS / Armazém: o café que a empresa guarda para os depositantes.

   Cinco telas no menu, uma para cada tipo de lançamento — Entrada, Saídas,
   Serviços, Transferências e Remoção — e todas com o mesmo esqueleto:
   cartões de resumo, filtros, a lista e o botão de lançar. O saldo não é
   digitado em lugar nenhum: é a soma dos lançamentos, e o botão "Saldo do
   armazém" mostra como ele está agora.

   Entrada, Saída e Transferência têm telas próprias — as guias, com lotes e
   posições — em wms_entrada.js, wms_saida.js e wms_transferencia.js; este
   arquivo cuida de Serviços e Remoção (e do saldo e dos armazéns).

   O café do armazém é do depositante, não da empresa — por isso este controle
   é separado do Estoque (que tem custo médio e é mercadoria própria). */
const WMS = {
  _tipo: 'ENTRADA',
  _dados: null,
  _armazens: [],
  _filtros: { de: '', ate: '', armazem_id: '', depositante_id: '', busca: '', mostrar_cancelados: false },

  TIPOS: {
    ENTRADA: {
      rota: '/wms-entradas', titulo: 'Entradas', novo: 'Nova guia de entrada', icone: '↘',
      explica: 'feita pela guia de entrada (wms_entrada.js): lotes, locais e o saldo ao fechar',
      vazio: 'Nenhuma entrada neste filtro.',
    },
    SAIDA: {
      rota: '/wms-saidas', titulo: 'Saídas', novo: 'Nova saída', icone: '↗',
      explica: 'café retirado ou expedido — sai do saldo e não pode passar do que o depositante tem',
      vazio: 'Nenhuma saída neste filtro.',
    },
    SERVICO: {
      rota: '/wms-servicos', titulo: 'Serviços', novo: 'Novo serviço', icone: '⚙',
      explica: 'rebenefício, padronização, ensaque, armazenagem... — registra o serviço e o valor, sem mexer no saldo',
      vazio: 'Nenhum serviço neste filtro.',
    },
    TRANSFERENCIA: {
      rota: '/wms-transferencias', titulo: 'Transferências', novo: 'Nova transferência', icone: '⇄',
      explica: 'troca de dono dentro do armazém — sai de um depositante e entra no outro',
      vazio: 'Nenhuma transferência neste filtro.',
    },
    REMOCAO: {
      rota: '/wms-remocoes', titulo: 'Remoção', novo: 'Nova remoção', icone: '⇆',
      explica: 'o mesmo café muda de armazém — sai do armazém de origem e entra no de destino',
      vazio: 'Nenhuma remoção neste filtro.',
    },
  },

  /* ------------------------------------------------------------- abertura */
  async tela(tipo) {
    if (tipo && tipo !== WMS._tipo) {
      WMS._tipo = tipo;
      WMS._filtros.busca = '';
    }
    if (WMS._tipo === 'ENTRADA') return WMSEntrada.tela();
    if (WMS._tipo === 'SAIDA') return WMSSaida.tela();
    if (WMS._tipo === 'TRANSFERENCIA') return WMSTransf.tela();
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';
    try {
      await WMS.carregar();
    } catch (e) {
      alvo.innerHTML = `<div class="cartao"><div class="vazio">${UI.escapar(e.message)}</div></div>`;
    }
  },

  async carregar() {
    // a Entrada é a guia de entrada (lotes e locais) — tela própria
    if (WMS._tipo === 'ENTRADA') return WMSEntrada.carregar();
    if (WMS._tipo === 'SAIDA') return WMSSaida.carregar();
    if (WMS._tipo === 'TRANSFERENCIA') return WMSTransf.carregar();
    const [armazens, dados] = await Promise.all([
      Api.get('/api/wms/armazens', { empresa_id: Estado.empresaId }),
      Api.get('/api/wms/movimentos', {
        empresa_id: Estado.empresaId, tipo: WMS._tipo, ...WMS._filtros,
      }),
    ]);
    WMS._armazens = armazens;
    WMS._dados = dados;
    WMS.desenhar();
  },

  armazensAtivos() {
    return WMS._armazens.filter((a) => a.ativo);
  },
  depositantes() {
    return Api.parceirosPorTipo(null);
  },

  /* ------------------------------------------------------------------ tela */
  desenhar() {
    const cfg = WMS.TIPOS[WMS._tipo];
    const d = WMS._dados || { movimentos: [], resumo: {} };
    const r = d.resumo || {};
    const semArmazem = !WMS._armazens.length;
    document.getElementById('pagina').innerHTML = `
      <div class="grade g4" style="margin-bottom:12px">
        ${WMS.cartao('Lançamentos', String(r.lancamentos || 0), 'no filtro abaixo', 'azul')}
        ${WMS.cartao('Sacas', UI.numero(r.sacas, 2), WMS._tipo === 'SERVICO' ? 'sacas atendidas' : 'movimentadas', 'verde')}
        ${WMS.cartao('Peso', `${UI.numero(r.peso_kg, 0)} kg`, 'somado dos lançamentos', '')}
        ${WMS._tipo === 'SERVICO'
          ? WMS.cartao('Valor dos serviços', UI.moeda(r.valor), 'cobrado dos depositantes', 'ambar')
          : WMS.cartao('Armazéns', String(WMS.armazensAtivos().length), 'ativos', '')}
      </div>

      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>${UI.escapar(cfg.titulo)}</h3>
            <div class="mini">${UI.escapar(cfg.explica)}</div></div>
          <div class="espaco">
            <button class="btn" id="wms-armazens">Armazéns</button>
            <button class="btn" id="wms-saldo">Saldo do armazém</button>
            <button class="btn" id="wms-exportar">Exportar</button>
            <button class="btn btn-primario" id="wms-novo">${UI.escapar(cfg.novo)}</button>
          </div>
        </div>
        <div class="cartao-corpo">
          ${semArmazem ? `<div class="ok-caixa" style="margin-bottom:12px">
            Comece cadastrando o armazém (botão <b>Armazéns</b>). Os depositantes são os
            clientes e fornecedores de <b>Cadastros &gt; Parceiros</b>.</div>` : ''}
          <div class="linha-campos" data-nao-suja>
            ${UI.campo('De', `<input type="date" name="de" value="${WMS._filtros.de}">`)}
            ${UI.campo('Até', `<input type="date" name="ate" value="${WMS._filtros.ate}">`)}
            ${UI.campo('Armazém', UI.select('armazem_id',
              WMS._armazens.map((a) => ({ valor: a.id, rotulo: a.nome })),
              WMS._filtros.armazem_id, { vazio: 'Todos' }))}
            ${UI.campo('Depositante', UI.select('depositante_id',
              WMS.depositantes().map((p) => ({ valor: p.id, rotulo: p.nome })),
              WMS._filtros.depositante_id, { vazio: 'Todos' }))}
            ${UI.campo('Procurar', `<input name="busca" value="${UI.escapar(WMS._filtros.busca)}"
              placeholder="lote, documento, placa${WMS._tipo === 'SERVICO' ? ', serviço' : ''}">`)}
            <label class="campo">Mostrar
              <span class="espaco" style="margin-top:6px">
                <input type="checkbox" name="mostrar_cancelados" ${WMS._filtros.mostrar_cancelados ? 'checked' : ''}>
                <span class="mini">os cancelados também</span>
              </span>
            </label>
          </div>
          <div id="lista-wms" style="margin-top:12px">${WMS.tabela(d, cfg)}</div>
          ${d.movimentos.length >= 500
            ? '<div class="mini" style="margin-top:8px">Mostrando os 500 lançamentos mais recentes — aperte o filtro para ver mais atrás.</div>'
            : ''}
        </div>
      </div>`;
    WMS.ligar();
  },

  cartao(titulo, valor, dica, cor = '') {
    return `<div class="kpi ${cor ? `destaque-${cor}` : ''}">
      <div class="kpi-rotulo">${UI.escapar(titulo)}</div>
      <div class="kpi-valor" ${cor ? `style="color:var(--${cor})"` : ''}>${valor}</div>
      <div class="kpi-nota">${UI.escapar(dica)}</div></div>`;
  },

  /* As colunas mudam com o tipo: a transferência mostra os dois donos, a
     remoção os dois armazéns, o serviço o nome e o valor. */
  tabela(d, cfg) {
    const t = WMS._tipo;
    const cancelado = (m) => m.status === 'CANCELADO';
    const colunas = [
      { titulo: 'Nº', chave: 'numero', valor: (m) => `<b>${m.numero}</b>` },
      { titulo: 'Data', valor: (m) => UI.data(m.data) },
    ];
    if (t === 'REMOCAO') {
      colunas.push({ titulo: 'Armazém', valor: (m) => `${UI.escapar(m.armazem_nome)}
        <div class="mini">→ ${UI.escapar(m.armazem_destino_nome || '-')}</div>` });
    } else {
      colunas.push({ titulo: 'Armazém', valor: (m) => UI.escapar(m.armazem_nome) });
    }
    if (t === 'TRANSFERENCIA') {
      colunas.push({ titulo: 'De → Para', valor: (m) => `${UI.escapar(m.depositante_nome)}
        <div class="mini">→ ${UI.escapar(m.depositante_destino_nome || '-')}</div>` });
    } else {
      colunas.push({ titulo: 'Depositante', valor: (m) => UI.escapar(m.depositante_nome) });
    }
    if (t === 'SERVICO') {
      colunas.push({ titulo: 'Serviço', valor: (m) => `<b>${UI.escapar(m.servico || '')}</b>` });
    }
    colunas.push(
      { titulo: 'Produto / lote', valor: (m) => `${UI.escapar(m.produto_nome || '—')}
        ${m.lote ? `<div class="mini">lote ${UI.escapar(m.lote)}</div>` : ''}` },
      { titulo: 'Sacas', classe: 'direita', chave: 'sacas', valor: (m) => `<b>${UI.numero(m.sacas, 2)}</b>` },
      { titulo: 'Peso (kg)', classe: 'direita', chave: 'peso', valor: (m) => UI.numero(m.peso_kg, 0) },
    );
    if (t === 'SERVICO') {
      colunas.push({ titulo: 'Valor', classe: 'direita', chave: 'valor', valor: (m) => UI.moeda(m.valor) });
    } else {
      colunas.push({ titulo: 'Documento', valor: (m) => `${UI.escapar(m.documento || '')}
        ${m.placa ? `<div class="mini">placa ${UI.escapar(m.placa)}</div>` : ''}` });
    }
    colunas.push({ titulo: '', classe: 'direita', valor: (m, i) => (cancelado(m)
      ? `<span class="tag tag-cancelado" title="${UI.escapar(m.observacao || '')}">Cancelado</span>`
      : `<button class="btn btn-mini" data-ver="${i}">Ver</button>
         <button class="btn btn-mini" data-cancelar="${i}">Cancelar</button>`) });

    const r = d.resumo || {};
    return UI.tabela({
      vazio: cfg.vazio,
      colunas,
      linhas: d.movimentos,
      rodape: d.movimentos.length ? {
        numero: `<b>${r.lancamentos}</b>`,
        sacas: `<b>${UI.numero(r.sacas, 2)}</b>`,
        peso: `<b>${UI.numero(r.peso_kg, 0)}</b>`,
        valor: `<b>${UI.moeda(r.valor)}</b>`,
      } : null,
    });
  },

  ligar() {
    const pagina = document.getElementById('pagina');
    pagina.querySelector('#wms-novo').onclick = () => WMS.formulario();
    pagina.querySelector('#wms-armazens').onclick = () => WMS.listaArmazens();
    pagina.querySelector('#wms-saldo').onclick = () => WMS.saldo();
    pagina.querySelector('#wms-exportar').onclick = () =>
      UI.exportarTabela(`wms-${WMS._tipo.toLowerCase()}`, '#lista-wms table');

    ['de', 'ate', 'armazem_id', 'depositante_id'].forEach((nome) => {
      const campo = pagina.querySelector(`[name="${nome}"]`);
      campo.onchange = () => { WMS._filtros[nome] = campo.value; WMS.carregar(); };
    });
    const cancelados = pagina.querySelector('[name="mostrar_cancelados"]');
    cancelados.onchange = () => { WMS._filtros.mostrar_cancelados = cancelados.checked; WMS.carregar(); };
    const busca = pagina.querySelector('[name="busca"]');
    let tempo = null;
    busca.oninput = () => {
      clearTimeout(tempo);
      tempo = setTimeout(() => { WMS._filtros.busca = busca.value; WMS.carregar(); }, 400);
    };
    pagina.querySelectorAll('[data-ver]').forEach((b) => {
      b.onclick = () => WMS.ver(WMS._dados.movimentos[Number(b.dataset.ver)]);
    });
    pagina.querySelectorAll('[data-cancelar]').forEach((b) => {
      b.onclick = () => WMS.cancelar(WMS._dados.movimentos[Number(b.dataset.cancelar)]);
    });
  },

  /* ------------------------------------------------------------ lançamento */
  formulario() {
    const t = WMS._tipo;
    const cfg = WMS.TIPOS[t];
    const armazens = WMS.armazensAtivos();
    if (!armazens.length) {
      UI.erro('Cadastre primeiro o armazém (botão Armazéns).');
      return WMS.formularioArmazem(null);
    }
    if (t === 'REMOCAO' && armazens.length < 2) {
      UI.erro('A remoção precisa de dois armazéns: cadastre o de destino.');
      return WMS.formularioArmazem(null);
    }
    const deps = WMS.depositantes().map((p) => ({ valor: p.id, rotulo: p.nome }));
    if (!deps.length) return UI.erro('Cadastre o depositante em Cadastros > Parceiros.');
    const opArm = armazens.map((a) => ({ valor: a.id, rotulo: a.nome }));
    const opProd = Api.produtosAtivos().map((p) => ({ valor: p.id, rotulo: `${p.codigo} — ${p.nome}` }));
    const unico = armazens.length === 1 ? armazens[0].id : '';
    const tiraDoSaldo = ['SAIDA', 'TRANSFERENCIA', 'REMOCAO'].includes(t);

    const corpo = UI.abrirModal({
      titulo: cfg.novo,
      largo: true,
      corpo: `
        <div class="linha-campos">
          ${UI.campo('Data', `<input type="date" name="data" value="${UI.hoje()}">`)}
          ${UI.campo(t === 'REMOCAO' ? 'Armazém de origem *' : 'Armazém *',
            UI.select('armazem_id', opArm, t === 'REMOCAO' ? '' : unico, { vazio: 'Escolha', obrigatorio: true }))}
          ${t === 'REMOCAO' ? UI.campo('Armazém de destino *',
            UI.select('armazem_destino_id', opArm, '', { vazio: 'Escolha', obrigatorio: true })) : ''}
          ${UI.campo(t === 'TRANSFERENCIA' ? 'Depositante de origem *' : 'Depositante *',
            UI.select('depositante_id', deps, '', { vazio: 'Escolha', obrigatorio: true }))}
          ${t === 'TRANSFERENCIA' ? UI.campo('Depositante de destino *',
            UI.select('depositante_destino_id', deps, '', { vazio: 'Escolha', obrigatorio: true })) : ''}
          ${UI.campo('Produto', UI.select('produto_id', opProd, '', { vazio: '—' }),
            'café arábica, conilon, bica corrida...')}
          ${UI.campo('Lote', '<input name="lote" placeholder="ex.: L-2026-015" maxlength="40">')}
          ${t === 'SERVICO' ? UI.campo('Serviço *', `<input name="servico" list="wms-lista-servicos" maxlength="80"
              placeholder="ex.: rebenefício">
              <datalist id="wms-lista-servicos">${(WMS._dados.servicos || [])
                .map((s) => `<option value="${UI.escapar(s)}">`).join('')}</datalist>`) : ''}
          ${UI.campo(t === 'SERVICO' ? 'Sacas atendidas' : 'Sacas *', '<input name="sacas" inputmode="decimal">')}
          ${UI.campo('Peso (kg)', '<input name="peso_kg" inputmode="decimal">', 'líquido, da balança')}
          ${t === 'SERVICO' ? UI.campo('Valor cobrado (R$)', '<input name="valor" inputmode="decimal">') : ''}
          ${t !== 'SERVICO' ? UI.campo('Documento', '<input name="documento" maxlength="40" placeholder="nota, romaneio, ticket">') : ''}
          ${['ENTRADA', 'SAIDA', 'REMOCAO'].includes(t) ? `
            ${UI.campo('Placa', '<input name="placa" maxlength="10" style="text-transform:uppercase">')}
            ${UI.campo('Motorista', '<input name="motorista" maxlength="120">')}` : ''}
          ${UI.campo('Observação', '<input name="observacao" maxlength="300">')}
        </div>
        ${tiraDoSaldo ? '<div id="wms-disponivel" class="mini" style="margin-top:10px"></div>' : ''}`,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        { rotulo: 'Lançar', classe: 'btn-primario', acao: () => WMS.salvar() },
      ],
      aoSalvar: () => WMS.salvar(),
    });

    // mostra quanto o depositante tem antes de tirar — evita a recusa do servidor
    if (tiraDoSaldo) {
      const mostrar = async () => {
        const f = UI.lerFormulario(corpo);
        const alvo = corpo.querySelector('#wms-disponivel');
        if (!f.armazem_id || !f.depositante_id) { alvo.innerHTML = ''; return; }
        try {
          const r = await Api.get('/api/wms/saldos', {
            empresa_id: Estado.empresaId, armazem_id: f.armazem_id, depositante_id: f.depositante_id,
          });
          if (!r.saldos.length) {
            alvo.innerHTML = '<span class="negativo">Este depositante não tem café neste armazém.</span>';
            return;
          }
          alvo.innerHTML = `Saldo deste depositante neste armazém (clique para usar):
            ${r.saldos.map((s, i) => `<button type="button" class="btn btn-mini" data-usar-saldo="${i}">
              <b>${UI.numero(s.sacas, 2)} sc</b> ${UI.escapar(s.produto_nome || '')}${
              s.lote ? ` lote ${UI.escapar(s.lote)}` : ' sem lote'}</button>`).join(' ')}`;
          // um clique preenche produto, lote e a quantidade inteira do lote
          alvo.querySelectorAll('[data-usar-saldo]').forEach((b) => {
            b.onclick = () => {
              const s = r.saldos[Number(b.dataset.usarSaldo)];
              corpo.querySelector('[name="produto_id"]').value = s.produto_id || '';
              corpo.querySelector('[name="lote"]').value = s.lote || '';
              corpo.querySelector('[name="sacas"]').value = UI.numero(s.sacas, 2);
              corpo.querySelector('[name="peso_kg"]').value = s.peso_kg ? UI.numero(s.peso_kg, 2) : '';
              UI._sujo = true;
            };
          });
        } catch { alvo.innerHTML = ''; }
      };
      ['armazem_id', 'depositante_id'].forEach((n) => {
        corpo.querySelector(`[name="${n}"]`).addEventListener('change', mostrar);
      });
      mostrar();
    }
  },

  numero(texto) {
    // "1.234,50" (do jeito brasileiro) ou "60.5" (com ponto) — os dois valem
    let limpo = String(texto || '').trim();
    if (limpo.includes(',')) limpo = limpo.replace(/\./g, '').replace(',', '.');
    return Number(limpo || 0) || 0;
  },

  async salvar() {
    const corpo = document.getElementById('modal-corpo');
    const f = UI.lerFormulario(corpo);
    const inteiro = (v) => (v ? Number(v) : null);
    try {
      const r = await Api.post('/api/wms/movimentos', {
        empresa_id: Estado.empresaId,
        tipo: WMS._tipo,
        data: f.data,
        armazem_id: inteiro(f.armazem_id),
        armazem_destino_id: inteiro(f.armazem_destino_id),
        depositante_id: inteiro(f.depositante_id),
        depositante_destino_id: inteiro(f.depositante_destino_id),
        produto_id: inteiro(f.produto_id),
        lote: f.lote,
        sacas: WMS.numero(f.sacas),
        peso_kg: WMS.numero(f.peso_kg),
        valor: WMS.numero(f.valor),
        documento: f.documento,
        placa: f.placa ? String(f.placa).toUpperCase() : '',
        motorista: f.motorista,
        servico: f.servico,
        observacao: f.observacao,
      });
      UI.modalSalvo();
      UI.fecharModal();
      UI.sucesso(`${r.tipo_nome} nº ${r.numero} lançada.`);
      await WMS.carregar();
    } catch (e) {
      UI.erro(e.message);
    }
  },

  ver(m) {
    const linha = (rotulo, valor) => (valor ? `<tr><td class="mini">${rotulo}</td><td>${valor}</td></tr>` : '');
    UI.abrirModal({
      titulo: `${m.tipo_nome} nº ${m.numero}`,
      corpo: `<table class="tabela-simples" style="width:100%">
        ${linha('Data', UI.data(m.data))}
        ${linha(m.armazem_destino_nome ? 'Armazém de origem' : 'Armazém', UI.escapar(m.armazem_nome))}
        ${linha('Armazém de destino', UI.escapar(m.armazem_destino_nome || ''))}
        ${linha(m.depositante_destino_nome ? 'Depositante de origem' : 'Depositante', UI.escapar(m.depositante_nome))}
        ${linha('Depositante de destino', UI.escapar(m.depositante_destino_nome || ''))}
        ${linha('Serviço', UI.escapar(m.servico || ''))}
        ${linha('Produto', UI.escapar(m.produto_nome || ''))}
        ${linha('Lote', UI.escapar(m.lote || ''))}
        ${linha('Sacas', UI.numero(m.sacas, 2))}
        ${linha('Peso', m.peso_kg ? `${UI.numero(m.peso_kg, 0)} kg` : '')}
        ${linha('Valor', m.valor ? UI.moeda(m.valor) : '')}
        ${linha('Documento', UI.escapar(m.documento || ''))}
        ${linha('Placa', UI.escapar(m.placa || ''))}
        ${linha('Motorista', UI.escapar(m.motorista || ''))}
        ${linha('Observação', UI.escapar(m.observacao || ''))}
        ${linha('Situação', m.status === 'CANCELADO' ? 'Cancelado' : 'Ativo')}
      </table>`,
      botoes: [{ rotulo: 'Fechar', acao: () => UI.fecharModal() }],
    });
  },

  cancelar(m) {
    const corpo = UI.abrirModal({
      titulo: `Cancelar ${m.tipo_nome.toLowerCase()} nº ${m.numero}`,
      corpo: `<p style="margin-top:0">${m.tipo === 'SERVICO'
        ? 'O serviço deixa de contar no total.'
        : 'O saldo do armazém volta a ficar como estava antes deste lançamento.'}</p>
        ${UI.campo('Motivo *', '<input name="motivo" maxlength="200" placeholder="ex.: lançado em dobro">')}`,
      botoes: [
        { rotulo: 'Voltar', acao: () => UI.fecharModal() },
        { rotulo: 'Cancelar lançamento', classe: 'btn-perigo', acao: async () => {
          const motivo = corpo.querySelector('[name="motivo"]').value;
          try {
            await Api.post(`/api/wms/movimentos/${m.id}/cancelar`, { motivo });
            UI.modalSalvo();
            UI.fecharModal();
            UI.sucesso('Lançamento cancelado.');
            await WMS.carregar();
          } catch (e) { UI.erro(e.message); }
        } },
      ],
    });
  },

  /* ------------------------------------------------------- saldo do armazém */
  async saldo() {
    let r;
    try {
      r = await Api.get('/api/wms/saldos', { empresa_id: Estado.empresaId });
    } catch (e) { return UI.erro(e.message); }
    UI.abrirModal({
      titulo: 'Saldo do armazém',
      largo: true,
      corpo: `<div class="mini" style="margin-bottom:10px">O que cada depositante tem guardado agora,
          por armazém, produto e lote — a soma de todas as entradas, saídas, transferências e remoções.</div>
        <div id="lista-saldo-wms">${UI.tabela({
          vazio: 'Nenhum café guardado.',
          colunas: [
            { titulo: 'Armazém', chave: 'armazem', valor: (s) => UI.escapar(s.armazem_nome) },
            { titulo: 'Depositante', valor: (s) => `<b>${UI.escapar(s.depositante_nome)}</b>` },
            { titulo: 'Produto', valor: (s) => UI.escapar(s.produto_nome || '—') },
            { titulo: 'Lote', valor: (s) => UI.escapar(s.lote || '—') },
            { titulo: 'Sacas', classe: 'direita', chave: 'sacas', valor: (s) => `<b>${UI.numero(s.sacas, 2)}</b>` },
            { titulo: 'Peso (kg)', classe: 'direita', chave: 'peso', valor: (s) => UI.numero(s.peso_kg, 0) },
          ],
          linhas: r.saldos,
          rodape: r.saldos.length ? {
            armazem: '<b>Total</b>',
            sacas: `<b>${UI.numero(r.total_sacas, 2)}</b>`,
            peso: `<b>${UI.numero(r.total_peso_kg, 0)}</b>`,
          } : null,
        })}</div>`,
      botoes: [
        { rotulo: 'Exportar', acao: () => UI.exportarTabela('wms-saldo', '#lista-saldo-wms table') },
        { rotulo: 'Fechar', classe: 'btn-primario', acao: () => UI.fecharModal() },
      ],
    });
  },

  /* -------------------------------------------------------------- armazéns */
  listaArmazens() {
    UI.abrirModal({
      titulo: 'Armazéns',
      largo: true,
      corpo: `${UI.tabela({
        vazio: 'Nenhum armazém cadastrado ainda.',
        colunas: [
          { titulo: 'Armazém', valor: (a) => `<b>${UI.escapar(a.nome)}</b>
            <div class="mini">${UI.escapar([a.cidade, a.uf].filter(Boolean).join(' / '))}</div>` },
          { titulo: 'Guardado', classe: 'direita', valor: (a) => `${UI.numero(a.sacas_guardadas, 2)} sc` },
          { titulo: 'Capacidade', classe: 'direita', valor: (a) => (Number(a.capacidade_sacas)
            ? `${UI.numero(a.capacidade_sacas, 0)} sc<div class="mini">${UI.numero(a.ocupacao, 1)}% ocupado</div>` : '—') },
          { titulo: 'Situação', valor: (a) => (a.ativo ? 'Ativo' : '<span class="tag tag-cancelado">Inativo</span>') },
          { titulo: '', classe: 'direita', valor: (a, i) => `<button class="btn btn-mini" data-editar-armazem="${i}">Editar</button>` },
        ],
        linhas: WMS._armazens,
      })}`,
      botoes: [
        { rotulo: 'Fechar', acao: () => UI.fecharModal() },
        { rotulo: 'Novo armazém', classe: 'btn-primario', acao: () => WMS.formularioArmazem(null) },
      ],
    });
    document.querySelectorAll('[data-editar-armazem]').forEach((b) => {
      b.onclick = () => WMS.formularioArmazem(WMS._armazens[Number(b.dataset.editarArmazem)]);
    });
  },

  formularioArmazem(a) {
    const v = a || { nome: '', cidade: '', uf: '', capacidade_sacas: '', observacao: '', ativo: true };
    UI.abrirModal({
      titulo: a ? `Armazém — ${a.nome}` : 'Novo armazém',
      corpo: `<div class="linha-campos">
        ${UI.campo('Nome *', `<input name="nome" maxlength="120" value="${UI.escapar(v.nome)}">`)}
        ${UI.campo('Cidade', `<input name="cidade" maxlength="80" value="${UI.escapar(v.cidade || '')}">`)}
        ${UI.campo('UF', `<input name="uf" maxlength="2" style="text-transform:uppercase" value="${UI.escapar(v.uf || '')}">`)}
        ${UI.campo('Capacidade (sacas)', `<input name="capacidade_sacas" inputmode="decimal"
          value="${v.capacidade_sacas ? UI.numero(v.capacidade_sacas, 0) : ''}">`, 'para mostrar a ocupação')}
        ${UI.campo('Observação', `<input name="observacao" maxlength="300" value="${UI.escapar(v.observacao || '')}">`)}
        <label class="campo">Situação
          <span class="espaco" style="margin-top:6px">
            <input type="checkbox" name="ativo" ${v.ativo ? 'checked' : ''}> <span class="mini">ativo</span>
          </span>
        </label>
      </div>`,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        { rotulo: 'Salvar', classe: 'btn-primario', acao: () => WMS.salvarArmazem(a) },
      ],
      aoSalvar: () => WMS.salvarArmazem(a),
    });
  },

  async salvarArmazem(a) {
    const corpo = document.getElementById('modal-corpo');
    const f = UI.lerFormulario(corpo);
    const dados = {
      empresa_id: Estado.empresaId,
      nome: f.nome,
      cidade: f.cidade,
      uf: f.uf,
      capacidade_sacas: WMS.numero(f.capacidade_sacas),
      observacao: f.observacao,
      ativo: corpo.querySelector('[name="ativo"]').checked,
    };
    try {
      if (a) await Api.put(`/api/wms/armazens/${a.id}`, dados);
      else await Api.post('/api/wms/armazens', dados);
      UI.modalSalvo();
      UI.fecharModal();
      UI.sucesso('Armazém salvo.');
      await WMS.carregar();
    } catch (e) {
      UI.erro(e.message);
    }
  },
};
