/* Painel e relatórios: títulos, fluxo de caixa, classificações, razão, DRE e balancete. */
const Relatorios = {
  abaAtual: 'dre',

  /* ==================================================================== PAINEL */
  async painel() {
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando painel...</div></div>';
    const d = await Api.get('/api/relatorios/dashboard', { empresa_id: Estado.empresaId });
    const t = d.titulos;

    alvo.innerHTML = `
      <div class="grade g4" style="margin-bottom:18px">
        <div class="kpi destaque-azul">
          <div class="kpi-rotulo">Saldo disponível</div>
          <div class="kpi-valor ${UI.classeValor(d.saldo_disponivel)}">${UI.moeda(d.saldo_disponivel)}</div>
          <div class="kpi-nota">soma de bancos e caixa em ${UI.data(d.data)}</div>
        </div>
        <div class="kpi destaque-verde">
          <div class="kpi-rotulo">A receber</div>
          <div class="kpi-valor positivo">${UI.moeda(t.receber_total)}</div>
          <div class="kpi-nota">vencido ${UI.moeda(t.receber_vencido)} · este mês ${UI.moeda(t.receber_mes)}</div>
        </div>
        <div class="kpi destaque-vermelho">
          <div class="kpi-rotulo">A pagar</div>
          <div class="kpi-valor negativo">${UI.moeda(t.pagar_total)}</div>
          <div class="kpi-nota">vencido ${UI.moeda(t.pagar_vencido)} · este mês ${UI.moeda(t.pagar_mes)}</div>
        </div>
        <div class="kpi destaque-ambar">
          <div class="kpi-rotulo">Previsão de saldo</div>
          <div class="kpi-valor ${UI.classeValor(d.saldo_disponivel + t.receber_total - t.pagar_total)}">
            ${UI.moeda(d.saldo_disponivel + t.receber_total - t.pagar_total)}</div>
          <div class="kpi-nota">saldo + a receber − a pagar</div>
        </div>
      </div>

      <div class="grade g2">
        <div class="cartao">
          <div class="cartao-cabecalho"><h3>Movimento do mês (caixa)</h3></div>
          <div class="cartao-corpo">
            <div class="grade g3" style="margin-bottom:14px">
              <div><div class="kpi-rotulo">Entradas</div><div class="kpi-valor positivo" style="font-size:19px">${UI.moeda(d.mes.entradas)}</div></div>
              <div><div class="kpi-rotulo">Saídas</div><div class="kpi-valor negativo" style="font-size:19px">${UI.moeda(d.mes.saidas)}</div></div>
              <div><div class="kpi-rotulo">Resultado</div><div class="kpi-valor ${UI.classeValor(d.mes.resultado_caixa)}" style="font-size:19px">${UI.moeda(d.mes.resultado_caixa)}</div></div>
            </div>
            ${UI.graficoBarras(d.evolucao)}
          </div>
        </div>

        <div class="cartao">
          <div class="cartao-cabecalho"><h3>Resultado do mês (competência)</h3></div>
          <div class="cartao-corpo">
            <div class="grade g2" style="margin-bottom:14px">
              <div><div class="kpi-rotulo">Receita bruta</div><div class="kpi-valor positivo" style="font-size:19px">${UI.moeda(d.mes.receita_competencia)}</div></div>
              <div><div class="kpi-rotulo">Resultado líquido</div><div class="kpi-valor ${UI.classeValor(d.mes.resultado_competencia)}" style="font-size:19px">${UI.moeda(d.mes.resultado_competencia)}</div></div>
            </div>
            <h4 style="margin:6px 0 8px;font-size:13px">Saldo por conta</h4>
            ${UI.tabela({
              colunas: [
                { titulo: 'Conta', valor: (c) => UI.escapar(c.nome) },
                { titulo: 'Tipo', valor: (c) => UI.escapar(c.tipo) },
                { titulo: 'Saldo', classe: 'num', valor: (c) => `<span class="${UI.classeValor(c.saldo)} forte">${UI.moeda(c.saldo)}</span>` },
              ],
              linhas: d.contas,
              vazio: 'Nenhuma conta bancária cadastrada.',
            })}
          </div>
        </div>
      </div>

      <div class="cartao">
        <div class="cartao-cabecalho"><h3>Atalhos</h3></div>
        <div class="cartao-corpo espaco">
          <button class="btn btn-verde" id="atalho-receber">+ Novo título a receber</button>
          <button class="btn btn-primario" id="atalho-pagar">+ Novo título a pagar</button>
          <button class="btn" id="atalho-caixa">Lançar no caixa</button>
          <button class="btn" id="atalho-dre">Ver DRE do mês</button>
        </div>
      </div>`;

    alvo.querySelector('#atalho-receber').onclick = () => Lancamentos.formulario('RECEBER');
    alvo.querySelector('#atalho-pagar').onclick = () => Lancamentos.formulario('PAGAR');
    alvo.querySelector('#atalho-caixa').onclick = () => { location.hash = '#/caixa'; };
    alvo.querySelector('#atalho-dre').onclick = () => {
      Relatorios.abaAtual = 'dre';
      location.hash = '#/relatorios';
    };
  },

  /* ================================================================ RELATÓRIOS */
  abas: [
    { id: 'dre', rotulo: 'DRE' },
    { id: 'balancete', rotulo: 'Balancete' },
    { id: 'receber', rotulo: 'Contas a receber' },
    { id: 'pagar', rotulo: 'Contas a pagar' },
    { id: 'fluxo', rotulo: 'Fluxo de caixa' },
    { id: 'contratos', rotulo: 'Contratos' },
    { id: 'centro', rotulo: 'Por centro de custo' },
    { id: 'conta', rotulo: 'Por conta contábil' },
    { id: 'operacao', rotulo: 'Por operação' },
    { id: 'parceiro', rotulo: 'Por cliente/fornecedor' },
    { id: 'razao', rotulo: 'Razão contábil' },
  ],

  async tela() {
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = `
      <div class="abas">${Relatorios.abas
        .map((a) => `<button class="aba ${a.id === Relatorios.abaAtual ? 'ativa' : ''}" data-aba="${a.id}">${a.rotulo}</button>`)
        .join('')}</div>
      <div id="area-relatorio"></div>`;

    alvo.querySelectorAll('[data-aba]').forEach((b) => {
      b.onclick = () => { Relatorios.abaAtual = b.dataset.aba; Relatorios.tela(); };
    });
    await Relatorios.desenhar();
  },

  cabecalhoPeriodo(extra = '') {
    const p = Relatorios.periodo || (Relatorios.periodo = { de: UI.primeiroDiaMes(), ate: UI.ultimoDiaMes() });
    return `<div class="filtros">
      ${UI.campo('De', `<input type="date" name="de" value="${p.de}">`)}
      ${UI.campo('Até', `<input type="date" name="ate" value="${p.ate}">`)}
      ${extra}
      <div class="acoes">
        <button class="btn btn-primario" id="btn-gerar">Gerar</button>
        <button class="btn" id="btn-exportar">CSV</button>
        <button class="btn" id="btn-imprimir">Imprimir</button>
      </div>
    </div>`;
  },

  ligarFiltros(nomeArquivo) {
    const alvo = document.getElementById('area-relatorio');
    const btn = alvo.querySelector('#btn-gerar');
    if (btn) {
      btn.onclick = () => {
        const d = UI.lerFormulario(alvo.querySelector('.filtros'));
        Relatorios.periodo = { de: d.de, ate: d.ate };
        Relatorios.opcoes = d;
        Relatorios.desenhar();
      };
    }
    const exportar = alvo.querySelector('#btn-exportar');
    if (exportar) exportar.onclick = () => UI.exportarTabela(nomeArquivo, '#area-relatorio table');
    const imprimir = alvo.querySelector('#btn-imprimir');
    if (imprimir) imprimir.onclick = UI.imprimir;
  },

  async desenhar() {
    const area = document.getElementById('area-relatorio');
    area.innerHTML = '<div class="cartao"><div class="vazio">Gerando relatório...</div></div>';
    const mapa = {
      dre: Relatorios.dre, balancete: Relatorios.balancete,
      receber: () => Relatorios.titulos('RECEBER'), pagar: () => Relatorios.titulos('PAGAR'),
      fluxo: Relatorios.fluxo,
      contratos: Relatorios.contratos,
      centro: () => Relatorios.classificacao('centro_custo', 'Centro de custo'),
      conta: () => Relatorios.classificacao('conta', 'Conta contábil'),
      operacao: () => Relatorios.classificacao('operacao', 'Operação'),
      parceiro: () => Relatorios.classificacao('parceiro', 'Cliente/Fornecedor'),
      razao: Relatorios.razao,
    };
    try {
      await mapa[Relatorios.abaAtual]();
    } catch (e) {
      area.innerHTML = `<div class="cartao"><div class="vazio">${UI.escapar(e.message)}</div></div>`;
    }
  },

  /* ------------------------------------------------------------------- DRE */
  async dre() {
    const p = Relatorios.periodo || { de: UI.primeiroDiaMes(), ate: UI.ultimoDiaMes() };
    const o = Relatorios.opcoes || {};
    const dados = await Api.get('/api/relatorios/dre', {
      empresa_id: Estado.empresaId, de: p.de, ate: p.ate,
      regime: o.regime || 'competencia',
      centro_custo_id: o.centro_custo_id || '',
      comparar_anterior: o.comparar_anterior ? 'true' : 'false',
    });

    const linhas = dados.linhas.map((l) => {
      const classe = l.tipo === 'subtotal' ? 'subtotal' : '';
      const detalhe = (l.contas || []).map((c) => `
        <tr><td class="recuo-2 mini">${UI.escapar(c.codigo)} — ${UI.escapar(c.nome)}</td>
        <td class="num mini">${UI.moeda(Math.abs(c.valor))}</td>
        <td class="num mini">${dados.receita_bruta ? UI.numero(Math.abs(c.valor) / dados.receita_bruta * 100) + '%' : '-'}</td>
        ${o.comparar_anterior ? '<td class="num mini"></td>' : ''}</tr>`).join('');
      return `
        <tr class="${classe}">
          <td class="${l.tipo === 'grupo' ? 'recuo-1' : 'forte'}">${UI.escapar(l.descricao)}</td>
          <td class="num ${UI.classeValor(l.valor)} forte">${UI.moeda(l.valor)}</td>
          <td class="num">${UI.numero(l.percentual)}%</td>
          ${o.comparar_anterior ? `<td class="num ${UI.classeValor(l.valor_anterior)}">${UI.moeda(l.valor_anterior)}</td>` : ''}
        </tr>${detalhe}`;
    }).join('');

    document.getElementById('area-relatorio').innerHTML = `
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Demonstração do Resultado do Exercício (DRE)</h3>
            <div class="mini">Período de ${UI.data(p.de)} a ${UI.data(p.ate)} — regime de ${dados.periodo.regime === 'caixa' ? 'caixa' : 'competência'}</div></div>
          <div class="espaco">
            <span class="mini">Margem líquida</span>
            <span class="kpi-valor ${UI.classeValor(dados.margem)}" style="font-size:19px">${UI.numero(dados.margem)}%</span>
          </div>
        </div>
        ${Relatorios.cabecalhoPeriodo(`
          ${UI.campo('Regime', UI.select('regime', [
            { valor: 'competencia', rotulo: 'Competência' }, { valor: 'caixa', rotulo: 'Caixa' },
          ], o.regime || 'competencia', { vazio: false }))}
          ${UI.campo('Centro de custo', UI.select('centro_custo_id', UI.opcoesCentros(), o.centro_custo_id || '', { vazio: 'Todos' }))}
          ${UI.campo('Comparar', `<span><input type="checkbox" name="comparar_anterior" ${o.comparar_anterior ? 'checked' : ''}> período anterior</span>`)}
        `)}
        <div class="cartao-corpo sem-padding">
          <div class="tabela-wrap"><table>
            <thead><tr><th>Descrição</th><th class="num">Valor</th><th class="num">% RB</th>
              ${o.comparar_anterior ? '<th class="num">Período anterior</th>' : ''}</tr></thead>
            <tbody>${linhas || '<tr><td colspan="4" class="vazio">Sem movimento no período.</td></tr>'}</tbody>
          </table></div>
        </div>
      </div>`;
    Relatorios.ligarFiltros('dre');
  },

  /* ------------------------------------------------------------- BALANCETE */
  async balancete() {
    const p = Relatorios.periodo || { de: UI.primeiroDiaMes(), ate: UI.ultimoDiaMes() };
    const o = Relatorios.opcoes || {};
    const dados = await Api.get('/api/relatorios/balancete', {
      empresa_id: Estado.empresaId, de: p.de, ate: p.ate,
      incluir_sinteticas: o.incluir_sinteticas === false ? 'false' : 'true',
      ocultar_zerados: o.ocultar_zerados === false ? 'false' : 'true',
    });

    const linhas = dados.linhas.map((l) => `
      <tr class="${l.analitica ? '' : 'grupo'}">
        <td style="padding-left:${(l.nivel - 1) * 16 + 12}px">${UI.escapar(l.codigo)}</td>
        <td>${UI.escapar(l.nome)}</td>
        <td class="num">${UI.moeda(l.saldo_anterior)} ${l.saldo_anterior ? l.saldo_anterior_dc : ''}</td>
        <td class="num">${UI.moeda(l.debitos, false)}</td>
        <td class="num">${UI.moeda(l.creditos, false)}</td>
        <td class="num forte">${UI.moeda(l.saldo_final)} ${l.saldo_final ? l.saldo_final_dc : ''}</td>
      </tr>`).join('');

    const t = dados.totais;
    document.getElementById('area-relatorio').innerHTML = `
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Balancete de Verificação</h3>
            <div class="mini">Movimento de ${UI.data(p.de)} a ${UI.data(p.ate)}</div></div>
        </div>
        ${Relatorios.cabecalhoPeriodo(`
          ${UI.campo('Sintéticas', `<span><input type="checkbox" name="incluir_sinteticas" ${o.incluir_sinteticas === false ? '' : 'checked'}> mostrar totalizadoras</span>`)}
          ${UI.campo('Zerados', `<span><input type="checkbox" name="ocultar_zerados" ${o.ocultar_zerados === false ? '' : 'checked'}> ocultar contas sem saldo</span>`)}
        `)}
        <div class="cartao-corpo">
          <div class="${t.fecha ? 'ok-caixa' : 'aviso-caixa'}">
            ${t.fecha
              ? `Balancete fechado: total de débitos e créditos igual a ${UI.moeda(t.debitos)}.`
              : `Atenção: diferença de ${UI.moeda(t.diferenca)} entre débitos (${UI.moeda(t.debitos)}) e créditos (${UI.moeda(t.creditos)}).`}
          </div>
        </div>
        <div class="cartao-corpo sem-padding">
          <div class="tabela-wrap"><table>
            <thead><tr><th>Código</th><th>Conta</th><th class="num">Saldo anterior</th>
              <th class="num">Débitos</th><th class="num">Créditos</th><th class="num">Saldo atual</th></tr></thead>
            <tbody>${linhas || '<tr><td colspan="6" class="vazio">Sem movimento no período.</td></tr>'}</tbody>
            <tfoot><tr><td colspan="3">TOTAIS DO PERÍODO</td>
              <td class="num">${UI.moeda(t.debitos)}</td><td class="num">${UI.moeda(t.creditos)}</td><td></td></tr></tfoot>
          </table></div>
        </div>
      </div>`;
    Relatorios.ligarFiltros('balancete');
  },

  /* --------------------------------------------------------------- TÍTULOS */
  async titulos(tipo) {
    const p = Relatorios.periodo || { de: UI.primeiroDiaMes(), ate: UI.ultimoDiaMes() };
    const o = Relatorios.opcoes || {};
    const dados = await Api.get('/api/relatorios/titulos', {
      empresa_id: Estado.empresaId, tipo, de: p.de, ate: p.ate,
      situacao: o.situacao || 'ABERTAS', base_data: o.base_data || 'vencimento',
      parceiro_id: o.parceiro_id || '', centro_custo_id: o.centro_custo_id || '',
      conta_contabil_id: o.conta_contabil_id || '',
    });

    const t = dados.totais;
    document.getElementById('area-relatorio').innerHTML = `
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>${tipo === 'RECEBER' ? 'Contas a Receber' : 'Contas a Pagar'} — analítico</h3>
            <div class="mini">${t.quantidade} título(s) — valor ${UI.moeda(t.valor)} · baixado ${UI.moeda(t.baixado)} · saldo ${UI.moeda(t.saldo)}</div></div>
        </div>
        ${Relatorios.cabecalhoPeriodo(`
          ${UI.campo('Situação', UI.select('situacao', [
            { valor: 'ABERTAS', rotulo: 'Em aberto' }, { valor: 'VENCIDAS', rotulo: 'Vencidas' },
            { valor: 'PAGAS', rotulo: 'Baixadas' }, { valor: 'TODAS', rotulo: 'Todas' },
          ], o.situacao || 'ABERTAS', { vazio: false }))}
          ${UI.campo('Data base', UI.select('base_data', [
            { valor: 'vencimento', rotulo: 'Vencimento' }, { valor: 'emissao', rotulo: 'Emissão' },
            { valor: 'competencia', rotulo: 'Competência' }, { valor: 'pagamento', rotulo: 'Pagamento' },
          ], o.base_data || 'vencimento', { vazio: false }))}
          ${UI.campo('Cliente/Fornecedor', UI.select('parceiro_id', UI.opcoesParceiros(), o.parceiro_id || '', { vazio: 'Todos' }))}
          ${UI.campo('Centro de custo', UI.select('centro_custo_id', UI.opcoesCentros(), o.centro_custo_id || '', { vazio: 'Todos' }))}
        `)}
        ${dados.aging.length ? `<div class="cartao-corpo">
          <div class="grade g4">${dados.aging.map((a) => `
            <div class="kpi"><div class="kpi-rotulo">${UI.escapar(a.faixa)}</div>
              <div class="kpi-valor" style="font-size:18px">${UI.moeda(a.valor)}</div></div>`).join('')}</div>
        </div>` : ''}
        <div class="cartao-corpo sem-padding">
          ${UI.tabela({
            colunas: [
              { titulo: 'Vencimento', valor: (l) => UI.data(l.vencimento) },
              { titulo: 'Documento', valor: (l) => UI.escapar(l.documento || '-') },
              { titulo: 'Cliente/Fornecedor', valor: (l) => UI.escapar(l.parceiro) },
              { titulo: 'Descrição', valor: (l) => UI.escapar(l.descricao) },
              { titulo: 'Parc.', classe: 'centro', valor: (l) => l.parcela },
              { titulo: 'Classificação', valor: (l) => `<span class="mini">${UI.escapar(l.classificacao || '-')}</span>` },
              { titulo: 'C. custo', valor: (l) => `<span class="mini">${UI.escapar(l.centro_custo || '-')}</span>` },
              { titulo: 'Valor', classe: 'num', valor: (l) => UI.moeda(l.valor) },
              { titulo: 'Baixado', classe: 'num', valor: (l) => UI.moeda(l.baixado, false) },
              { titulo: 'Saldo', classe: 'num', valor: (l) => `<span class="forte">${UI.moeda(l.saldo)}</span>` },
              { titulo: 'Atraso', classe: 'centro', valor: (l) => (l.dias_atraso ? `<span class="negativo">${l.dias_atraso}d</span>` : '-') },
              { titulo: 'Situação', classe: 'centro', valor: (l) => UI.tagStatus(l.status, l.dias_atraso > 0) },
            ],
            linhas: dados.linhas,
            rodape: { },
            vazio: 'Nenhum título encontrado no período.',
          })}
        </div>
      </div>`;
    Relatorios.ligarFiltros(tipo === 'RECEBER' ? 'contas-a-receber' : 'contas-a-pagar');
  },

  /* -------------------------------------------------- CONTRATOS × FINANCEIRO */
  async contratos() {
    const p = Relatorios.periodo || { de: UI.primeiroDiaMes(), ate: UI.ultimoDiaMes() };
    const o = Relatorios.opcoes || {};
    const dados = await Api.get('/api/relatorios/contratos', {
      empresa_id: Estado.empresaId, de: p.de, ate: p.ate,
      status: o.status || '', parceiro_id: o.parceiro_id || '',
      representante_id: o.representante_id || '',
      agrupar_por: o.agrupar_por || 'status',
    });
    const t = dados.totais;
    const opcoesStatus = dados.status.map((s) => ({ valor: s.codigo, rotulo: s.nome }));

    document.getElementById('area-relatorio').innerHTML = `
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Contratos × financeiro</h3>
            <div class="mini">${t.quantidade} contrato(s) — comissão ${UI.moeda(t.comissao_total)} ·
              recebido ${UI.moeda(t.comissao_recebida)} · a receber ${UI.moeda(t.comissao_a_receber)}</div></div>
        </div>
        ${Relatorios.cabecalhoPeriodo(`
          ${UI.campo('Situação', UI.select('status', opcoesStatus, o.status || '', { vazio: 'Todas' }))}
          ${UI.campo('Cliente/Fornecedor', UI.select('parceiro_id', UI.opcoesParceiros(), o.parceiro_id || '', { vazio: 'Todos' }))}
          ${UI.campo('Representante', UI.select('representante_id',
            Api.representantes().map((u) => ({ valor: u.id, rotulo: u.nome })),
            o.representante_id || '', { vazio: 'Todos' }))}
          ${UI.campo('Agrupar por', UI.select('agrupar_por', [
            { valor: 'status', rotulo: 'Situação' },
            { valor: 'parceiro', rotulo: 'Comprador' },
            { valor: 'representante', rotulo: 'Representante' },
            { valor: 'produto', rotulo: 'Produto' },
            { valor: 'mes', rotulo: 'Mês' },
          ], o.agrupar_por || 'status', { vazio: false }))}
        `)}

        <div class="cartao-corpo">
          <div class="grade g4">
            <div class="kpi destaque-azul"><div class="kpi-rotulo">Comissão do período</div>
              <div class="kpi-valor" style="font-size:20px">${UI.moeda(t.comissao_total)}</div>
              <div class="kpi-nota">${t.quantidade} contrato(s) · ${UI.moeda(t.valor_total)} negociados</div></div>
            <div class="kpi destaque-verde"><div class="kpi-rotulo">Já recebido</div>
              <div class="kpi-valor positivo" style="font-size:20px">${UI.moeda(t.comissao_recebida)}</div>
              <div class="kpi-nota">${UI.numero(t.recebido_percentual, 1)}% da comissão</div></div>
            <div class="kpi destaque-ambar"><div class="kpi-rotulo">A receber</div>
              <div class="kpi-valor" style="font-size:20px">${UI.moeda(t.comissao_a_receber)}</div>
              <div class="kpi-nota">inclui o que ainda não virou título</div></div>
            <div class="kpi destaque-vermelho"><div class="kpi-rotulo">Vencido</div>
              <div class="kpi-valor negativo" style="font-size:20px">${UI.moeda(t.comissao_vencida)}</div>
              <div class="kpi-nota">${t.em_atraso} contrato(s) com parcela em atraso</div></div>
          </div>
        </div>

        <div class="cartao-corpo sem-padding">
          ${UI.tabela({
            colunas: [
              { titulo: Relatorios.ROTULO_GRUPO[o.agrupar_por || 'status'] || 'Situação',
                valor: (g) => `<span class="forte">${UI.escapar(g.nome)}</span>` },
              { titulo: 'Contratos', classe: 'centro', valor: (g) => g.quantidade },
              { titulo: 'Valor negociado', classe: 'num', valor: (g) => UI.moeda(g.valor_total) },
              { titulo: 'Comissão', classe: 'num', valor: (g) => UI.moeda(g.comissao_total) },
              { titulo: 'Recebido', classe: 'num', valor: (g) => `<span class="positivo">${UI.moeda(g.comissao_recebida, false) || '-'}</span>` },
              { titulo: 'A receber', classe: 'num', valor: (g) => UI.moeda(g.comissao_a_receber, false) || '-' },
              { titulo: 'Vencido', classe: 'num', valor: (g) => (g.comissao_vencida ? `<span class="negativo">${UI.moeda(g.comissao_vencida)}</span>` : '-') },
            ],
            linhas: dados.resumo,
            vazio: 'Nenhum contrato no período.',
          })}
        </div>
      </div>

      <div class="cartao" style="margin-top:18px">
        <div class="cartao-cabecalho">
          <div><h3>Contrato a contrato</h3>
            <div class="mini">clique no número para abrir a ficha do contrato</div></div>
        </div>
        <div class="cartao-corpo sem-padding" id="lista-contratos-relatorio">
          ${UI.tabela({
            colunas: [
              { titulo: 'Contrato', valor: (l, i) => `<button class="btn-link-tabela" data-abrir="${i}">${UI.escapar(l.numero)}</button>
                  <div class="mini">${UI.data(l.data)}</div>` },
              { titulo: 'Comprador', valor: (l) => UI.escapar(l.comprador_nome) },
              { titulo: 'Vendedor', valor: (l) => UI.escapar(l.vendedor_nome) },
              { titulo: 'Mercadoria', valor: (l) => `${UI.escapar(l.produto_nome || l.produto || '-')}
                  <div class="mini">${UI.numero(l.quantidade)} ${UI.escapar(l.unidade || '')}</div>` },
              { titulo: 'Representante', valor: (l) => `<span class="mini">${UI.escapar(l.representante_nome || '-')}</span>` },
              { titulo: 'Negociado', classe: 'num', valor: (l) => UI.moeda(l.valor_total) },
              { titulo: 'Comissão', classe: 'num', valor: (l) => `<span class="forte">${UI.moeda(l.comissao_total)}</span>` },
              { titulo: 'Recebido', classe: 'num', valor: (l) => `<span class="positivo">${UI.moeda(l.comissao_recebida, false) || '-'}</span>
                  ${l.comissao_recebida ? `<div class="mini">${UI.numero(l.financeiro.recebido_percentual, 0)}% da comissão</div>` : ''}` },
              { titulo: 'A receber', classe: 'num', valor: (l) => UI.moeda(l.comissao_a_receber, false) || '-' },
              { titulo: 'Vencimento', classe: 'centro', valor: (l) => (l.financeiro.proximo_vencimento
                  ? `${UI.data(l.financeiro.proximo_vencimento)}
                     ${l.financeiro.dias_atraso ? `<div class="mini negativo">${l.financeiro.dias_atraso} dia(s) em atraso</div>` : ''}`
                  : '-') },
              { titulo: 'Situação', classe: 'centro',
                valor: (l) => `<span class="tag ${l.status_tag}">${UI.escapar(l.status_nome)}</span>` },
            ],
            linhas: dados.linhas,
            vazio: 'Nenhum contrato no período.',
          })}
        </div>
      </div>`;

    document.querySelectorAll('[data-abrir]').forEach((b) => {
      b.onclick = () => Contratos.ficha(dados.linhas[Number(b.dataset.abrir)].id);
    });
    Relatorios.ligarFiltros('contratos');
  },

  ROTULO_GRUPO: {
    status: 'Situação', parceiro: 'Comprador', representante: 'Representante',
    produto: 'Produto', mes: 'Mês',
  },

  /* ---------------------------------------------------------- FLUXO DE CAIXA */
  async fluxo() {
    const p = Relatorios.periodo || { de: UI.primeiroDiaMes(), ate: UI.ultimoDiaMes() };
    const o = Relatorios.opcoes || {};
    const dados = await Api.get('/api/relatorios/fluxo-caixa', {
      empresa_id: Estado.empresaId, de: p.de, ate: p.ate,
      agrupar: o.agrupar || 'dia', banco_id: o.banco_id || '',
      incluir_previsto: o.incluir_previsto ? 'true' : 'false',
    });
    const t = dados.totais;
    const prev = Boolean(o.incluir_previsto);

    document.getElementById('area-relatorio').innerHTML = `
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Fluxo de Caixa</h3>
            <div class="mini">Saldo anterior ${UI.moeda(dados.saldo_anterior)} · entradas ${UI.moeda(t.entradas)} · saídas ${UI.moeda(t.saidas)} · saldo final ${UI.moeda(t.saldo_final)}</div></div>
        </div>
        ${Relatorios.cabecalhoPeriodo(`
          ${UI.campo('Agrupar por', UI.select('agrupar', [
            { valor: 'dia', rotulo: 'Dia' }, { valor: 'mes', rotulo: 'Mês' },
          ], o.agrupar || 'dia', { vazio: false }))}
          ${UI.campo('Conta', UI.select('banco_id', UI.opcoesBancos(), o.banco_id || '', { vazio: 'Todas' }))}
          ${UI.campo('Projeção', `<span><input type="checkbox" name="incluir_previsto" ${prev ? 'checked' : ''}> incluir títulos em aberto</span>`)}
        `)}
        <div class="cartao-corpo sem-padding">
          ${UI.tabela({
            colunas: [
              { titulo: 'Período', valor: (l) => (l.periodo.length === 7 ? l.periodo.split('-').reverse().join('/') : UI.data(l.periodo)) },
              { titulo: 'Entradas', classe: 'num', valor: (l) => `<span class="positivo">${UI.moeda(l.entradas, false)}</span>` },
              { titulo: 'Saídas', classe: 'num', valor: (l) => `<span class="negativo">${UI.moeda(l.saidas, false)}</span>` },
              { titulo: 'Resultado', classe: 'num', valor: (l) => `<span class="${UI.classeValor(l.resultado)}">${UI.moeda(l.resultado)}</span>` },
              { titulo: 'Saldo', classe: 'num', valor: (l) => `<span class="forte">${UI.moeda(l.saldo)}</span>` },
              ...(prev ? [
                { titulo: 'Prev. entradas', classe: 'num', valor: (l) => UI.moeda(l.previsto_entradas, false) },
                { titulo: 'Prev. saídas', classe: 'num', valor: (l) => UI.moeda(l.previsto_saidas, false) },
                { titulo: 'Saldo projetado', classe: 'num', valor: (l) => `<span class="${UI.classeValor(l.saldo_projetado)} forte">${UI.moeda(l.saldo_projetado)}</span>` },
              ] : []),
            ],
            linhas: dados.linhas,
            vazio: 'Sem movimento no período.',
          })}
        </div>
      </div>`;
    Relatorios.ligarFiltros('fluxo-de-caixa');
  },

  /* -------------------------------------------------------- POR CLASSIFICAÇÃO */
  async classificacao(agrupar, rotulo) {
    const p = Relatorios.periodo || { de: UI.primeiroDiaMes(), ate: UI.ultimoDiaMes() };
    const o = Relatorios.opcoes || {};
    const dados = await Api.get('/api/relatorios/por-classificacao', {
      empresa_id: Estado.empresaId, agrupar_por: agrupar, de: p.de, ate: p.ate,
      regime: o.regime || 'competencia', natureza: o.natureza || '',
    });
    const t = dados.totais;
    const maior = Math.max(1, ...dados.linhas.map((l) => Math.max(l.receitas, l.despesas)));

    document.getElementById('area-relatorio').innerHTML = `
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Movimento por ${UI.escapar(rotulo)}</h3>
            <div class="mini">Receitas ${UI.moeda(t.receitas)} · despesas ${UI.moeda(t.despesas)} · resultado ${UI.moeda(t.resultado)}</div></div>
        </div>
        ${Relatorios.cabecalhoPeriodo(`
          ${UI.campo('Regime', UI.select('regime', [
            { valor: 'competencia', rotulo: 'Competência' }, { valor: 'caixa', rotulo: 'Caixa' },
          ], o.regime || 'competencia', { vazio: false }))}
          ${UI.campo('Mostrar', UI.select('natureza', [
            { valor: 'RECEITA', rotulo: 'Somente receitas' }, { valor: 'DESPESA', rotulo: 'Somente despesas' },
          ], o.natureza || '', { vazio: 'Receitas e despesas' }))}
        `)}
        <div class="cartao-corpo sem-padding">
          ${UI.tabela({
            colunas: [
              { titulo: 'Código', valor: (l) => UI.escapar(l.codigo) },
              { titulo: rotulo, valor: (l) => UI.escapar(l.nome) },
              { titulo: 'Receitas', classe: 'num', valor: (l) => `<span class="positivo">${UI.moeda(l.receitas, false)}</span>` },
              { titulo: 'Despesas', classe: 'num', valor: (l) => `<span class="negativo">${UI.moeda(l.despesas, false)}</span>` },
              { titulo: 'Resultado', classe: 'num', valor: (l) => `<span class="${UI.classeValor(l.resultado)} forte">${UI.moeda(l.resultado)}</span>` },
              { titulo: '% do total', classe: 'num', valor: (l) => `${UI.numero(l.percentual)}%` },
              {
                titulo: 'Participação',
                valor: (l) => `<div class="barra"><span style="width:${(Math.max(l.receitas, l.despesas) / maior) * 100}%;background:${l.receitas ? 'var(--verde)' : 'var(--vermelho)'}"></span></div>`,
              },
            ],
            linhas: dados.linhas,
            vazio: 'Sem movimento no período.',
          })}
        </div>
      </div>`;
    Relatorios.ligarFiltros(`por-${agrupar}`);
  },

  /* ---------------------------------------------------------------- RAZÃO */
  async razao() {
    const p = Relatorios.periodo || { de: UI.primeiroDiaMes(), ate: UI.ultimoDiaMes() };
    const o = Relatorios.opcoes || {};
    const contas = Api.contasAnaliticas();
    const contaId = o.conta_contabil_id || (contas[0] && contas[0].id);
    const area = document.getElementById('area-relatorio');
    if (!contaId) {
      area.innerHTML = '<div class="cartao"><div class="vazio">Cadastre o plano de contas primeiro.</div></div>';
      return;
    }
    const dados = await Api.get('/api/relatorios/razao', {
      empresa_id: Estado.empresaId, conta_contabil_id: contaId, de: p.de, ate: p.ate,
    });

    area.innerHTML = `
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Razão — ${UI.escapar(dados.conta.codigo)} ${UI.escapar(dados.conta.nome)}</h3>
            <div class="mini">Saldo anterior ${UI.moeda(dados.saldo_anterior)} · débitos ${UI.moeda(dados.totais.debitos)} · créditos ${UI.moeda(dados.totais.creditos)} · saldo final ${UI.moeda(dados.totais.saldo_final)}</div></div>
        </div>
        ${Relatorios.cabecalhoPeriodo(UI.campo('Conta contábil',
          UI.select('conta_contabil_id', UI.opcoesContas(), contaId, { vazio: false })))}
        <div class="cartao-corpo sem-padding">
          ${UI.tabela({
            colunas: [
              { titulo: 'Data', valor: (l) => UI.data(l.data) },
              { titulo: 'Histórico', valor: (l) => UI.escapar(l.historico) },
              { titulo: 'Contrapartida', valor: (l) => `<span class="mini">${UI.escapar(l.contrapartida)}</span>` },
              { titulo: 'Débito', classe: 'num', valor: (l) => UI.moeda(l.debito, false) },
              { titulo: 'Crédito', classe: 'num', valor: (l) => UI.moeda(l.credito, false) },
              { titulo: 'Saldo', classe: 'num', valor: (l) => `<span class="forte">${UI.moeda(l.saldo)}</span>` },
            ],
            linhas: dados.linhas,
            vazio: 'Nenhum lançamento nesta conta no período.',
          })}
        </div>
      </div>`;
    Relatorios.ligarFiltros('razao-contabil');
  },
};
