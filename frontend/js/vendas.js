/* Vendas e margens — os relatórios comerciais.

   Fica separado de Relatórios de propósito: lá são perguntas de contabilidade
   (DRE, balancete, razão), que vêm dos lançamentos; aqui são perguntas de dono
   de negócio — quanto vendi, para quem, com que margem, o que está encalhado —,
   e vêm das vendas e do estoque. Misturar as duas coisas numa tela de vinte
   abas só faria achar a aba certa virar o trabalho.

   Todas as abas partem do mesmo período e das mesmas linhas de venda, no
   servidor. Por isso o total da aba Clientes é sempre o mesmo da aba Produtos —
   o que não aconteceria se cada tela montasse a sua consulta. */
const Vendas = {
  _aba: 'geral',
  _periodo: null,
  _dados: null,
  _ordem: 'receita',
  _dias: 60,

  ABAS: [
    { id: 'geral', rotulo: 'Visão geral' },
    { id: 'clientes', rotulo: 'Melhores clientes' },
    { id: 'produtos', rotulo: 'Produtos mais vendidos' },
    { id: 'margens', rotulo: 'Melhores margens' },
    { id: 'custos', rotulo: 'Custos' },
    { id: 'parados', rotulo: 'Parados em estoque' },
  ],

  /* Duas séries na mesma escala e na mesma unidade (reais): colunas lado a
     lado, num eixo só. Duas escalas num gráfico só é a maneira clássica de
     inventar uma correlação que não existe nos números. */
  SERIES: [
    { campo: 'receita', rotulo: 'Faturamento', cor: 'var(--azul)' },
    { campo: 'margem', rotulo: 'Margem bruta', cor: 'var(--verde)' },
  ],

  periodo() {
    if (!Vendas._periodo) {
      Vendas._periodo = { de: UI.primeiroDiaMes(), ate: UI.ultimoDiaMes() };
    }
    return Vendas._periodo;
  },

  /* ------------------------------------------------------------------ tela */
  async tela(aba) {
    if (aba) Vendas._aba = aba;
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = `
      <div class="abas">${Vendas.ABAS
        .map((a) => `<button class="aba ${a.id === Vendas._aba ? 'ativa' : ''}" data-aba="${a.id}">${a.rotulo}</button>`)
        .join('')}</div>
      <div id="area-vendas"><div class="cartao"><div class="vazio">Carregando...</div></div></div>`;
    alvo.querySelectorAll('[data-aba]').forEach((b) => {
      b.onclick = () => Vendas.tela(b.dataset.aba);
    });
    await Vendas.carregar();
  },

  async carregar() {
    const area = document.getElementById('area-vendas');
    const p = Vendas.periodo();
    const rotas = {
      geral: ['/api/vendas/resumo', {}],
      clientes: ['/api/vendas/clientes', {}],
      produtos: ['/api/vendas/produtos', { ordem: 'quantidade' }],
      margens: ['/api/vendas/produtos', { ordem: 'margem_percentual' }],
      custos: ['/api/vendas/custos', {}],
      parados: ['/api/vendas/parados', { dias: Vendas._dias }],
    };
    const [rota, extras] = rotas[Vendas._aba];
    const params = Vendas._aba === 'parados'
      ? { empresa_id: Estado.empresaId, ...extras }
      : { empresa_id: Estado.empresaId, de: p.de, ate: p.ate, ...extras };
    try {
      Vendas._dados = await Api.get(rota, params);
      area.innerHTML = Vendas.desenhar();
      Vendas.ligar();
    } catch (e) {
      area.innerHTML = `<div class="cartao"><div class="vazio">${UI.escapar(e.message)}</div></div>`;
    }
  },

  filtros(extra = '') {
    const p = Vendas.periodo();
    return `<div class="filtros" data-nao-suja>
      ${Vendas._aba === 'parados' ? '' : `
        ${UI.campo('De', `<input type="date" name="de" value="${p.de}">`)}
        ${UI.campo('Até', `<input type="date" name="ate" value="${p.ate}">`)}`}
      ${extra}
      <div class="acoes">
        <button class="btn btn-primario" id="btn-gerar-vendas">Gerar</button>
        <button class="btn" id="btn-exportar-vendas">CSV</button>
        <button class="btn" id="btn-imprimir-vendas">Imprimir</button>
      </div>
    </div>`;
  },

  desenhar() {
    switch (Vendas._aba) {
      case 'clientes': return Vendas.telaClientes();
      case 'produtos': return Vendas.telaProdutos(false);
      case 'margens': return Vendas.telaProdutos(true);
      case 'custos': return Vendas.telaCustos();
      case 'parados': return Vendas.telaParados();
      default: return Vendas.telaGeral();
    }
  },

  /* ------------------------------------------------------------ visão geral */
  telaGeral() {
    const d = Vendas._dados;
    const t = d.totais;
    return `
      <div class="cartao"><div class="cartao-corpo">${Vendas.filtros()}</div></div>

      <div class="grade g4" style="margin:14px 0">
        ${Vendas.kpi('Faturamento', UI.moeda(t.receita),
          `${t.documentos} venda(s) · ticket médio ${UI.moeda(t.ticket_medio)}`, 'azul')}
        ${Vendas.kpi('Custo das mercadorias', UI.moeda(t.custo),
          'o que a mercadoria vendida custou')}
        ${Vendas.kpi('Margem bruta', UI.moeda(t.margem),
          `${UI.numero(t.margem_percentual, 2)}% do faturamento`,
          t.margem < 0 ? 'vermelho' : 'verde')}
        ${Vendas.kpi('Itens vendidos', UI.numero(t.quantidade, 0),
          `${t.itens} linha(s) de venda`)}
      </div>

      ${Vendas.avisoSemCusto(t)}

      <div class="cartao">
        <div class="cartao-cabecalho"><div>
          <h3>Faturamento e margem no período</h3>
          <div class="mini">margem bruta = faturamento − custo da mercadoria. Dela ainda
            saem despesa fixa, salário e imposto — o lucro da empresa é o do DRE.</div>
        </div></div>
        <div class="cartao-corpo">
          ${UI.graficoColunas(d.evolucao, { series: Vendas.SERIES })}
        </div>
      </div>

      <div class="grade g2" style="margin-top:14px">
        <div class="cartao">
          <div class="cartao-cabecalho"><div><h3>Dez melhores clientes</h3>
            <div class="mini">por faturamento no período</div></div></div>
          <div class="cartao-corpo">
            ${UI.graficoRanking(d.clientes, { campo: 'receita', rotulo: 'cliente' })}
          </div>
        </div>
        <div class="cartao">
          <div class="cartao-cabecalho"><div><h3>Dez produtos que mais faturaram</h3>
            <div class="mini">por faturamento no período</div></div></div>
          <div class="cartao-corpo">
            ${UI.graficoRanking(d.produtos, { campo: 'receita', rotulo: 'produto' })}
          </div>
        </div>
      </div>

      <div class="cartao" style="margin-top:14px">
        <div class="cartao-cabecalho"><div><h3>Por categoria</h3></div></div>
        <div class="cartao-corpo sem-padding">
          ${Vendas.tabela(d.categorias, [
            { titulo: 'Categoria', chave: 'categoria', valor: (l) => UI.escapar(l.categoria) },
          ])}
        </div>
      </div>

      <div class="cartao" style="margin-top:14px">
        <div class="cartao-cabecalho"><div><h3>Por tipo de venda</h3>
          <div class="mini">a venda sem documento entra aqui; quando a nota dela sair,
            passa a contar como nota — nunca as duas</div></div></div>
        <div class="cartao-corpo sem-padding">
          ${Vendas.tabela(d.tipos, [
            { titulo: 'Tipo', chave: 'tipo', valor: (l) => UI.escapar(l.tipo) },
          ])}
        </div>
      </div>`;
  },

  /* --------------------------------------------------------------- clientes */
  telaClientes() {
    const d = Vendas._dados;
    return `
      <div class="cartao"><div class="cartao-corpo">${Vendas.filtros()}</div></div>
      <div class="cartao" style="margin-top:14px">
        <div class="cartao-cabecalho"><div><h3>Melhores clientes</h3>
          <div class="mini">${d.linhas.length} cliente(s) no período</div></div></div>
        <div class="cartao-corpo">
          ${UI.graficoRanking(d.linhas, { campo: 'receita', rotulo: 'cliente', limite: 12 })}
        </div>
        <div class="cartao-corpo sem-padding">
          ${Vendas.tabela(d.linhas, [
            { titulo: 'Cliente', chave: 'cliente', valor: (l) => UI.escapar(l.cliente) },
            { titulo: 'Compras', classe: 'direita', valor: (l) => String(l.documentos) },
            { titulo: 'Ticket médio', classe: 'direita', valor: (l) => UI.moeda(l.ticket_medio) },
          ])}
        </div>
      </div>`;
  },

  /* --------------------------------------------------------------- produtos */
  telaProdutos(porMargem) {
    const d = Vendas._dados;
    // a barra tem de medir a MESMA coisa pela qual a lista está ordenada: barra
    // em reais numa lista ordenada por percentual sai fora de ordem e parece
    // defeito da tela
    const campo = porMargem ? 'margem_percentual' : 'quantidade';
    return `
      <div class="cartao"><div class="cartao-corpo">${Vendas.filtros()}</div></div>
      <div class="cartao" style="margin-top:14px">
        <div class="cartao-cabecalho"><div>
          <h3>${porMargem ? 'Produtos com melhor margem' : 'Produtos mais vendidos'}</h3>
          <div class="mini">${porMargem
            ? 'ordenado pela margem em % — produto que quase não vendeu fica no fim da '
              + 'lista, porque margem de uma venda só não é informação'
            : 'ordenado pela quantidade vendida'}</div></div></div>
        <div class="cartao-corpo">
          ${UI.graficoRanking(d.linhas, {
            campo, rotulo: 'produto', limite: 12,
            formato: porMargem
              ? ((v) => `${UI.numero(v, 2)}%`)
              : ((v) => UI.numero(v, 0)),
          })}
        </div>
        <div class="cartao-corpo sem-padding">
          ${Vendas.tabela(d.linhas, [
            { titulo: 'Produto', chave: 'produto', valor: (l) => `${UI.escapar(l.produto)}
              <div class="mini">${UI.escapar(l.codigo || '')}${l.categoria
                ? ` · ${UI.escapar(l.categoria)}` : ''}</div>` },
            { titulo: 'Quantidade', classe: 'direita',
              valor: (l) => `${UI.numero(l.quantidade, 0)} ${UI.escapar(l.unidade || '')}` },
          ])}
        </div>
      </div>`;
  },

  /* ----------------------------------------------------------------- custos */
  telaCustos() {
    const d = Vendas._dados;
    const t = d.totais;
    return `
      <div class="cartao"><div class="cartao-corpo">${Vendas.filtros()}</div></div>

      <div class="grade g4" style="margin:14px 0">
        ${Vendas.kpi('Custo das mercadorias', UI.moeda(t.custo),
          'o CMV do período', 'azul')}
        ${Vendas.kpi('Faturamento', UI.moeda(t.receita), `${t.documentos} venda(s)`)}
        ${Vendas.kpi('Margem bruta', UI.moeda(t.margem),
          `${UI.numero(t.margem_percentual, 2)}% do faturamento`,
          t.margem < 0 ? 'vermelho' : 'verde')}
        ${Vendas.kpi('Custo sobre a venda',
          `${UI.numero(t.receita ? (t.custo / t.receita) * 100 : 0, 2)}%`,
          'quanto de cada real vendido foi custo')}
      </div>

      ${Vendas.avisoSemCusto(t)}

      <div class="cartao">
        <div class="cartao-cabecalho"><div><h3>Custo por categoria</h3></div></div>
        <div class="cartao-corpo">
          ${UI.graficoRanking(d.categorias, { campo: 'custo', rotulo: 'categoria', limite: 12 })}
        </div>
        <div class="cartao-corpo sem-padding">
          ${Vendas.tabela(d.categorias, [
            { titulo: 'Categoria', chave: 'categoria', valor: (l) => UI.escapar(l.categoria) },
          ])}
        </div>
      </div>

      <div class="cartao" style="margin-top:14px">
        <div class="cartao-cabecalho"><div><h3>Custo por produto</h3>
          <div class="mini">do que mais custou para o que menos custou</div></div></div>
        <div class="cartao-corpo sem-padding">
          ${Vendas.tabela(d.produtos, [
            { titulo: 'Produto', chave: 'produto', valor: (l) => `${UI.escapar(l.produto)}
              <div class="mini">${UI.escapar(l.codigo || '')}</div>` },
            { titulo: 'Quantidade', classe: 'direita',
              valor: (l) => UI.numero(l.quantidade, 0) },
          ])}
        </div>
      </div>`;
  },

  /* ---------------------------------------------------------------- parados */
  telaParados() {
    const d = Vendas._dados;
    return `
      <div class="cartao"><div class="cartao-corpo">
        ${Vendas.filtros(UI.campo('Parado há mais de',
          `<input type="number" name="dias" min="0" max="3650" value="${d.dias}">`,
          'dias sem sair do estoque'))}
      </div></div>

      <div class="grade g3" style="margin:14px 0">
        ${Vendas.kpi('Dinheiro parado', UI.moeda(d.valor_total),
          `saldo x custo médio`, d.valor_total ? 'ambar' : '')}
        ${Vendas.kpi('Produtos parados', String(d.produtos),
          `sem sair há mais de ${d.dias} dia(s)`)}
        ${Vendas.kpi('Nunca vendidos', String(d.nunca_vendidos),
          'entraram no estoque e nunca saíram')}
      </div>

      <div class="cartao">
        <div class="cartao-cabecalho"><div><h3>O que está parado</h3>
          <div class="mini">só produtos que controlam estoque e ainda têm saldo —
            produto zerado não está parado, está acabado</div></div></div>
        <div class="cartao-corpo">
          ${UI.graficoRanking(d.linhas, { campo: 'valor', rotulo: 'produto', limite: 12,
            cor: 'var(--ambar)' })}
        </div>
        <div class="cartao-corpo sem-padding">
          ${UI.tabela({
            vazio: `Nenhum produto parado há mais de ${d.dias} dias. `
              + 'Todo o estoque teve saída no período.',
            colunas: [
              { titulo: 'Produto', valor: (l) => `<b>${UI.escapar(l.produto)}</b>
                <div class="mini">${UI.escapar(l.codigo)} · ${UI.escapar(l.categoria)}</div>` },
              { titulo: 'Saldo', classe: 'direita',
                valor: (l) => `${UI.numero(l.saldo, 0)} ${UI.escapar(l.unidade)}` },
              { titulo: 'Custo médio', classe: 'direita', valor: (l) => UI.moeda(l.custo_medio) },
              { titulo: 'Parado desde', classe: 'direita', valor: (l) => (l.ultima_saida
                ? `${UI.data(l.ultima_saida)}<div class="mini">${l.dias_parado} dias</div>`
                : '<span class="alerta">nunca saiu</span>') },
              { titulo: 'Dinheiro parado', classe: 'direita', chave: 'valor',
                valor: (l) => `<b>${UI.moeda(l.valor)}</b>` },
            ],
            linhas: d.linhas,
            rodape: d.linhas.length ? { valor: `<b>${UI.moeda(d.valor_total)}</b>` } : null,
          })}
        </div>
      </div>`;
  },

  /* ----------------------------------------------------------- componentes */
  kpi(titulo, valor, dica, cor = '') {
    return `<div class="kpi ${cor ? `destaque-${cor}` : ''}">
      <div class="kpi-rotulo">${UI.escapar(titulo)}</div>
      <div class="kpi-valor" ${cor ? `style="color:var(--${cor})"` : ''}>${UI.escapar(String(valor))}</div>
      <div class="kpi-nota">${UI.escapar(dica)}</div></div>`;
  },

  /** As colunas de dinheiro são sempre as mesmas — o que muda é a primeira. */
  tabela(linhas, colunasIniciais) {
    const total = (campo) => linhas.reduce((s, l) => s + Number(l[campo] || 0), 0);
    return UI.tabela({
      vazio: 'Nenhuma venda no período.',
      colunas: colunasIniciais.concat([
        { titulo: 'Faturamento', classe: 'direita', chave: 'receita',
          valor: (l) => UI.moeda(l.receita) },
        { titulo: 'Custo', classe: 'direita', chave: 'custo',
          valor: (l) => UI.moeda(l.custo) },
        { titulo: 'Margem', classe: 'direita', chave: 'margem',
          valor: (l) => `<span class="${l.margem < 0 ? 'negativo' : 'positivo'} forte">${UI.moeda(l.margem)}</span>` },
        { titulo: 'Margem %', classe: 'direita',
          valor: (l) => `<span class="${l.margem < 0 ? 'negativo' : ''}">${UI.numero(l.margem_percentual, 2)}%</span>${
            l.sem_custo ? '<div class="mini alerta">custo incompleto</div>' : ''}` },
      ]),
      linhas,
      rodape: linhas.length ? {
        [colunasIniciais[0].chave]: `<b>${linhas.length} linha(s)</b>`,
        receita: `<b>${UI.moeda(total('receita'))}</b>`,
        custo: `<b>${UI.moeda(total('custo'))}</b>`,
        margem: `<b>${UI.moeda(total('margem'))}</b>`,
      } : null,
    });
  },

  avisoSemCusto(t) {
    if (!t.receita_sem_custo) return '';
    return `<div class="aviso-caixa">
      <b>Margem incompleta.</b> ${UI.moeda(t.receita_sem_custo)} de faturamento saiu de
      produto sem custo conhecido — nem movimento de estoque, nem custo de compra no
      cadastro. Esses itens entram com custo zero, então a margem acima está
      <b>maior do que a real</b>. Preencha o custo de compra no cadastro do produto
      (botão Preço) ou lance a entrada da mercadoria.
    </div>`;
  },

  /* ----------------------------------------------------------------- ações */
  ligar() {
    const area = document.getElementById('area-vendas');
    const gerar = () => {
      const de = area.querySelector('[name=de]');
      const ate = area.querySelector('[name=ate]');
      if (de && ate) Vendas._periodo = { de: de.value, ate: ate.value };
      const dias = area.querySelector('[name=dias]');
      if (dias) Vendas._dias = Number(dias.value || 0);
      Vendas.carregar();
    };
    const botao = (id, acao) => {
      const b = area.querySelector(`#${id}`);
      if (b) b.onclick = acao;
    };
    botao('btn-gerar-vendas', gerar);
    botao('btn-imprimir-vendas', () => UI.imprimir());
    botao('btn-exportar-vendas', () => {
      const nome = `vendas-${Vendas._aba}`;
      UI.exportarTabela(nome, '#area-vendas table');
    });
    area.querySelectorAll('[name=dias]').forEach((c) => { c.onchange = gerar; });
  },
};
