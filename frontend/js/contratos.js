/* Contratos de intermediação: comprador, vendedor, comissão dos dois lados
   e geração das contas a receber. */
const Contratos = {
  filtros: { de: '', ate: '', status: '', q: '' },

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
      empresa_id: Estado.empresaId, de: f.de, ate: f.ate, status: f.status, q: f.q,
    });
    const t = dados.totais;

    alvo.querySelector('#kpis-contratos').innerHTML = `
      <div class="kpi destaque-azul"><div class="kpi-rotulo">Contratos</div>
        <div class="kpi-valor">${t.quantidade}</div>
        <div class="kpi-nota">${UI.moeda(t.valor_negociado)} negociados</div></div>
      <div class="kpi destaque-verde"><div class="kpi-rotulo">Comissão total</div>
        <div class="kpi-valor positivo">${UI.moeda(t.comissao_total)}</div>
        <div class="kpi-nota">comprador ${UI.moeda(t.comissao_comprador)} · vendedor ${UI.moeda(t.comissao_vendedor)}</div></div>
      <div class="kpi"><div class="kpi-rotulo">Já recebido</div>
        <div class="kpi-valor positivo">${UI.moeda(t.comissao_recebida)}</div>
        <div class="kpi-nota">${t.comissao_total ? UI.numero(t.comissao_recebida / t.comissao_total * 100, 1) : '0,0'}% da comissão</div></div>
      <div class="kpi destaque-ambar"><div class="kpi-rotulo">A receber</div>
        <div class="kpi-valor">${UI.moeda(t.comissao_a_receber)}</div>
        <div class="kpi-nota">${t.comissao_vencida ? `<span class="negativo">${UI.moeda(t.comissao_vencida)} vencido</span>` : 'nada vencido'}</div></div>`;

    Contratos.STATUS = dados.status || Contratos.STATUS;
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
      `${t.quantidade} contrato(s) — comissão ${UI.moeda(t.comissao_total)}`;


    alvo.querySelector('#lista-contratos').innerHTML = UI.tabela({
      colunas: [
        { titulo: 'Contrato', valor: (c) => `<span class="forte">${UI.escapar(c.numero)}</span>
            <div class="mini">${UI.data(c.data)}</div>` },
        { titulo: 'Comprador', valor: (c) => UI.escapar(c.comprador_nome) },
        { titulo: 'Vendedor', valor: (c) => UI.escapar(c.vendedor_nome) },
        { titulo: 'Mercadoria', valor: (c) => `${UI.escapar(c.produto || '-')}
            <div class="mini">${UI.numero(c.quantidade)} ${UI.escapar(c.unidade || '')} × ${UI.moeda(c.preco_unitario)}</div>` },
        { titulo: 'Valor negociado', classe: 'num', valor: (c) => UI.moeda(c.valor_total) },
        { titulo: 'Comissão comprador', classe: 'num',
          valor: (c) => `${UI.moeda(c.comissao_comprador_valor, false) || '-'}
            <div class="mini">${UI.numero(c.comissao_comprador_percentual, 2)}%</div>` },
        { titulo: 'Comissão vendedor', classe: 'num',
          valor: (c) => `${UI.moeda(c.comissao_vendedor_valor, false) || '-'}
            <div class="mini">${UI.numero(c.comissao_vendedor_percentual, 2)}%</div>` },
        { titulo: 'Total', classe: 'num',
          valor: (c) => `<span class="forte positivo">${UI.moeda(c.comissao_total)}</span>` },
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

  async formulario(contrato) {
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
          ${UI.campo('Nº do contrato', `<input name="numero" value="${v('numero', sugestao)}" placeholder="automático">`, edicao ? '' : 'numeração automática; pode alterar')}
          ${UI.campo('Data do contrato', `<input type="date" name="data" value="${v('data', UI.hoje())}">`)}
          ${UI.campo('Produto', UI.select('produto_id', produtos, contrato ? contrato.produto_id : '', { vazio: 'Selecione o produto' }))}
          ${UI.campo('Modalidade', UI.select('modalidade_id', modalidades, contrato ? contrato.modalidade_id : '', { vazio: 'Selecione a modalidade' }))}
          ${UI.campo('Embalagem', `<input name="embalagem" value="${v('embalagem')}" placeholder="A GRANEL, SACARIA...">`)}
          ${UI.campo('Representante', UI.select('representante_id', representantes, contrato ? contrato.representante_id : '', { vazio: 'Selecione o usuário' }), 'usuários ligados à empresa')}
        </div>`,

      partes: `
        <div class="linha-campos">
          ${UI.campo('Comprador *', UI.select('comprador_id', parceiros, contrato ? contrato.comprador_id : '', { obrigatorio: true }))}
          ${UI.campo('Vendedor *', UI.select('vendedor_id', parceiros, contrato ? contrato.vendedor_id : '', { obrigatorio: true }))}
        </div>
        <div class="mini" style="margin-top:10px">
          Os dois precisam estar em Clientes/Fornecedores. Cadastre lá com a busca por CNPJ,
          se for o caso.
        </div>`,

      mercadoria: `
        <div class="linha-campos">
          ${UI.campo('Quantidade', `<input type="number" inputmode="decimal" step="0.001" name="quantidade" value="${v('quantidade', 0)}">`)}
          ${UI.campo('Unidade', UI.select('unidade_id', unidades, contrato ? contrato.unidade_id : '', { vazio: 'Selecione a unidade' }))}
          ${UI.campo('Preço unitário', `<input type="number" inputmode="decimal" step="0.0001" name="preco_unitario" value="${v('preco_unitario', 0)}">`)}
          ${UI.campo('Diferencial', `<input type="number" inputmode="decimal" step="0.0001" name="diferencial" value="${v('diferencial', 0)}">`)}
          ${UI.campo('Valor negociado', `<input type="number" inputmode="decimal" step="0.01" name="valor_total" value="${v('valor_total', 0)}">`, 'calculado; pode ajustar')}
        </div>`,

      corretagem: `
        <div class="linha-campos">
          ${UI.campo('% do comprador', `<input type="number" inputmode="decimal" step="0.0001" name="comissao_comprador_percentual" value="${v('comissao_comprador_percentual', 0)}">`)}
          ${UI.campo('Valor do comprador', `<input type="number" inputmode="decimal" step="0.01" name="comissao_comprador_valor" value="${v('comissao_comprador_valor', 0)}">`)}
          ${UI.campo('% do vendedor', `<input type="number" inputmode="decimal" step="0.0001" name="comissao_vendedor_percentual" value="${v('comissao_vendedor_percentual', 0)}">`)}
          ${UI.campo('Valor do vendedor', `<input type="number" inputmode="decimal" step="0.01" name="comissao_vendedor_valor" value="${v('comissao_vendedor_valor', 0)}">`)}
        </div>
        <div class="mini" style="margin-top:10px">
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
      const comissao = num('comissao_comprador_valor') + num('comissao_vendedor_valor');
      const unidade = Api.unidadesAtivas()
        .find((u) => String(u.id) === campo('unidade_id').value);
      const peso = unidade ? num('quantidade') * Number(unidade.peso_conversao || 0) : 0;
      /* enquanto não há número nenhum o resumo fica fora do caminho */
      corpo.querySelector('#resumo-calculo').classList.toggle('oculto',
        !total && !comissao && !peso);
      corpo.querySelector('#resumo-calculo').innerHTML = `
        <div class="resumo-linha">
          <span>Valor negociado</span><b>${UI.moeda(total)}</b>
        </div>
        <div class="resumo-linha">
          <span>Comissão do comprador</span><b>${UI.moeda(num('comissao_comprador_valor'))}</b>
        </div>
        <div class="resumo-linha">
          <span>Comissão do vendedor</span><b>${UI.moeda(num('comissao_vendedor_valor'))}</b>
        </div>
        <div class="resumo-linha total">
          <span>Total a receber</span>
          <b class="positivo">${UI.moeda(comissao)}
            ${total ? `<small>${UI.numero(comissao / total * 100, 3)}% do contrato</small>` : ''}</b>
        </div>
        ${peso ? `<div class="resumo-linha">
          <span>Peso total</span><b>${UI.numero(peso, 3)} kg
            <small>${UI.numero(unidade.peso_conversao, 3)} kg por ${UI.escapar(unidade.codigo)}</small></b>
        </div>` : ''}`;
    };

    ['quantidade', 'preco_unitario', 'diferencial', 'valor_total',
     'comissao_comprador_percentual', 'comissao_vendedor_percentual',
     'comissao_comprador_valor', 'comissao_vendedor_valor'].forEach((nome) => {
      campo(nome).oninput = () => recalcular(nome);
    });
    campo('unidade_id').onchange = () => recalcular('unidade_id');
    /* o produto pode trazer a unidade e a embalagem padrão */
    campo('produto_id').onchange = (ev) => {
      const produto = Api.produtosAtivos().find((p) => String(p.id) === ev.target.value);
      if (!produto) return;
      if (produto.unidade_id && !campo('unidade_id').value) campo('unidade_id').value = produto.unidade_id;
      if (produto.embalagem && !campo('embalagem').value) campo('embalagem').value = produto.embalagem;
      recalcular('produto_id');
    };
    recalcular();

    /* ------------------------------------------------------- navegação das etapas */
    let atual = 0;
    const ultima = Contratos.ETAPAS.length - 1;

    const validar = (indice) => {
      if (indice === 1) {   // partes
        const c = campo('comprador_id').value;
        const vd = campo('vendedor_id').value;
        if (!c || !vd) { UI.erro('Escolha o comprador e o vendedor.'); return false; }
        if (c === vd) {
          UI.erro('O comprador e o vendedor precisam ser cadastros diferentes.');
          return false;
        }
      }
      return true;
    };

    const salvar = async () => {
      for (let i = 0; i <= ultima; i += 1) {
        if (!validar(i)) { irPara(i); return; }
      }
      const d = UI.lerFormulario(corpo);
      const opcional = (nome) => (d[nome] ? Number(d[nome]) : null);
      const payload = {
        ...d,
        empresa_id: Estado.empresaId,
        numero: (d.numero || '').trim() || null,   // em branco = numeração automática
        comprador_id: Number(d.comprador_id),
        vendedor_id: Number(d.vendedor_id),
        produto_id: opcional('produto_id'),
        modalidade_id: opcional('modalidade_id'),
        unidade_id: opcional('unidade_id'),
        representante_id: opcional('representante_id'),
        conta_contabil_id: opcional('conta_contabil_id'),
        centro_custo_id: opcional('centro_custo_id'),
        operacao_id: opcional('operacao_id'),
      };
      try {
        const salvo = edicao
          ? await Api.put(`/api/contratos/${contrato.id}`, payload)
          : await Api.post('/api/contratos', payload);
        UI.fecharModal();
        UI.sucesso('Contrato salvo.');
        Contratos.ficha(salvo.id);
      } catch (e) {
        UI.erro(e.message);
      }
    };

    const botoes = () => {
      const lista = [];
      if (atual > 0) lista.push({ rotulo: '← Voltar', acao: () => irPara(atual - 1) });
      else lista.push({ rotulo: 'Cancelar', acao: UI.fecharModal });
      if (atual < ultima) {
        lista.push({
          rotulo: 'Próximo →',
          classe: 'btn-primario',
          acao: () => { if (validar(atual)) irPara(atual + 1); },
        });
      } else {
        lista.push({
          rotulo: edicao ? 'Salvar contrato' : 'Salvar e abrir',
          classe: 'btn-primario',
          acao: salvar,
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
      botoes: botoes(),
    });
    irPara(0);
  },

  /* ============================================================ FICHA / AÇÕES */
  async ficha(id) {
    const c = await Api.get(`/api/contratos/${id}`);
    const corpo = document.createElement('div');

    const linha = (rotulo, valor) =>
      `<div><div class="mini">${UI.escapar(rotulo)}</div><div class="forte">${valor || '-'}</div></div>`;

    const recebivel = (r, lado) => {
      if (!r) {
        return `<div class="mini">Comissão ${lado}: nenhuma conta a receber gerada.</div>`;
      }
      return `
        <div class="forma-cartao">
          <div class="forma-topo">
            <div><span class="tag tag-pago">${UI.escapar(lado)}</span>
              <span class="forte"> ${UI.moeda(r.valor)}</span>
              <span class="mini"> em ${r.qtd_parcelas} parcela(s)</span></div>
            <div>${UI.tagStatus(r.status)}</div>
          </div>
          <div class="mini">
            Vencimento ${r.proximo_vencimento ? UI.data(r.proximo_vencimento) : '-'} ·
            recebido ${UI.moeda(r.baixado)} · saldo ${UI.moeda(r.saldo)}
          </div>
        </div>`;
    };

    corpo.innerHTML = `
      <div class="grade g3" style="margin-bottom:14px">
        ${linha('Contrato', UI.escapar(c.numero))}
        ${linha('Data', UI.data(c.data))}
        ${linha('Situação', `<span class="tag ${c.status_tag}">${UI.escapar(c.status_nome)}</span>`)}
        ${linha('Comprador', `${UI.escapar(c.comprador_nome)}<div class="mini">${UI.escapar(c.comprador_documento || '')}</div>`)}
        ${linha('Vendedor', `${UI.escapar(c.vendedor_nome)}<div class="mini">${UI.escapar(c.vendedor_documento || '')}</div>`)}
        ${linha('Representante', UI.escapar(c.representante_nome || c.corretor || ''))}
        ${linha('Mercadoria', `${UI.escapar(c.produto_nome || c.produto || '')}
          <div class="mini">${UI.escapar(c.modalidade_nome || c.modalidade || '')} ${UI.escapar(c.embalagem || '')}</div>`)}
        ${linha('Quantidade', `${UI.numero(c.quantidade, 2)} ${UI.escapar(c.unidade || '')}
          ${c.peso_total ? `<div class="mini">${UI.numero(c.peso_total, 3)} kg no total</div>` : ''}`)}
        ${linha('Preço unitário', UI.moeda(c.preco_unitario))}
        ${linha('Valor negociado', `<span style="font-size:17px">${UI.moeda(c.valor_total)}</span>`)}
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

      <div class="grade g3" style="margin-bottom:16px">
        <div class="kpi"><div class="kpi-rotulo">Comissão do comprador</div>
          <div class="kpi-valor" style="font-size:19px">${UI.moeda(c.comissao_comprador_valor)}</div>
          <div class="kpi-nota">${UI.numero(c.comissao_comprador_percentual, 3)}% do contrato</div></div>
        <div class="kpi"><div class="kpi-rotulo">Comissão do vendedor</div>
          <div class="kpi-valor" style="font-size:19px">${UI.moeda(c.comissao_vendedor_valor)}</div>
          <div class="kpi-nota">${UI.numero(c.comissao_vendedor_percentual, 3)}% do contrato</div></div>
        <div class="kpi destaque-verde"><div class="kpi-rotulo">Total a receber</div>
          <div class="kpi-valor positivo" style="font-size:19px">${UI.moeda(c.comissao_total)}</div>
          <div class="kpi-nota">${UI.numero(c.percentual_total, 3)}% do contrato</div></div>
      </div>

      <h4 class="titulo-bloco">Situação financeira</h4>
      <div class="grade g4" style="margin-bottom:14px">
        <div class="kpi"><div class="kpi-rotulo">Virou conta a receber</div>
          <div class="kpi-valor" style="font-size:17px">${UI.moeda(c.financeiro.gerado)}</div>
          <div class="kpi-nota">${c.financeiro.parcelas} parcela(s)</div></div>
        <div class="kpi destaque-verde"><div class="kpi-rotulo">Recebido</div>
          <div class="kpi-valor positivo" style="font-size:17px">${UI.moeda(c.financeiro.recebido)}</div>
          <div class="kpi-nota">${UI.numero(c.financeiro.recebido_percentual, 1)}% · ${c.financeiro.parcelas_pagas} parcela(s) paga(s)</div></div>
        <div class="kpi destaque-ambar"><div class="kpi-rotulo">Falta receber</div>
          <div class="kpi-valor" style="font-size:17px">${UI.moeda(c.comissao_a_receber)}</div>
          <div class="kpi-nota">${c.financeiro.a_gerar ? `${UI.moeda(c.financeiro.a_gerar)} ainda sem título` : 'tudo lançado'}</div></div>
        <div class="kpi ${c.financeiro.vencido ? 'destaque-vermelho' : ''}"><div class="kpi-rotulo">Vencido</div>
          <div class="kpi-valor ${c.financeiro.vencido ? 'negativo' : ''}" style="font-size:17px">${UI.moeda(c.financeiro.vencido)}</div>
          <div class="kpi-nota">${c.financeiro.dias_atraso ? `${c.financeiro.dias_atraso} dia(s) em atraso` : 'em dia'}</div></div>
      </div>

      <h4 class="titulo-bloco">Contas a receber deste contrato</h4>
      ${recebivel(c.recebivel_comprador, 'do comprador')}
      ${recebivel(c.recebivel_vendedor, 'do vendedor')}
      ${c.status !== 'CANCELADO' && c.financeiro.a_gerar > 0 ? `
        <div class="linha-campos" style="margin-top:12px">
          ${UI.campo('Vencimento', `<input type="date" name="vencimento" value="${(c.data_pagamento || UI.hoje()).slice(0, 10)}">`)}
          ${UI.campo('Parcelas', '<input type="number" name="num_parcelas" min="1" max="36" value="1">')}
          ${UI.campo('Periodicidade', UI.select('periodicidade', [
            { valor: 'MENSAL', rotulo: 'Mensal' }, { valor: 'DIAS', rotulo: 'A cada N dias' },
          ], 'MENSAL', { vazio: false }))}
          ${UI.campo('Intervalo (dias)', '<input type="number" name="intervalo_dias" value="30">')}
        </div>
        <div class="espaco" style="margin-top:10px">
          <label class="mini"><input type="checkbox" name="gerar_comprador" ${c.comissao_comprador_valor ? 'checked' : 'disabled'}> gerar comissão do comprador</label>
          <label class="mini"><input type="checkbox" name="gerar_vendedor" ${c.comissao_vendedor_valor ? 'checked' : 'disabled'}> gerar comissão do vendedor</label>
        </div>` : ''}`;

    const botoes = [
      { rotulo: 'Fechar', acao: () => { UI.fecharModal(); Contratos.tela(); } },
      { rotulo: 'Imprimir', acao: () => Impressao.contrato(c.id) },
    ];

    const temTitulos = Boolean(c.recebivel_comprador || c.recebivel_vendedor);

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
        rotulo: 'Estornar recebíveis',
        classe: 'btn-perigo',
        acao: async () => {
          if (!(await UI.confirmar(
            'Apagar as contas a receber geradas por este contrato? Só é possível se ainda não houver baixa.',
            'Estornar'))) return;
          try {
            await Api.post(`/api/contratos/${c.id}/estornar-recebiveis`);
            UI.sucesso('Contas a receber estornadas.');
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
          rotulo: 'Gerar contas a receber',
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
              });
              UI.sucesso(r.mensagem);
              Contratos.ficha(c.id);
            } catch (e) { UI.erro(e.message); }
          },
        },
      );
    }

    UI.abrirModal({ titulo: `Contrato ${c.numero}`, corpo, largo: true, botoes });
  },
};
