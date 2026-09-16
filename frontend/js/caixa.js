/* Caixa e bancos: saldos, extrato, movimentos avulsos e transferências. */
const Caixa = {
  filtros: { de: '', ate: '', banco_id: '', tipo: '' },

  async tela() {
    const alvo = document.getElementById('pagina');
    const f = Caixa.filtros;
    if (!f.de) { f.de = UI.primeiroDiaMes(); f.ate = UI.ultimoDiaMes(); }

    alvo.innerHTML = `
      <div id="saldos" class="grade g4" style="margin-bottom:18px"></div>
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Livro Caixa / Extrato</h3><div class="mini" id="resumo-extrato"></div></div>
          <div class="espaco">
            <button class="btn" id="btn-transferir">Transferência entre contas</button>
            <button class="btn" id="btn-exportar">Exportar CSV</button>
            <button class="btn btn-verde" id="btn-entrada">+ Entrada</button>
            <button class="btn btn-perigo" id="btn-saida">− Saída</button>
          </div>
        </div>
        <div class="filtros">
          ${UI.campo('Conta', UI.select('banco_id', UI.opcoesBancos(), f.banco_id, { vazio: 'Todas as contas' }))}
          ${UI.campo('De', `<input type="date" name="de" value="${f.de}">`)}
          ${UI.campo('Até', `<input type="date" name="ate" value="${f.ate}">`)}
          ${UI.campo('Tipo', UI.select('tipo', [
            { valor: 'E', rotulo: 'Somente entradas' }, { valor: 'S', rotulo: 'Somente saídas' },
          ], f.tipo, { vazio: 'Entradas e saídas' }))}
          <div class="acoes"><button class="btn btn-primario" id="btn-filtrar">Filtrar</button></div>
        </div>
        <div class="cartao-corpo sem-padding" id="extrato"><div class="vazio">Carregando...</div></div>
      </div>`;

    alvo.querySelector('#btn-filtrar').onclick = () => {
      Object.assign(Caixa.filtros, UI.lerFormulario(alvo.querySelector('.filtros')));
      Caixa.tela();
    };
    alvo.querySelector('#btn-entrada').onclick = () => Caixa.movimento('E');
    alvo.querySelector('#btn-saida').onclick = () => Caixa.movimento('S');
    alvo.querySelector('#btn-transferir').onclick = () => Caixa.transferencia();
    alvo.querySelector('#btn-exportar').onclick = () => UI.exportarTabela('extrato-caixa', '#extrato table');

    const [saldos, extrato] = await Promise.all([
      Api.get('/api/caixa/saldos', { empresa_id: Estado.empresaId }),
      Api.get('/api/caixa/extrato', {
        empresa_id: Estado.empresaId, banco_id: f.banco_id, de: f.de, ate: f.ate, tipo: f.tipo,
      }),
    ]);

    alvo.querySelector('#saldos').innerHTML = `
      <div class="kpi destaque-azul"><div class="kpi-rotulo">Saldo total disponível</div>
        <div class="kpi-valor ${UI.classeValor(saldos.total)}">${UI.moeda(saldos.total)}</div>
        <div class="kpi-nota">${saldos.contas.length} conta(s) ativa(s)</div></div>
      ${saldos.contas.map((c) => `
        <div class="kpi"><div class="kpi-rotulo">${UI.escapar(c.nome)}</div>
          <div class="kpi-valor ${UI.classeValor(c.saldo)}">${UI.moeda(c.saldo)}</div>
          <div class="kpi-nota">${UI.escapar(c.tipo)}${c.conta ? ' · ' + UI.escapar(c.conta) : ''}</div></div>`).join('')}`;

    alvo.querySelector('#resumo-extrato').innerHTML =
      `Saldo anterior ${UI.moeda(extrato.saldo_anterior)} · Entradas <span class="positivo forte">${UI.moeda(extrato.entradas)}</span>
       · Saídas <span class="negativo forte">${UI.moeda(extrato.saidas)}</span> · Saldo final <span class="forte">${UI.moeda(extrato.saldo_final)}</span>`;

    const origens = { BAIXA: 'Baixa de título', AVULSO: 'Avulso', TRANSFERENCIA: 'Transferência' };
    alvo.querySelector('#extrato').innerHTML = UI.tabela({
      colunas: [
        { titulo: 'Data', valor: (m) => UI.data(m.data) },
        { titulo: 'Conta', valor: (m) => UI.escapar(m.banco_nome) },
        { titulo: 'Histórico', valor: (m) => UI.escapar(m.historico) },
        { titulo: 'Origem', valor: (m) => `<span class="mini">${origens[m.origem] || m.origem}</span>` },
        { titulo: 'Classificação', valor: (m) => `<span class="mini">${UI.escapar(m.conta_contabil_codigo ? `${m.conta_contabil_codigo} ${m.conta_contabil_nome}` : '-')}</span>` },
        { titulo: 'C. Custo', valor: (m) => `<span class="mini">${UI.escapar(m.centro_custo_nome || '-')}</span>` },
        { titulo: 'Entrada', classe: 'num', valor: (m) => (m.tipo === 'E' ? `<span class="positivo forte">${UI.moeda(m.valor)}</span>` : '') },
        { titulo: 'Saída', classe: 'num', valor: (m) => (m.tipo === 'S' ? `<span class="negativo forte">${UI.moeda(m.valor)}</span>` : '') },
        { titulo: 'Saldo', classe: 'num', valor: (m) => UI.moeda(m.saldo_acumulado) },
        {
          titulo: '', classe: 'centro',
          valor: (m, i) => (m.origem === 'BAIXA' ? '' : `<button class="btn btn-mini btn-perigo" data-excluir="${i}">Excluir</button>`),
        },
      ],
      linhas: extrato.movimentos,
      rodape: {},
      vazio: 'Nenhum movimento no período.',
    });

    alvo.querySelectorAll('[data-excluir]').forEach((b) => {
      b.onclick = async () => {
        const m = extrato.movimentos[Number(b.dataset.excluir)];
        if (!(await UI.confirmar('Excluir este movimento do caixa?', 'Excluir'))) return;
        try {
          await Api.del(`/api/caixa/movimentos/${m.id}`);
          UI.sucesso('Movimento excluído.');
          Caixa.tela();
        } catch (e) {
          UI.erro(e.message);
        }
      };
    });
  },

  movimento(tipo) {
    const entrada = tipo === 'E';
    const corpo = document.createElement('div');
    corpo.innerHTML = `<div class="linha-campos">
      ${UI.campo('Conta bancária *', UI.select('banco_id', UI.opcoesBancos(), '', { obrigatorio: true }))}
      ${UI.campo('Data', `<input type="date" name="data" value="${UI.hoje()}">`)}
      ${UI.campo('Valor *', '<input type="number" step="0.01" min="0.01" name="valor" placeholder="0,00">')}
      ${UI.campo('Histórico *', '<input name="historico" placeholder="descrição do movimento">', 'aparece no extrato')}
      ${UI.campo('Conta contábil *', UI.select('conta_contabil_id',
        UI.opcoesContas(entrada ? ['RECEITA', 'PASSIVO', 'PATRIMONIO_LIQUIDO'] : ['DESPESA', 'CUSTO', 'ATIVO', 'PASSIVO']),
        '', { obrigatorio: true }), entrada ? 'de onde veio o dinheiro' : 'para onde foi o dinheiro')}
      ${UI.campo('Centro de custo', UI.select('centro_custo_id', UI.opcoesCentros(), '', { vazio: 'Não informado' }))}
      ${UI.campo('Operação', UI.select('operacao_id', UI.opcoesOperacoes(entrada ? 'ENTRADA' : 'SAIDA'), '', { vazio: 'Não informada' }))}
      ${UI.campo('Cliente/Fornecedor', UI.select('parceiro_id', UI.opcoesParceiros(), '', { vazio: 'Não informado' }))}
      ${UI.campo('Documento', '<input name="documento">')}
    </div>
    <div class="mini" style="margin-top:12px">
      Movimento avulso não gera título em contas a ${entrada ? 'receber' : 'pagar'} — use para tarifas,
      aportes, resgates e demais lançamentos diretos no caixa.
    </div>`;

    UI.abrirModal({
      titulo: entrada ? 'Entrada no caixa' : 'Saída do caixa',
      corpo,
      botoes: [
        { rotulo: 'Cancelar', acao: UI.fecharModal },
        {
          rotulo: 'Lançar',
          classe: entrada ? 'btn-verde' : 'btn-primario',
          acao: async () => {
            const d = UI.lerFormulario(corpo);
            if (!d.banco_id || !d.valor || !d.historico || !d.conta_contabil_id) {
              return UI.erro('Preencha conta bancária, valor, histórico e conta contábil.');
            }
            try {
              await Api.post('/api/caixa/movimentos', {
                empresa_id: Estado.empresaId,
                banco_id: Number(d.banco_id),
                data: d.data,
                tipo,
                valor: Number(d.valor),
                historico: d.historico,
                conta_contabil_id: Number(d.conta_contabil_id),
                centro_custo_id: d.centro_custo_id ? Number(d.centro_custo_id) : null,
                operacao_id: d.operacao_id ? Number(d.operacao_id) : null,
                parceiro_id: d.parceiro_id ? Number(d.parceiro_id) : null,
                documento: d.documento,
              });
              UI.fecharModal();
              UI.sucesso('Movimento lançado.');
              Caixa.tela();
            } catch (e) {
              UI.erro(e.message);
            }
          },
        },
      ],
    });
  },

  transferencia() {
    const corpo = document.createElement('div');
    corpo.innerHTML = `<div class="linha-campos">
      ${UI.campo('Conta de origem *', UI.select('banco_origem_id', UI.opcoesBancos(), '', { obrigatorio: true }))}
      ${UI.campo('Conta de destino *', UI.select('banco_destino_id', UI.opcoesBancos(), '', { obrigatorio: true }))}
      ${UI.campo('Data', `<input type="date" name="data" value="${UI.hoje()}">`)}
      ${UI.campo('Valor *', '<input type="number" step="0.01" min="0.01" name="valor">')}
      ${UI.campo('Histórico', '<input name="historico" placeholder="ex.: suprimento de caixa">')}
    </div>`;

    UI.abrirModal({
      titulo: 'Transferência entre contas',
      corpo,
      botoes: [
        { rotulo: 'Cancelar', acao: UI.fecharModal },
        {
          rotulo: 'Transferir',
          classe: 'btn-primario',
          acao: async () => {
            const d = UI.lerFormulario(corpo);
            if (!d.banco_origem_id || !d.banco_destino_id || !d.valor) {
              return UI.erro('Preencha as contas e o valor.');
            }
            try {
              await Api.post('/api/caixa/transferencias', {
                empresa_id: Estado.empresaId,
                banco_origem_id: Number(d.banco_origem_id),
                banco_destino_id: Number(d.banco_destino_id),
                data: d.data,
                valor: Number(d.valor),
                historico: d.historico,
              });
              UI.fecharModal();
              UI.sucesso('Transferência realizada.');
              Caixa.tela();
            } catch (e) {
              UI.erro(e.message);
            }
          },
        },
      ],
    });
  },
};
