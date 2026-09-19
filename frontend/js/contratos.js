/* Contratos de café, em três tipos:
     CORRETAGEM — a empresa só intermedeia e recebe comissão dos dois lados;
     COMPRA     — a empresa compra (conta a pagar do fornecedor);
     VENDA      — a empresa vende (conta a receber do cliente).
   Nos três, um agente pode receber comissão (conta a pagar da empresa). */
const Contratos = {
  filtros: { de: '', ate: '', tipo: '', status: '', q: '' },

  TIPOS: [
    { codigo: 'CORRETAGEM', nome: 'Corretagem (intermediação)' },
    { codigo: 'COMPRA', nome: 'Compra de café' },
    { codigo: 'VENDA', nome: 'Venda de café' },
  ],
  TIPO_CURTO: { CORRETAGEM: 'Corretagem', COMPRA: 'Compra', VENDA: 'Venda' },
  TIPO_TAG: { CORRETAGEM: 'tag-aberto', COMPRA: 'tag-cancelado', VENDA: 'tag-pago' },

  /* situações do contrato — o servidor devolve a lista atualizada a cada consulta */
  STATUS: [
    { codigo: 'ABERTO', nome: 'Aberto' },
    { codigo: 'FECHADO_A_RECEBER', nome: 'Fechado a Receber' },
    { codigo: 'RECEBIDO_PARCIAL', nome: 'Fechado Recebido Parcial' },
    { codigo: 'RECEBIDO_TOTAL', nome: 'Fechado Recebido Total' },
    { codigo: 'CANCELADO', nome: 'Cancelado' },
  ],

  /* ================================================================ LISTAGEM */
  async tela() {
    const alvo = document.getElementById('pagina');
    const f = Contratos.filtros;

    alvo.innerHTML = `
      <div id="kpis-contratos" class="grade g4" style="margin-bottom:18px"></div>
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Contratos</h3><div class="mini" id="resumo-contratos"></div></div>
          <div class="espaco">
            <button class="btn" id="btn-exportar">Exportar CSV</button>
            <button class="btn btn-primario" id="btn-novo-contrato">+ Novo contrato</button>
          </div>
        </div>
        <div class="filtros">
          ${UI.campo('Data de', `<input type="date" name="de" value="${f.de}">`)}
          ${UI.campo('Data até', `<input type="date" name="ate" value="${f.ate}">`)}
          ${UI.campo('Tipo', UI.select('tipo', Contratos.TIPOS
            .map((x) => ({ valor: x.codigo, rotulo: x.nome })), f.tipo, { vazio: 'Todos' }))}
          ${UI.campo('Situação', UI.select('status', Contratos.STATUS
            .map((s) => ({ valor: s.codigo, rotulo: s.nome })), f.status, { vazio: 'Todas' }))}
          ${UI.campo('Buscar', `<input name="q" value="${UI.escapar(f.q)}" placeholder="número, produto...">`)}
          <div class="acoes"><button class="btn btn-primario" id="btn-filtrar">Filtrar</button></div>
        </div>
        <div class="barra-pilulas" id="barra-status"></div>
        <div class="cartao-corpo sem-padding" id="lista-contratos"><div class="vazio">Carregando...</div></div>
      </div>`;

    alvo.querySelector('#btn-filtrar').onclick = () => {
      Object.assign(Contratos.filtros, UI.lerFormulario(alvo.querySelector('.filtros')));
      Contratos.tela();
    };
    alvo.querySelector('#btn-novo-contrato').onclick = () => Contratos.formulario(null);
    alvo.querySelector('#btn-exportar').onclick = () =>
      UI.exportarTabela('contratos', '#lista-contratos table');

    const dados = await Api.get('/api/contratos', {
      empresa_id: Estado.empresaId, de: f.de, ate: f.ate, tipo: f.tipo, status: f.status, q: f.q,
    });
    const t = dados.totais;

    alvo.querySelector('#kpis-contratos').innerHTML = `
      <div class="kpi destaque-azul"><div class="kpi-rotulo">Contratos</div>
        <div class="kpi-valor">${t.quantidade}</div>
        <div class="kpi-nota">${UI.moeda(t.valor_negociado)} negociados${
          (t.por_tipo && (t.por_tipo.COMPRA || t.por_tipo.VENDA))
            ? `<br>corretagem ${t.por_tipo.CORRETAGEM || 0} · compra ${t.por_tipo.COMPRA || 0} · venda ${t.por_tipo.VENDA || 0}`
            : ''}</div></div>
      <div class="kpi destaque-verde"><div class="kpi-rotulo">A receber dos contratos</div>
        <div class="kpi-valor positivo">${UI.moeda(t.a_receber_total)}</div>
        <div class="kpi-nota">comissões ${UI.moeda(t.comissao_total)}${
          t.por_tipo && t.por_tipo.VENDA ? ` · vendas ${UI.moeda(t.a_receber_total - t.comissao_total)}` : ''}</div></div>
      <div class="kpi ${t.a_pagar_total ? 'destaque-vermelho' : ''}"><div class="kpi-rotulo">A pagar dos contratos</div>
        <div class="kpi-valor ${t.a_pagar_total ? 'negativo' : ''}">${UI.moeda(t.a_pagar_total)}</div>
        <div class="kpi-nota">${t.comissao_agente ? `agente ${UI.moeda(t.comissao_agente)}` : 'sem comissão de agente'}</div></div>
      <div class="kpi destaque-ambar"><div class="kpi-rotulo">Já liquidado</div>
        <div class="kpi-valor positivo">${UI.moeda(t.comissao_recebida)}</div>
        <div class="kpi-nota">${t.comissao_vencida ? `<span class="negativo">${UI.moeda(t.comissao_vencida)} vencido</span>` : 'nada vencido'}</div></div>`;

    Contratos.STATUS = dados.status || Contratos.STATUS;
    Contratos.TIPOS = dados.tipos || Contratos.TIPOS;
    alvo.querySelector('#barra-status').innerHTML = Contratos.STATUS
      .map((s) => `<button class="pilula ${f.status === s.codigo ? 'ativa' : ''}" data-status="${s.codigo}">
          ${UI.escapar(s.nome)} <b>${t.por_status[s.codigo] || 0}</b></button>`)
      .join('');
    alvo.querySelectorAll('[data-status]').forEach((b) => {
      b.onclick = () => {
        Contratos.filtros.status = f.status === b.dataset.status ? '' : b.dataset.status;
        Contratos.tela();
      };
    });

    alvo.querySelector('#resumo-contratos').textContent =
      `${t.quantidade} contrato(s) — a receber ${UI.moeda(t.a_receber_total)}`
      + (t.a_pagar_total ? ` · a pagar ${UI.moeda(t.a_pagar_total)}` : '');


    alvo.querySelector('#lista-contratos').innerHTML = UI.tabela({
      colunas: [
        { titulo: 'Contrato', valor: (c) => `<span class="forte">${UI.escapar(c.numero)}</span>
            <div class="mini">${UI.data(c.data)}</div>` },
        { titulo: 'Tipo', classe: 'centro',
          valor: (c) => `<span class="tag ${Contratos.TIPO_TAG[c.tipo] || ''}">${
            UI.escapar(Contratos.TIPO_CURTO[c.tipo] || c.tipo)}</span>` },
        { titulo: 'Comprador', valor: (c) => `${UI.escapar(c.comprador_nome)}${
          c.tipo === 'COMPRA' ? '<div class="mini">minha empresa</div>' : ''}` },
        { titulo: 'Vendedor', valor: (c) => `${UI.escapar(c.vendedor_nome)}${
          c.tipo === 'VENDA' ? '<div class="mini">minha empresa</div>' : ''}` },
        { titulo: 'Mercadoria', valor: (c) => `${UI.escapar(c.produto || '-')}
            <div class="mini">${UI.numero(c.quantidade)} ${UI.escapar(c.unidade || '')} × ${UI.moeda(c.preco_unitario)}</div>` },
        { titulo: 'Valor negociado', classe: 'num', valor: (c) => UI.moeda(c.valor_total) },
        { titulo: 'Comissões', classe: 'num',
          valor: (c) => (c.tipo === 'CORRETAGEM'
            ? `${UI.moeda(c.comissao_comprador_valor, false) || '-'} <span class="mini">comprador ${UI.numero(c.comissao_comprador_percentual, 2)}%</span>
               <div>${UI.moeda(c.comissao_vendedor_valor, false) || '-'} <span class="mini">vendedor ${UI.numero(c.comissao_vendedor_percentual, 2)}%</span></div>`
            : '<span class="mini">—</span>') },
        { titulo: 'Agente', classe: 'num',
          valor: (c) => (c.agente_nome
            ? `${UI.moeda(c.agente_valor)}<div class="mini">${UI.escapar(c.agente_nome)}</div>`
            : '-') },
        { titulo: 'Total', classe: 'num',
          valor: (c) => (c.tipo === 'CORRETAGEM'
            ? `<span class="forte positivo">${UI.moeda(c.comissao_total)}</span>`
            : `<span class="forte">${UI.moeda(c.valor_previsto)}</span>
               <div class="mini">${c.tipo === 'COMPRA' ? 'a pagar' : 'a receber + agente'}</div>`) },
        { titulo: 'Situação', classe: 'centro',
          valor: (c) => `<span class="tag ${c.status_tag}">${UI.escapar(c.status_nome)}</span>` },
        { titulo: 'Ações', classe: 'centro', valor: (c, i) => `
            <button class="btn btn-mini" data-imprimir="${i}">Imprimir</button>
            <button class="btn btn-mini btn-primario" data-ver="${i}">Abrir</button>` },
      ],
      linhas: dados.linhas,
      vazio: 'Nenhum contrato cadastrado. Clique em "+ Novo contrato" para lançar o primeiro.',
    });

    alvo.querySelectorAll('[data-ver]').forEach((b) => {
      b.onclick = () => Contratos.ficha(dados.linhas[Number(b.dataset.ver)].id);
    });
    alvo.querySelectorAll('[data-imprimir]').forEach((b) => {
      b.onclick = () => Impressao.contrato(dados.linhas[Number(b.dataset.imprimir)].id);
    });
  },

  /* ============================================================== FORMULÁRIO
     Lançar contrato é a tarefa mais feita no celular, então o formulário vem
     dividido em etapas curtas: uma tela de cada vez, com Voltar/Próximo e o
     resumo do cálculo sempre à vista. No computador as etapas ficam como abas
     — dá para pular direto para a que interessa. */
  ETAPAS: [
    { id: 'identificacao', rotulo: 'Identificação' },
    { id: 'partes', rotulo: 'Partes' },
    { id: 'mercadoria', rotulo: 'Quantidade' },
    { id: 'corretagem', rotulo: 'Corretagem' },
    { id: 'fechamento', rotulo: 'Embarque' },
  ],

  async formulario(contrato, etapaInicial = 0) {
    const edicao = Boolean(contrato);
    const v = (campo, padrao = '') => UI.escapar(contrato ? (contrato[campo] ?? padrao) : padrao);
    const parceiros = UI.opcoesParceiros();
    const opcoes = (lista, rotulo) => lista.map((r) => ({ valor: r.id, rotulo: rotulo(r) }));
    const produtos = opcoes(Api.produtosAtivos(), (p) => `${p.codigo} - ${p.nome}`);
    const modalidades = opcoes(Api.modalidadesAtivas(), (m) => `${m.codigo} - ${m.nome}`);
    const unidades = opcoes(Api.unidadesAtivas(), (u) => `${u.codigo} - ${u.nome}`);
    const representantes = opcoes(Api.representantes(), (u) => u.nome);

    /* número automático: só sugere; a numeração final sai do servidor ao salvar */
    let sugestao = '';
    if (!edicao) {
      try {
        sugestao = (await Api.get('/api/contratos/proximo-numero',
          { empresa_id: Estado.empresaId })).numero || '';
      } catch { sugestao = ''; }
    }

    const paineis = {
      identificacao: `
        <div class="linha-campos">
          ${UI.campo('Tipo de contrato *', UI.select('tipo', Contratos.TIPOS
            .map((x) => ({ valor: x.codigo, rotulo: x.nome })),
            (contrato && contrato.tipo) || 'CORRETAGEM', { vazio: false }),
            'corretagem só intermedeia; compra e venda geram títulos da mercadoria')}
          ${UI.campo('Nº do contrato', `<input name="numero" value="${v('numero', sugestao)}" placeholder="automático">`, edicao ? '' : 'numeração automática; pode alterar')}
          ${UI.campo('Data do contrato', `<input type="date" name="data" value="${v('data', UI.hoje())}">`)}
          ${UI.campo('Produto', UI.select('produto_id', produtos, contrato ? contrato.produto_id : '', { vazio: 'Selecione o produto' }))}
          ${UI.campo('Modalidade', UI.select('modalidade_id', modalidades, contrato ? contrato.modalidade_id : '', { vazio: 'Selecione a modalidade' }))}
          ${UI.campo('Embalagem', `<input name="embalagem" value="${v('embalagem')}" placeholder="A GRANEL, SACARIA...">`)}
          ${UI.campo('Representante', UI.select('representante_id', representantes, contrato ? contrato.representante_id : '', { vazio: 'Selecione o usuário' }), 'usuários ligados à empresa')}
        </div>`,

      partes: `
        <div class="linha-campos">
          <label class="campo" data-parte="comprador">
            <span id="rotulo-comprador">Comprador *</span>
            ${UI.select('comprador_id', parceiros, contrato ? contrato.comprador_id : '', { vazio: 'Selecione...' })}
          </label>
          <label class="campo" data-parte="vendedor">
            <span id="rotulo-vendedor">Vendedor *</span>
            ${UI.select('vendedor_id', parceiros, contrato ? contrato.vendedor_id : '', { vazio: 'Selecione...' })}
          </label>
        </div>
        <div class="mini" id="aviso-partes" style="margin-top:10px"></div>
        <h4 class="titulo-bloco">Agente (opcional)</h4>
        <div class="linha-campos">
          ${UI.campo('Agente que intermediou', UI.select('agente_id', parceiros, contrato ? contrato.agente_id : '', { vazio: 'Sem agente' }), 'a comissão dele vira conta a pagar')}
          ${UI.campo('% do agente', `<input type="number" inputmode="decimal" step="0.0001" name="agente_percentual" value="${v('agente_percentual', 0)}">`)}
          ${UI.campo('Valor do agente', `<input type="number" inputmode="decimal" step="0.01" name="agente_valor" value="${v('agente_valor', 0)}">`, 'calculado; pode ajustar')}
        </div>
        <div class="mini" style="margin-top:10px">
          Todos precisam estar em Clientes/Fornecedores. Cadastre lá com a busca por CNPJ,
          se for o caso.
        </div>`,

      mercadoria: `
        <div class="linha-campos">
          ${UI.campo('Quantidade', `<input type="number" inputmode="decimal" step="0.001" name="quantidade" value="${v('quantidade', 0)}">`)}
          ${UI.campo('Unidade', UI.select('unidade_id', unidades, contrato ? contrato.unidade_id : '', { vazio: 'Selecione a unidade' }))}
          ${UI.campo('Preço unitário', `<input type="number" inputmode="decimal" step="0.0001" name="preco_unitario" value="${v('preco_unitario', 0)}">`)}
          ${UI.campo('Diferencial', `<input type="number" inputmode="decimal" step="0.0001" name="diferencial" value="${v('diferencial', 0)}">`)}
          ${UI.campo('Valor negociado', `<input type="number" inputmode="decimal" step="0.01" name="valor_total" value="${v('valor_total', 0)}">`, 'calculado; pode ajustar')}
        </div>
        <h4 class="titulo-bloco">ICMS <span class="mini" style="font-weight:400">informativo — não altera o valor negociado nem a corretagem</span></h4>
        <div class="linha-campos">
          ${UI.campo('Alíquota de ICMS (%)', `<input type="number" inputmode="decimal" step="0.01" min="0" name="icms_percentual" value="${v('icms_percentual', 0)}">`, 'vem da tabela de ICMS; pode ajustar')}
          ${UI.campo('Valor do ICMS', '<input type="text" name="icms_valor_tela" readonly tabindex="-1">', 'valor negociado × alíquota')}
        </div>
        <div class="mini" id="icms-info" style="margin-top:8px"></div>`,

      corretagem: `
        <div class="linha-campos" id="bloco-corretagem">
          ${UI.campo('% do comprador', `<input type="number" inputmode="decimal" step="0.0001" name="comissao_comprador_percentual" value="${v('comissao_comprador_percentual', 0)}">`)}
          ${UI.campo('Valor do comprador', `<input type="number" inputmode="decimal" step="0.01" name="comissao_comprador_valor" value="${v('comissao_comprador_valor', 0)}">`)}
          ${UI.campo('% do vendedor', `<input type="number" inputmode="decimal" step="0.0001" name="comissao_vendedor_percentual" value="${v('comissao_vendedor_percentual', 0)}">`)}
          ${UI.campo('Valor do vendedor', `<input type="number" inputmode="decimal" step="0.01" name="comissao_vendedor_valor" value="${v('comissao_vendedor_valor', 0)}">`)}
        </div>
        <div class="mini" id="aviso-corretagem" style="margin-top:10px">
          O percentual manda no cálculo. Digitar o valor direto vale quando a corretagem
          foi combinada em valor fechado.
        </div>`,

      fechamento: `
        <div class="linha-campos">
          ${UI.campo('Data de embarque', `<input type="date" name="data_embarque" value="${v('data_embarque')}">`)}
          ${UI.campo('Data de pagamento', `<input type="date" name="data_pagamento" value="${v('data_pagamento')}">`, 'vencimento sugerido da comissão')}
          ${UI.campo('Nº de compra', `<input name="numero_compra" value="${v('numero_compra')}">`)}
          ${UI.campo('Nº de venda', `<input name="numero_venda" value="${v('numero_venda')}">`)}
          ${UI.campo('Local de coleta', `<input name="local_coleta" value="${v('local_coleta')}">`)}
          ${UI.campo('Local de descarga', `<input name="local_descarga" value="${v('local_descarga')}">`)}
        </div>
        <h4 class="titulo-bloco">Classificação das comissões</h4>
        <div class="linha-campos">
          ${UI.campo('Conta contábil', UI.select('conta_contabil_id', UI.opcoesContas(['RECEITA']), contrato ? contrato.conta_contabil_id : '', { vazio: 'Receita de Corretagem (padrão)' }))}
          ${UI.campo('Centro de custo', UI.select('centro_custo_id', UI.opcoesCentros(), contrato ? contrato.centro_custo_id : '', { vazio: 'Não informado' }))}
          ${UI.campo('Operação', UI.select('operacao_id', UI.opcoesOperacoes('ENTRADA'), contrato ? contrato.operacao_id : '', { vazio: 'Não informada' }))}
        </div>
        <div style="margin-top:12px">
          ${UI.campo('Observações', `<textarea name="observacao">${v('observacao')}</textarea>`)}
        </div>`,
    };

    const corpo = document.createElement('div');
    corpo.className = 'formulario-etapas';
    corpo.innerHTML = `
      <div class="etapas" id="barra-etapas">
        ${Contratos.ETAPAS.map((e, i) => `
          <button type="button" class="etapa" data-etapa="${i}">
            <span class="etapa-numero">${i + 1}</span>
            <span class="etapa-rotulo">${UI.escapar(e.rotulo)}</span>
          </button>`).join('')}
      </div>
      <div class="etapa-progresso"><span id="progresso-etapas"></span></div>
      ${Contratos.ETAPAS.map((e, i) => `
        <section class="painel-etapa ${i ? 'oculto' : ''}" data-painel="${i}">
          <h4 class="titulo-etapa">${i + 1}. ${UI.escapar(e.rotulo)}</h4>
          ${paineis[e.id]}
        </section>`).join('')}
      <div class="resumo-contrato" id="resumo-calculo"></div>`;

    /* ------------------------------------------------------------ cálculo ao vivo */
    const campo = (nome) => corpo.querySelector(`[name=${nome}]`);
    const num = (nome) => Number(campo(nome).value || 0);
    const set = (nome, valor) => { campo(nome).value = valor.toFixed(2); };
    let totalManual = edicao;
    let icmsManual = Boolean(contrato && contrato.icms_manual);
    let agenteManual = Boolean(contrato && contrato.agente_id && contrato.agente_valor
      && contrato.agente_percentual === 0);
    const tipo = () => campo('tipo').value || 'CORRETAGEM';
    const minhaEmpresa = () => {
      const e = (Estado.empresas || []).find((x) => String(x.id) === String(Estado.empresaId));
      return (e && (e.nome_fantasia || e.razao_social)) || 'minha empresa';
    };

    /* mostra só o que o tipo escolhido precisa */
    const aplicarTipo = () => {
      const t = tipo();
      const compra = t === 'COMPRA';
      const venda = t === 'VENDA';
      const corretagem = t === 'CORRETAGEM';
      corpo.querySelector('[data-parte="comprador"]').classList.toggle('oculto', compra);
      corpo.querySelector('[data-parte="vendedor"]').classList.toggle('oculto', venda);
      corpo.querySelector('#bloco-corretagem').classList.toggle('oculto', !corretagem);
      corpo.querySelector('#aviso-corretagem').classList.toggle('oculto', !corretagem);
      corpo.querySelector('#rotulo-comprador').textContent = compra
        ? 'Comprador' : (venda ? 'Cliente (para quem estou vendendo) *' : 'Comprador *');
      corpo.querySelector('#rotulo-vendedor').textContent = venda
        ? 'Vendedor' : (compra ? 'Fornecedor (de quem estou comprando) *' : 'Vendedor *');
      const avisos = {
        CORRETAGEM: 'A empresa só intermedeia: as duas comissões viram contas a receber.',
        COMPRA: `Quem compra é <b>${UI.escapar(minhaEmpresa())}</b>. O valor do café vira uma `
          + '<b>conta a pagar</b> do fornecedor, e a comissão do agente, outra conta a pagar.',
        VENDA: `Quem vende é <b>${UI.escapar(minhaEmpresa())}</b>. O valor do café vira uma `
          + '<b>conta a receber</b> do cliente, e a comissão do agente, uma conta a pagar.',
      };
      corpo.querySelector('#aviso-partes').innerHTML = avisos[t];
      const etapa = corpo.querySelector('[data-etapa="3"] .etapa-rotulo');
      const titulo = corpo.querySelector('[data-painel="3"] .titulo-etapa');
      const nome = corretagem ? 'Corretagem' : 'Comissões';
      if (etapa) etapa.textContent = nome;
      if (titulo) titulo.textContent = `4. ${nome}`;
    };
    const parceiro = (id) => (Estado.cache.parceiros || []).find((p) => String(p.id) === String(id));

    /* ICMS: procura a alíquota pela UF do vendedor e do comprador (e produto) */
    const atualizarIcms = (total) => {
      const vendedor = parceiro(campo('vendedor_id').value);
      const comprador = parceiro(campo('comprador_id').value);
      const origem = (vendedor && vendedor.uf || '').toUpperCase();
      const destino = (comprador && comprador.uf || '').toUpperCase();
      const linha = Api.aliquotaIcms(origem, destino, campo('produto_id').value);
      if (!icmsManual) campo('icms_percentual').value = (linha ? Number(linha.aliquota) : 0).toFixed(2);
      const percentual = num('icms_percentual');
      const valor = Math.round(total * percentual) / 100;
      campo('icms_valor_tela').value = UI.moeda(valor);

      const faltando = [];
      if (vendedor && !origem) faltando.push(`vendedor (${vendedor.nome})`);
      if (comprador && !destino) faltando.push(`comprador (${comprador.nome})`);
      let texto;
      if (!vendedor || !comprador) {
        texto = 'Escolha o comprador e o vendedor na etapa Partes para buscar a alíquota.';
      } else if (faltando.length) {
        texto = `⚠ Falta a UF no cadastro do ${faltando.join(' e do ')}. Complete em Clientes/Fornecedores.`;
      } else if (icmsManual) {
        texto = `${UI.escapar(origem)} → ${UI.escapar(destino)} · alíquota digitada`
          + (linha ? ` (tabela: ${UI.numero(linha.aliquota, 2)}%)` : '')
          + ' · <a href="#" data-icms-tabela>usar a da tabela</a>';
      } else if (linha) {
        texto = `${UI.escapar(origem)} → ${UI.escapar(destino)} · tabela de ICMS: ${UI.numero(linha.aliquota, 2)}%`
          + (linha.produto_id ? ` para ${UI.escapar(linha.produto_nome || 'este produto')}` : ' (todos os produtos)')
          + (linha.observacao ? ` · ${UI.escapar(linha.observacao)}` : '');
      } else {
        texto = `⚠ Não há alíquota cadastrada para ${UI.escapar(origem)} → ${UI.escapar(destino)}. `
          + 'Cadastre em Cadastros › ICMS ou digite a alíquota aqui.';
      }
      const info = corpo.querySelector('#icms-info');
      info.innerHTML = texto;
      const link = info.querySelector('[data-icms-tabela]');
      if (link) link.onclick = (ev) => { ev.preventDefault(); icmsManual = false; recalcular('icms_tabela'); };
      return { origem, destino, percentual, valor };
    };

    const recalcular = (origem) => {
      if (origem === 'valor_total') totalManual = true;
      if (['quantidade', 'preco_unitario', 'diferencial'].includes(origem)) totalManual = false;
      if (!totalManual) {
        set('valor_total', num('quantidade') * (num('preco_unitario') + num('diferencial')));
      }
      const total = num('valor_total');
      if (origem !== 'comissao_comprador_valor') {
        set('comissao_comprador_valor', total * num('comissao_comprador_percentual') / 100);
      }
      if (origem !== 'comissao_vendedor_valor') {
        set('comissao_vendedor_valor', total * num('comissao_vendedor_percentual') / 100);
      }
      if (origem === 'icms_percentual') icmsManual = true;
      if (origem === 'agente_valor') agenteManual = true;
      if (origem === 'agente_percentual') agenteManual = false;
      const temAgente = Boolean(campo('agente_id').value);
      if (!temAgente) { campo('agente_percentual').value = 0; set('agente_valor', 0); }
      else if (!agenteManual) set('agente_valor', total * num('agente_percentual') / 100);
      const agente = temAgente ? num('agente_valor') : 0;
      const icms = atualizarIcms(total);
      const comissao = num('comissao_comprador_valor') + num('comissao_vendedor_valor');
      const unidade = Api.unidadesAtivas()
        .find((u) => String(u.id) === campo('unidade_id').value);
      const peso = unidade ? num('quantidade') * Number(unidade.peso_conversao || 0) : 0;
      /* enquanto não há número nenhum o resumo fica fora do caminho */
      corpo.querySelector('#resumo-calculo').classList.toggle('oculto',
        !total && !comissao && !peso);
      const t = tipo();
      const linhaAgente = agente ? `<div class="resumo-linha">
          <span>Comissão do agente <small>a pagar</small></span>
          <b class="negativo">${UI.moeda(agente)}
            ${total ? `<small>${UI.numero(agente / total * 100, 3)}% do contrato</small>` : ''}</b>
        </div>` : '';
      corpo.querySelector('#resumo-calculo').innerHTML = `
        <div class="resumo-linha">
          <span>${t === 'COMPRA' ? 'Valor da compra' : t === 'VENDA' ? 'Valor da venda' : 'Valor negociado'}</span>
          <b>${UI.moeda(total)}</b>
        </div>
        ${t === 'CORRETAGEM' ? `<div class="resumo-linha">
          <span>Comissão do comprador</span><b>${UI.moeda(num('comissao_comprador_valor'))}</b>
        </div>
        <div class="resumo-linha">
          <span>Comissão do vendedor</span><b>${UI.moeda(num('comissao_vendedor_valor'))}</b>
        </div>${linhaAgente}
        <div class="resumo-linha total">
          <span>Total a receber</span>
          <b class="positivo">${UI.moeda(comissao)}
            ${total ? `<small>${UI.numero(comissao / total * 100, 3)}% do contrato</small>` : ''}</b>
        </div>` : `${linhaAgente}
        <div class="resumo-linha total">
          <span>${t === 'COMPRA' ? 'Total a pagar' : 'A receber do cliente'}</span>
          <b class="${t === 'COMPRA' ? 'negativo' : 'positivo'}">${UI.moeda(t === 'COMPRA' ? total + agente : total)}
            ${t === 'COMPRA' && agente ? '<small>café + comissão do agente</small>' : ''}</b>
        </div>`}
        ${icms.percentual ? `<div class="resumo-linha">
          <span>ICMS ${icms.origem && icms.destino ? `${UI.escapar(icms.origem)} → ${UI.escapar(icms.destino)}` : ''}</span>
          <b>${UI.moeda(icms.valor)} <small>${UI.numero(icms.percentual, 2)}% · informativo</small></b>
        </div>` : ''}
        ${peso ? `<div class="resumo-linha">
          <span>Peso total</span><b>${UI.numero(peso, 3)} kg
            <small>${UI.numero(unidade.peso_conversao, 3)} kg por ${UI.escapar(unidade.codigo)}</small></b>
        </div>` : ''}`;
    };

    ['quantidade', 'preco_unitario', 'diferencial', 'valor_total',
     'comissao_comprador_percentual', 'comissao_vendedor_percentual',
     'comissao_comprador_valor', 'comissao_vendedor_valor', 'icms_percentual',
     'agente_percentual', 'agente_valor'].forEach((nome) => {
      campo(nome).oninput = () => recalcular(nome);
    });
    campo('unidade_id').onchange = () => recalcular('unidade_id');
    campo('agente_id').onchange = () => { agenteManual = false; recalcular('agente_id'); };
    campo('tipo').onchange = () => { aplicarTipo(); recalcular('tipo'); };
    campo('comprador_id').onchange = () => recalcular('comprador_id');
    campo('vendedor_id').onchange = () => recalcular('vendedor_id');
    /* o produto pode trazer a unidade e a embalagem padrão */
    campo('produto_id').onchange = (ev) => {
      const produto = Api.produtosAtivos().find((p) => String(p.id) === ev.target.value);
      if (!produto) return;
      if (produto.unidade_id && !campo('unidade_id').value) campo('unidade_id').value = produto.unidade_id;
      if (produto.embalagem && !campo('embalagem').value) campo('embalagem').value = produto.embalagem;
      recalcular('produto_id');
    };
    aplicarTipo();
    recalcular();

    /* ------------------------------------------------------- navegação das etapas */
    let atual = etapaInicial;
    let registroId = contrato ? contrato.id : null;
    const ultima = Contratos.ETAPAS.length - 1;

    const validar = (indice) => {
      if (indice === 1) {   // partes
        const t = tipo();
        const c = campo('comprador_id').value;
        const vd = campo('vendedor_id').value;
        const ag = campo('agente_id').value;
        if (t === 'COMPRA' && !vd) {
          UI.erro('Escolha o fornecedor de quem você está comprando.'); return false;
        }
        if (t === 'VENDA' && !c) {
          UI.erro('Escolha o cliente para quem você está vendendo.'); return false;
        }
        if (t === 'CORRETAGEM') {
          if (!c || !vd) { UI.erro('Escolha o comprador e o vendedor.'); return false; }
          if (c === vd) {
            UI.erro('O comprador e o vendedor precisam ser cadastros diferentes.');
            return false;
          }
        }
        if (ag && (ag === c || ag === vd)) {
          UI.erro('O agente precisa ser um cadastro diferente das partes.'); return false;
        }
      }
      return true;
    };

    /* `fechar` verdadeiro grava e abre a ficha; falso grava e deixa você
       continuar na mesma etapa (é o botão Salvar que aparece em toda etapa). */
    const salvar = async (fechar = true) => {
      for (let i = 0; i <= ultima; i += 1) {
        if (!validar(i)) { irPara(i); return; }
      }
      const d = UI.lerFormulario(corpo);
      const opcional = (nome) => (d[nome] ? Number(d[nome]) : null);
      const t = d.tipo || 'CORRETAGEM';
      const payload = {
        ...d,
        empresa_id: Estado.empresaId,
        tipo: t,
        numero: (d.numero || '').trim() || null,   // em branco = numeração automática
        // na compra quem compra é a empresa; na venda, quem vende
        comprador_id: t === 'COMPRA' ? null : opcional('comprador_id'),
        vendedor_id: t === 'VENDA' ? null : opcional('vendedor_id'),
        agente_id: opcional('agente_id'),
        agente_percentual: Number(d.agente_percentual || 0),
        agente_valor: Number(d.agente_valor || 0),
        produto_id: opcional('produto_id'),
        modalidade_id: opcional('modalidade_id'),
        unidade_id: opcional('unidade_id'),
        representante_id: opcional('representante_id'),
        conta_contabil_id: opcional('conta_contabil_id'),
        centro_custo_id: opcional('centro_custo_id'),
        operacao_id: opcional('operacao_id'),
        icms_manual: icmsManual,
        icms_percentual: Number(d.icms_percentual || 0),
      };
      delete payload.icms_valor_tela;
      try {
        const salvo = registroId
          ? await Api.put(`/api/contratos/${registroId}`, payload)
          : await Api.post('/api/contratos', payload);
        registroId = salvo.id;
        UI.modalSalvo();
        UI.sucesso('Contrato salvo.');
        if (!fechar) return Contratos.formulario(salvo, atual);
        UI.fecharModal();
        Contratos.ficha(salvo.id);
      } catch (e) {
        UI.erro(e.message);
      }
    };

    const botoes = () => {
      const lista = [];
      if (atual > 0) lista.push({ rotulo: '← Voltar', acao: () => irPara(atual - 1) });
      else lista.push({ rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() });
      if (atual < ultima) {
        // dá para gravar em qualquer etapa, sem precisar ir até o fim
        lista.push({ rotulo: 'Salvar', acao: () => salvar(false) });
        lista.push({
          rotulo: 'Próximo →',
          classe: 'btn-primario',
          acao: () => { if (validar(atual)) irPara(atual + 1); },
        });
      } else {
        lista.push({
          rotulo: edicao ? 'Salvar contrato' : 'Salvar e abrir',
          classe: 'btn-primario',
          acao: () => salvar(true),
        });
      }
      return lista;
    };

    const irPara = (indice) => {
      atual = Math.max(0, Math.min(indice, ultima));
      corpo.querySelectorAll('[data-painel]').forEach((p) => {
        p.classList.toggle('oculto', Number(p.dataset.painel) !== atual);
      });
      corpo.querySelectorAll('[data-etapa]').forEach((b) => {
        const i = Number(b.dataset.etapa);
        b.classList.toggle('ativa', i === atual);
        b.classList.toggle('feita', i < atual);
      });
      corpo.querySelector('#progresso-etapas').style.width =
        `${((atual + 1) / (ultima + 1)) * 100}%`;
      /* leva a etapa escolhida para a vista no celular */
      corpo.querySelector('.etapa.ativa')?.scrollIntoView(
        { block: 'nearest', inline: 'center', behavior: 'smooth' });
      document.getElementById('modal-corpo').scrollTop = 0;
      UI.trocarBotoes(botoes(), corpo);
      const primeiro = corpo.querySelector(`[data-painel="${atual}"] input,[data-painel="${atual}"] select`);
      if (primeiro && window.innerWidth > 760) setTimeout(() => primeiro.focus(), 40);
    };

    corpo.querySelectorAll('[data-etapa]').forEach((b) => {
      b.onclick = () => {
        const destino = Number(b.dataset.etapa);
        if (destino > atual && !validar(atual)) return;
        irPara(destino);
      };
    });

    UI.abrirModal({
      titulo: edicao ? `Editar contrato ${contrato.numero}` : 'Novo contrato',
      corpo,
      largo: true,
      aoSalvar: () => salvar(true),
      botoes: botoes(),
    });
    irPara(etapaInicial);
  },

  /* ============================================================ FICHA / AÇÕES */
  async ficha(id) {
    const c = await Api.get(`/api/contratos/${id}`);
    const corpo = document.createElement('div');

    const linha = (rotulo, valor) =>
      `<div><div class="mini">${UI.escapar(rotulo)}</div><div class="forte">${valor || '-'}</div></div>`;

    const compra = c.tipo === 'COMPRA';
    const venda = c.tipo === 'VENDA';
    const corretagem = c.tipo === 'CORRETAGEM';

    /* cartão de um título do contrato — a receber (verde) ou a pagar (vermelho) */
    const titulo = (r, rotulo, pagar, vazio) => {
      if (!r) return `<div class="mini">${UI.escapar(vazio)}</div>`;
      return `
        <div class="forma-cartao">
          <div class="forma-topo">
            <div><span class="tag ${pagar ? 'tag-cancelado' : 'tag-pago'}">${UI.escapar(rotulo)}</span>
              <span class="forte"> ${UI.moeda(r.valor)}</span>
              <span class="mini"> em ${r.qtd_parcelas} parcela(s)</span></div>
            <div>${UI.tagStatus(r.status)}</div>
          </div>
          <div class="mini">
            Vencimento ${r.proximo_vencimento ? UI.data(r.proximo_vencimento) : '-'} ·
            ${pagar ? 'pago' : 'recebido'} ${UI.moeda(r.baixado)} · saldo ${UI.moeda(r.saldo)}
          </div>
        </div>`;
    };
    const recebivel = (r, lado) => titulo(r, lado, false,
      `Comissão ${lado}: nenhuma conta a receber gerada.`);

    corpo.innerHTML = `
      <div class="grade g3" style="margin-bottom:14px">
        ${linha('Contrato', `${UI.escapar(c.numero)}
          <div class="mini">${UI.escapar(c.tipo_nome || '')}</div>`)}
        ${linha('Data', UI.data(c.data))}
        ${linha('Situação', `<span class="tag ${c.status_tag}">${UI.escapar(c.status_nome)}</span>`)}
        ${linha('Comprador', `${UI.escapar(c.comprador_nome)}<div class="mini">${compra ? 'minha empresa' : UI.escapar(c.comprador_documento || '')}</div>`)}
        ${linha('Vendedor', `${UI.escapar(c.vendedor_nome)}<div class="mini">${venda ? 'minha empresa' : UI.escapar(c.vendedor_documento || '')}</div>`)}
        ${c.agente_nome ? linha('Agente', `${UI.escapar(c.agente_nome)}
          <div class="mini">comissão ${UI.moeda(c.agente_valor)} · ${UI.numero(c.agente_percentual, 3)}%</div>`) : ''}
        ${linha('Representante', UI.escapar(c.representante_nome || c.corretor || ''))}
        ${linha('Mercadoria', `${UI.escapar(c.produto_nome || c.produto || '')}
          <div class="mini">${UI.escapar(c.modalidade_nome || c.modalidade || '')} ${UI.escapar(c.embalagem || '')}</div>`)}
        ${linha('Quantidade', `${UI.numero(c.quantidade, 2)} ${UI.escapar(c.unidade || '')}
          ${c.peso_total ? `<div class="mini">${UI.numero(c.peso_total, 3)} kg no total</div>` : ''}`)}
        ${linha('Preço unitário', UI.moeda(c.preco_unitario))}
        ${linha(compra ? 'Valor da compra' : venda ? 'Valor da venda' : 'Valor negociado', `<span style="font-size:17px">${UI.moeda(c.valor_total)}</span>`)}
        ${linha('ICMS', c.icms_percentual
          ? `${UI.moeda(c.icms_valor)}<div class="mini">${UI.numero(c.icms_percentual, 2)}%${c.icms_regra ? ` · ${UI.escapar(c.icms_regra)}` : ''}${c.icms_manual ? ' · digitado' : ' · tabela'}</div>`
          : `<span class="mini">sem ICMS${c.icms_regra ? ` (${UI.escapar(c.icms_regra)})` : ''}</span>`)}
        ${linha('Embarque', c.data_embarque ? UI.data(c.data_embarque) : '')}
        ${linha('Pagamento', c.data_pagamento ? UI.data(c.data_pagamento) : '')}
        ${linha('Nº compra', UI.escapar(c.numero_compra || ''))}
        ${linha('Nº venda', UI.escapar(c.numero_venda || ''))}
        ${linha('Classificação', UI.escapar(c.conta_contabil_nome || ''))}
      </div>
      ${c.local_coleta || c.local_descarga ? `<div class="grade g2" style="margin-bottom:14px">
        ${linha('Local de coleta', UI.escapar(c.local_coleta || ''))}
        ${linha('Local de descarga', UI.escapar(c.local_descarga || ''))}</div>` : ''}
      ${c.observacao ? `<div class="mini" style="margin-bottom:14px">${UI.escapar(c.observacao)}</div>` : ''}

      ${corretagem ? `<div class="grade g3" style="margin-bottom:16px">
        <div class="kpi"><div class="kpi-rotulo">Comissão do comprador</div>
          <div class="kpi-valor" style="font-size:19px">${UI.moeda(c.comissao_comprador_valor)}</div>
          <div class="kpi-nota">${UI.numero(c.comissao_comprador_percentual, 3)}% do contrato</div></div>
        <div class="kpi"><div class="kpi-rotulo">Comissão do vendedor</div>
          <div class="kpi-valor" style="font-size:19px">${UI.moeda(c.comissao_vendedor_valor)}</div>
          <div class="kpi-nota">${UI.numero(c.comissao_vendedor_percentual, 3)}% do contrato</div></div>
        <div class="kpi destaque-verde"><div class="kpi-rotulo">Total a receber</div>
          <div class="kpi-valor positivo" style="font-size:19px">${UI.moeda(c.comissao_total)}</div>
          <div class="kpi-nota">${UI.numero(c.percentual_total, 3)}% do contrato</div></div>
      </div>` : `<div class="grade g3" style="margin-bottom:16px">
        <div class="kpi ${compra ? '' : 'destaque-verde'}">
          <div class="kpi-rotulo">${compra ? 'A pagar pelo café' : 'A receber do café'}</div>
          <div class="kpi-valor ${compra ? '' : 'positivo'}" style="font-size:19px">${UI.moeda(c.valor_total)}</div>
          <div class="kpi-nota">${UI.escapar(compra ? c.vendedor_nome : c.comprador_nome)}</div></div>
        <div class="kpi ${c.agente_valor ? 'destaque-vermelho' : ''}">
          <div class="kpi-rotulo">Comissão do agente</div>
          <div class="kpi-valor ${c.agente_valor ? 'negativo' : ''}" style="font-size:19px">${UI.moeda(c.agente_valor)}</div>
          <div class="kpi-nota">${c.agente_nome ? `a pagar para ${UI.escapar(c.agente_nome)}` : 'sem agente neste contrato'}</div></div>
        <div class="kpi destaque-azul"><div class="kpi-rotulo">${compra ? 'Total a pagar' : 'Total do contrato'}</div>
          <div class="kpi-valor" style="font-size:19px">${UI.moeda(c.valor_previsto)}</div>
          <div class="kpi-nota">${compra ? 'café + comissão do agente' : 'a receber do café e a pagar do agente'}</div></div>
      </div>`}

      <h4 class="titulo-bloco">Situação financeira</h4>
      <div class="grade g4" style="margin-bottom:14px">
        <div class="kpi"><div class="kpi-rotulo">${compra ? 'Virou conta a pagar' : 'Virou título'}</div>
          <div class="kpi-valor" style="font-size:17px">${UI.moeda(c.financeiro.gerado)}</div>
          <div class="kpi-nota">${c.financeiro.parcelas} parcela(s)</div></div>
        <div class="kpi destaque-verde"><div class="kpi-rotulo">${compra ? 'Pago' : 'Recebido'}</div>
          <div class="kpi-valor positivo" style="font-size:17px">${UI.moeda(c.financeiro.recebido)}</div>
          <div class="kpi-nota">${UI.numero(c.financeiro.recebido_percentual, 1)}% · ${c.financeiro.parcelas_pagas} parcela(s) paga(s)</div></div>
        <div class="kpi destaque-ambar"><div class="kpi-rotulo">${compra ? 'Falta pagar' : 'Falta receber'}</div>
          <div class="kpi-valor" style="font-size:17px">${UI.moeda(c.comissao_a_receber)}</div>
          <div class="kpi-nota">${c.financeiro.a_gerar ? `${UI.moeda(c.financeiro.a_gerar)} ainda sem título` : 'tudo lançado'}</div></div>
        <div class="kpi ${c.financeiro.vencido ? 'destaque-vermelho' : ''}"><div class="kpi-rotulo">Vencido</div>
          <div class="kpi-valor ${c.financeiro.vencido ? 'negativo' : ''}" style="font-size:17px">${UI.moeda(c.financeiro.vencido)}</div>
          <div class="kpi-nota">${c.financeiro.dias_atraso ? `${c.financeiro.dias_atraso} dia(s) em atraso` : 'em dia'}</div></div>
      </div>

      <h4 class="titulo-bloco">${corretagem ? 'Contas a receber deste contrato' : 'Títulos deste contrato'}</h4>
      ${corretagem ? `${recebivel(c.recebivel_comprador, 'do comprador')}
      ${recebivel(c.recebivel_vendedor, 'do vendedor')}` : titulo(c.titulo_mercadoria,
        compra ? `a pagar · ${c.vendedor_nome}` : `a receber · ${c.comprador_nome}`, compra,
        compra ? 'Café: nenhuma conta a pagar gerada.' : 'Café: nenhuma conta a receber gerada.')}
      ${c.agente_id ? titulo(c.titulo_agente, `a pagar · agente ${c.agente_nome}`, true,
        'Agente: nenhuma conta a pagar gerada.') : ''}
      ${c.status !== 'CANCELADO' && c.financeiro.a_gerar > 0 ? `
        <div class="linha-campos" style="margin-top:12px">
          ${UI.campo('Vencimento', `<input type="date" name="vencimento" value="${(c.data_pagamento || UI.hoje()).slice(0, 10)}">`)}
          ${UI.campo('Parcelas', '<input type="number" name="num_parcelas" min="1" max="36" value="1">')}
          ${UI.campo('Periodicidade', UI.select('periodicidade', [
            { valor: 'MENSAL', rotulo: 'Mensal' }, { valor: 'DIAS', rotulo: 'A cada N dias' },
          ], 'MENSAL', { vazio: false }))}
          ${UI.campo('Intervalo (dias)', '<input type="number" name="intervalo_dias" value="30">')}
          ${!corretagem && c.agente_id ? UI.campo('Vencimento do agente', `<input type="date" name="vencimento_agente" value="${(c.data_pagamento || UI.hoje()).slice(0, 10)}">`, 'em branco usa o mesmo do café') : ''}
        </div>
        <div class="espaco" style="margin-top:10px">
          ${corretagem ? `
          <label class="mini"><input type="checkbox" name="gerar_comprador" ${c.comissao_comprador_valor && !c.recebivel_comprador ? 'checked' : 'disabled'}> gerar comissão do comprador</label>
          <label class="mini"><input type="checkbox" name="gerar_vendedor" ${c.comissao_vendedor_valor && !c.recebivel_vendedor ? 'checked' : 'disabled'}> gerar comissão do vendedor</label>` : `
          <label class="mini"><input type="checkbox" name="gerar_mercadoria" ${c.valor_total && !c.titulo_mercadoria ? 'checked' : 'disabled'}> gerar ${compra ? 'conta a pagar do café' : 'conta a receber do café'}</label>`}
          ${c.agente_id && c.agente_valor ? `<label class="mini"><input type="checkbox" name="gerar_agente" ${c.titulo_agente ? 'disabled' : 'checked'}> gerar conta a pagar do agente</label>` : ''}
        </div>` : ''}`;

    const botoes = [
      { rotulo: 'Fechar', acao: () => { UI.fecharModal(); Contratos.tela(); } },
      { rotulo: 'Imprimir', acao: () => Impressao.contrato(c.id) },
    ];

    const temTitulos = Boolean(c.recebivel_comprador || c.recebivel_vendedor
      || c.titulo_mercadoria || c.titulo_agente);

    if (c.status === 'CANCELADO') {
      botoes.push({
        rotulo: 'Reabrir contrato',
        classe: 'btn-primario',
        acao: async () => {
          try {
            await Api.post(`/api/contratos/${c.id}/reabrir`);
            UI.sucesso('Contrato reaberto.');
            Contratos.ficha(c.id);
          } catch (e) { UI.erro(e.message); }
        },
      });
    } else if (temTitulos) {
      botoes.push({
        rotulo: corretagem ? 'Estornar recebíveis' : 'Estornar títulos',
        classe: 'btn-perigo',
        acao: async () => {
          if (!(await UI.confirmar(
            'Apagar os títulos gerados por este contrato? Só é possível se ainda não houver baixa.',
            'Estornar'))) return;
          try {
            await Api.post(`/api/contratos/${c.id}/estornar-recebiveis`);
            UI.sucesso('Títulos estornados.');
            Contratos.ficha(c.id);
          } catch (e) { UI.erro(e.message); }
        },
      });
    }

    if (!temTitulos && c.status !== 'CANCELADO') {
      botoes.push(
        {
          rotulo: 'Cancelar contrato',
          classe: 'btn-perigo',
          acao: async () => {
            if (!(await UI.confirmar(
              `Cancelar o contrato ${c.numero}? Ele continua na lista, marcado como cancelado.`,
              'Cancelar contrato'))) return;
            try {
              await Api.post(`/api/contratos/${c.id}/cancelar`);
              UI.sucesso('Contrato cancelado.');
              Contratos.ficha(c.id);
            } catch (e) { UI.erro(e.message); }
          },
        },
        {
          rotulo: 'Excluir',
          classe: 'btn-perigo',
          acao: async () => {
            if (!(await UI.confirmar(`Excluir o contrato ${c.numero}?`, 'Excluir'))) return;
            try {
              await Api.del(`/api/contratos/${c.id}`);
              UI.fecharModal();
              UI.sucesso('Contrato excluído.');
              Contratos.tela();
            } catch (e) { UI.erro(e.message); }
          },
        },
        { rotulo: 'Editar', acao: () => { UI.fecharModal(); Contratos.formulario(c); } },
      );
    }

    if (c.status !== 'CANCELADO' && c.financeiro.a_gerar > 0) {
      botoes.push(
        {
          rotulo: corretagem ? 'Gerar contas a receber'
            : compra ? 'Gerar contas a pagar' : 'Gerar títulos do contrato',
          classe: 'btn-verde',
          acao: async () => {
            const d = UI.lerFormulario(corpo);
            try {
              const r = await Api.post(`/api/contratos/${c.id}/gerar-recebiveis`, {
                vencimento: d.vencimento,
                num_parcelas: Number(d.num_parcelas) || 1,
                periodicidade: d.periodicidade,
                intervalo_dias: Number(d.intervalo_dias) || 30,
                gerar_comprador: Boolean(d.gerar_comprador),
                gerar_vendedor: Boolean(d.gerar_vendedor),
                gerar_mercadoria: Boolean(d.gerar_mercadoria),
                gerar_agente: Boolean(d.gerar_agente),
                vencimento_agente: d.vencimento_agente || null,
              });
              UI.sucesso(r.mensagem);
              Contratos.ficha(c.id);
            } catch (e) { UI.erro(e.message); }
          },
        },
      );
    }

    UI.abrirModal({ titulo: `${UI.escapar(c.tipo_nome || 'Contrato')} ${c.numero}`, corpo, largo: true, botoes });
  },
};
