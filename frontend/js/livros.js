/* Relatórios Fiscais — os livros fiscais montados das notas e do estoque.

   Cinco abas: Registro de Entradas, Registro de Saídas, Resumo por CFOP,
   Resumo por Estado e Livro de estoque. Nada é digitado: as notas são as mesmas
   do SPED Fiscal (a importada vira entrada; a NF-e e o cupom emitidos viram
   saída), e o estoque sai dos movimentos. Todo livro imprime com o cabeçalho
   da empresa e baixa em planilha (CSV). */
const Livros = {
  _aba: 'entradas',
  _de: '',
  _ate: '',
  _soMovimento: false,
  _dados: null,

  ABAS: [
    { aba: 'entradas', rotulo: 'Registro de Entradas' },
    { aba: 'saidas', rotulo: 'Registro de Saídas' },
    { aba: 'cfop', rotulo: 'Por CFOP' },
    { aba: 'uf', rotulo: 'Por Estado' },
    { aba: 'estoque', rotulo: 'Livro de estoque' },
  ],

  /* O período padrão é o mês anterior: é o que o contador pede no começo do mês. */
  periodoPadrao() {
    const hoje = new Date();
    const inicio = new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1);
    const fim = new Date(hoje.getFullYear(), hoje.getMonth(), 0);
    const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${
      String(d.getDate()).padStart(2, '0')}`;
    return [iso(inicio), iso(fim)];
  },

  async tela(aba) {
    if (aba && Livros.ABAS.some((a) => a.aba === aba)) Livros._aba = aba;
    if (!Livros._de) [Livros._de, Livros._ate] = Livros.periodoPadrao();
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';
    try {
      Livros._dados = await Api.get(`/api/livros/${Livros._aba}`, {
        empresa_id: Estado.empresaId, de: Livros._de, ate: Livros._ate,
        apenas_com_movimento: Livros._soMovimento ? 'true' : '',
      });
    } catch (e) {
      Livros._dados = null;
      Livros.desenhar(`<div class="erro-caixa">${UI.escapar(e.message)}</div>`);
      return;
    }
    Livros.desenhar();
  },

  desenhar(conteudo) {
    const aba = Livros.ABAS.find((a) => a.aba === Livros._aba);
    document.getElementById('pagina').innerHTML = `
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Livros Fiscais</h3>
            <div class="mini">montados das notas importadas, das NF-e e dos cupons emitidos
              e dos movimentos de estoque — as mesmas notas do SPED Fiscal.</div></div>
          <div class="espaco">
            <button class="btn" id="btn-livro-csv">Baixar planilha</button>
            <button class="btn btn-primario" id="btn-livro-imprimir">Imprimir</button>
          </div>
        </div>
        <div class="cartao-corpo">
          <div class="abas">
            ${Livros.ABAS.map((a) => `<button class="aba ${a.aba === Livros._aba ? 'ativa' : ''}"
              data-aba="${a.aba}">${a.rotulo}</button>`).join('')}
          </div>
          <div class="filtros" data-nao-suja>
            ${UI.campo('De', `<input type="date" name="de" value="${Livros._de}">`)}
            ${UI.campo('Até', `<input type="date" name="ate" value="${Livros._ate}">`)}
            ${Livros._aba === 'estoque' ? `
              <label class="campo">Produtos
                <span class="espaco" style="margin-top:6px">
                  <input type="checkbox" name="so_movimento" ${Livros._soMovimento ? 'checked' : ''}>
                  <span class="mini">só os que movimentaram</span>
                </span>
              </label>` : ''}
            <div class="acoes"><button class="btn btn-primario" id="btn-livro-gerar">Gerar</button></div>
          </div>
          ${Livros.cabecalhoImpressao(aba ? aba.rotulo : '')}
          <div id="livro-conteudo">${conteudo || Livros.corpo()}</div>
        </div>
      </div>`;
    Livros.ligar();
  },

  /* O cabeçalho que o livro de papel tem: empresa, CNPJ, IE e período. */
  cabecalhoImpressao(titulo) {
    const d = Livros._dados;
    const e = (d && d.empresa) || {};
    return `
      <div class="livro-cabecalho">
        <div class="forte" style="font-size:16px">${UI.escapar((d && d.livro) || titulo)}</div>
        <div>${UI.escapar(e.razao_social || '')}
          ${e.cnpj ? ` · CNPJ ${UI.escapar(e.cnpj)}` : ''}
          ${e.inscricao_estadual ? ` · IE ${UI.escapar(e.inscricao_estadual)}` : ''}
          ${e.uf ? ` · ${UI.escapar(e.uf)}` : ''}</div>
        <div class="mini">Período: ${UI.data(Livros._de)} a ${UI.data(Livros._ate)}</div>
      </div>`;
  },

  corpo() {
    const d = Livros._dados;
    if (!d) return '<div class="vazio">Escolha o período e clique em Gerar.</div>';
    if (Livros._aba === 'entradas' || Livros._aba === 'saidas') return Livros.telaNotas(d);
    if (Livros._aba === 'cfop') return Livros.telaResumo(d, 'cfop');
    if (Livros._aba === 'uf') return Livros.telaResumo(d, 'uf');
    return Livros.telaEstoque(d);
  },

  /* ------------------------------------------------ entradas e saídas */
  colunasNotas() {
    const entrada = Livros._aba === 'entradas';
    return [
      { titulo: entrada ? 'Data' : 'Emissão', chave: 'data', valor: (x) => UI.data(x.data), csv: (x) => x.data },
      { titulo: 'Documento', chave: 'numero',
        valor: (x) => `${x.especie} <span class="forte">${UI.escapar(x.numero)}</span>
          <div class="mini">série ${UI.escapar(x.serie || '-')}</div>`, csv: (x) => x.numero },
      { titulo: 'Espécie', chave: 'especie', oculta: true, csv: (x) => x.especie },
      { titulo: 'Série', chave: 'serie', oculta: true, csv: (x) => x.serie },
      { titulo: entrada ? 'Emitente' : 'Destinatário', chave: 'participante',
        valor: (x) => `${UI.escapar(x.participante || '-')}<div class="mini">${UI.escapar(x.documento || '')}</div>`,
        csv: (x) => x.participante },
      { titulo: 'CNPJ/CPF', chave: 'documento', oculta: true, csv: (x) => x.documento },
      { titulo: 'UF', chave: 'uf', classe: 'centro', valor: (x) => UI.escapar(x.uf || '-'), csv: (x) => x.uf },
      { titulo: 'CFOP', chave: 'cfop', classe: 'centro', valor: (x) => UI.escapar(x.cfop || '-'), csv: (x) => x.cfop },
      { titulo: 'Valor contábil', chave: 'valor_contabil', classe: 'num', valor: (x) => UI.moeda(x.valor_contabil), csv: (x) => Livros.num(x.valor_contabil) },
      { titulo: 'Base ICMS', chave: 'base', classe: 'num', valor: (x) => UI.moeda(x.base, false), csv: (x) => Livros.num(x.base) },
      { titulo: 'Alíq.', chave: 'aliquota', classe: 'num', valor: (x) => (x.aliquota ? `${UI.numero(x.aliquota)}%` : ''), csv: (x) => Livros.num(x.aliquota) },
      { titulo: entrada ? 'ICMS creditado' : 'ICMS debitado', chave: 'icms', classe: 'num', valor: (x) => UI.moeda(x.icms, false), csv: (x) => Livros.num(x.icms) },
      { titulo: 'Isentas / não trib.', chave: 'isentas', classe: 'num', valor: (x) => UI.moeda(x.isentas, false), csv: (x) => Livros.num(x.isentas) },
      { titulo: 'Outras', chave: 'outras', classe: 'num', valor: (x) => UI.moeda(x.outras, false), csv: (x) => Livros.num(x.outras) },
      { titulo: 'IPI', chave: 'ipi', classe: 'num', valor: (x) => UI.moeda(x.ipi, false), csv: (x) => Livros.num(x.ipi) },
      { titulo: 'Observação', chave: 'observacao', valor: (x) => (x.observacao
        ? `<span class="tag ${x.observacao === 'CANCELADA' || x.observacao === 'DENEGADA' ? 'tag-cancelado' : 'tag-parcial'}">${
          UI.escapar(x.observacao)}</span>` : ''), csv: (x) => x.observacao },
    ];
  },

  telaNotas(d) {
    const t = d.totais || {};
    const avisos = [];
    if (d.so_resumo) {
      avisos.push(`${d.so_resumo} nota(s) sem itens entraram só pelos totais do cabeçalho — o CFOP
        e o ICMS podem estar incompletos. Complete-as em Fiscal → SPED Fiscal → Completar as notas.`);
    }
    return `
      <div class="grade g4" style="margin:12px 0">
        ${Livros.kpi('Documentos', d.documentos, `${d.canceladas} cancelado(s)`)}
        ${Livros.kpi('Valor contábil', UI.moeda(t.valor_contabil))}
        ${Livros.kpi('Base de cálculo', UI.moeda(t.base))}
        ${Livros.kpi(Livros._aba === 'entradas' ? 'ICMS creditado' : 'ICMS debitado', UI.moeda(t.icms))}
      </div>
      ${avisos.map((a) => `<div class="aviso-caixa">${a}</div>`).join('')}
      ${UI.tabela({
        colunas: Livros.colunasNotas().filter((c) => !c.oculta && (c.chave !== 'ipi' || t.ipi)),
        linhas: d.linhas,
        vazio: 'Nenhuma nota neste período.',
        rodape: {
          data: '<b>Totais</b>',
          valor_contabil: `<b>${UI.moeda(t.valor_contabil)}</b>`,
          base: `<b>${UI.moeda(t.base)}</b>`,
          icms: `<b>${UI.moeda(t.icms)}</b>`,
          isentas: `<b>${UI.moeda(t.isentas)}</b>`,
          outras: `<b>${UI.moeda(t.outras)}</b>`,
          ipi: `<b>${UI.moeda(t.ipi)}</b>`,
        },
      })}`;
  },

  /* ------------------------------------------------ resumos */
  colunasResumo(tipo) {
    const primeira = tipo === 'cfop'
      ? [{ titulo: 'CFOP', chave: 'cfop', valor: (x) => `<span class="forte">${UI.escapar(x.cfop)}</span>
            <div class="mini">${UI.escapar(x.grupo || '')}</div>`, csv: (x) => x.cfop },
         { titulo: 'Grupo', chave: 'grupo', oculta: true, csv: (x) => x.grupo }]
      : [{ titulo: 'UF', chave: 'uf', valor: (x) => `<span class="forte">${UI.escapar(x.uf)}</span>
            ${x.dentro_do_estado ? '<div class="mini">dentro do estado</div>' : ''}`, csv: (x) => x.uf }];
    return primeira.concat([
      { titulo: 'Documentos', chave: 'documentos', classe: 'num', valor: (x) => x.documentos, csv: (x) => x.documentos },
      { titulo: 'Valor contábil', chave: 'valor_contabil', classe: 'num', valor: (x) => UI.moeda(x.valor_contabil), csv: (x) => Livros.num(x.valor_contabil) },
      { titulo: 'Base ICMS', chave: 'base', classe: 'num', valor: (x) => UI.moeda(x.base, false), csv: (x) => Livros.num(x.base) },
      { titulo: 'ICMS', chave: 'icms', classe: 'num', valor: (x) => UI.moeda(x.icms, false), csv: (x) => Livros.num(x.icms) },
      { titulo: 'Isentas / não trib.', chave: 'isentas', classe: 'num', valor: (x) => UI.moeda(x.isentas, false), csv: (x) => Livros.num(x.isentas) },
      { titulo: 'Outras', chave: 'outras', classe: 'num', valor: (x) => UI.moeda(x.outras, false), csv: (x) => Livros.num(x.outras) },
      { titulo: 'IPI', chave: 'ipi', classe: 'num', valor: (x) => UI.moeda(x.ipi, false), csv: (x) => Livros.num(x.ipi) },
    ]);
  },

  rodapeResumo(t, tipo) {
    return {
      [tipo]: '<b>Totais</b>',
      documentos: `<b>${t.documentos}</b>`,
      valor_contabil: `<b>${UI.moeda(t.valor_contabil)}</b>`,
      base: `<b>${UI.moeda(t.base)}</b>`,
      icms: `<b>${UI.moeda(t.icms)}</b>`,
      isentas: `<b>${UI.moeda(t.isentas)}</b>`,
      outras: `<b>${UI.moeda(t.outras)}</b>`,
      ipi: `<b>${UI.moeda(t.ipi)}</b>`,
    };
  },

  telaResumo(d, tipo) {
    const temIpi = d.entradas.totais.ipi || d.saidas.totais.ipi;
    const colunas = Livros.colunasResumo(tipo).filter((c) => !c.oculta && (c.chave !== 'ipi' || temIpi));
    const bloco = (titulo, parte, dica) => `
      <h4 style="margin:18px 0 6px">${titulo}</h4>
      <div class="mini" style="margin-bottom:6px">${dica}</div>
      ${UI.tabela({
        colunas, linhas: parte.linhas, vazio: 'Nada neste período.',
        rodape: Livros.rodapeResumo(parte.totais, tipo),
      })}`;
    const ent = d.entradas.totais;
    const sai = d.saidas.totais;
    return `
      <div class="grade g4" style="margin:12px 0">
        ${Livros.kpi('Entradas', UI.moeda(ent.valor_contabil), `ICMS creditado ${UI.moeda(ent.icms)}`)}
        ${Livros.kpi('Saídas', UI.moeda(sai.valor_contabil), `ICMS debitado ${UI.moeda(sai.icms)}`)}
        ${Livros.kpi('ICMS débito − crédito', UI.moeda(sai.icms - ent.icms),
          'saldo simples do período, sem ajustes')}
        ${Livros.kpi('Documentos', ent.documentos + sai.documentos, 'canceladas ficam de fora')}
      </div>
      ${bloco('Entradas', d.entradas, tipo === 'cfop'
        ? 'CFOP iniciado em 1, 2 ou 3' : 'por estado do emitente')}
      ${bloco('Saídas', d.saidas, tipo === 'cfop'
        ? 'CFOP iniciado em 5, 6 ou 7' : 'por estado do destinatário — o cupom conta no estado da empresa')}`;
  },

  /* ------------------------------------------------ estoque */
  colunasEstoque() {
    const qtd = (v) => UI.numero(v, 3);
    return [
      { titulo: 'Código', chave: 'codigo', valor: (x) => UI.escapar(x.codigo), csv: (x) => x.codigo },
      { titulo: 'Produto', chave: 'produto', valor: (x) => `${UI.escapar(x.produto)}
          <div class="mini">${x.ncm ? `NCM ${UI.escapar(x.ncm)}` : ''}</div>`, csv: (x) => x.produto },
      { titulo: 'NCM', chave: 'ncm', oculta: true, csv: (x) => x.ncm },
      { titulo: 'Un.', chave: 'unidade', classe: 'centro', valor: (x) => UI.escapar(x.unidade), csv: (x) => x.unidade },
      { titulo: 'Saldo inicial', chave: 'inicial_quantidade', classe: 'num',
        valor: (x) => `${qtd(x.inicial_quantidade)}<div class="mini">${UI.moeda(x.inicial_valor)}</div>`,
        csv: (x) => Livros.num(x.inicial_quantidade, 3) },
      { titulo: 'Valor inicial', chave: 'inicial_valor', oculta: true, csv: (x) => Livros.num(x.inicial_valor) },
      { titulo: 'Entradas', chave: 'entradas_quantidade', classe: 'num',
        valor: (x) => `${qtd(x.entradas_quantidade)}<div class="mini">${UI.moeda(x.entradas_valor)}</div>`,
        csv: (x) => Livros.num(x.entradas_quantidade, 3) },
      { titulo: 'Valor entradas', chave: 'entradas_valor', oculta: true, csv: (x) => Livros.num(x.entradas_valor) },
      { titulo: 'Saídas', chave: 'saidas_quantidade', classe: 'num',
        valor: (x) => `${qtd(x.saidas_quantidade)}<div class="mini">${UI.moeda(x.saidas_valor)}</div>`,
        csv: (x) => Livros.num(x.saidas_quantidade, 3) },
      { titulo: 'Valor saídas', chave: 'saidas_valor', oculta: true, csv: (x) => Livros.num(x.saidas_valor) },
      { titulo: 'Saldo final', chave: 'final_quantidade', classe: 'num',
        valor: (x) => `<span class="${x.negativo ? 'negativo' : 'forte'}">${qtd(x.final_quantidade)}</span>`,
        csv: (x) => Livros.num(x.final_quantidade, 3) },
      { titulo: 'Custo médio', chave: 'final_custo_medio', classe: 'num',
        valor: (x) => UI.moeda(x.final_custo_medio, false), csv: (x) => Livros.num(x.final_custo_medio, 4) },
      { titulo: 'Valor final', chave: 'final_valor', classe: 'num',
        valor: (x) => UI.moeda(x.final_valor), csv: (x) => Livros.num(x.final_valor) },
    ];
  },

  telaEstoque(d) {
    const t = d.totais || {};
    return `
      <div class="grade g4" style="margin:12px 0">
        ${Livros.kpi('Estoque inicial', UI.moeda(t.inicial_valor), `em ${UI.data(Livros._de)}`)}
        ${Livros.kpi('Entradas', UI.moeda(t.entradas_valor), 'a custo de entrada')}
        ${Livros.kpi('Saídas', UI.moeda(t.saidas_valor), 'a custo médio')}
        ${Livros.kpi('Estoque final', UI.moeda(t.final_valor), `inventário em ${UI.data(Livros._ate)}`)}
      </div>
      ${d.negativos ? `<div class="aviso-caixa">${d.negativos} produto(s) terminam o período
        com saldo negativo — confira as entradas em Estoque → Extrato.</div>` : ''}
      ${UI.tabela({
        colunas: Livros.colunasEstoque().filter((c) => !c.oculta),
        linhas: d.linhas,
        vazio: 'Nenhum produto com estoque neste período. Só entram os produtos marcados '
          + 'como "controla estoque" no cadastro.',
        rodape: {
          codigo: `<b>${t.produtos} produto(s)</b>`,
          inicial_quantidade: `<b>${UI.moeda(t.inicial_valor)}</b>`,
          entradas_quantidade: `<b>${UI.moeda(t.entradas_valor)}</b>`,
          saidas_quantidade: `<b>${UI.moeda(t.saidas_valor)}</b>`,
          final_valor: `<b>${UI.moeda(t.final_valor)}</b>`,
        },
      })}
      <div class="mini" style="margin-top:8px">O saldo em cada data é a soma dos movimentos
        até ela; o saldo final é o inventário na data final.</div>`;
  },

  /* ------------------------------------------------ utilidades */
  kpi(rotulo, valor, nota = '') {
    return `<div class="kpi"><div class="kpi-rotulo">${UI.escapar(rotulo)}</div>
      <div class="kpi-valor" style="font-size:18px">${valor}</div>
      ${nota ? `<div class="kpi-nota">${UI.escapar(nota)}</div>` : ''}</div>`;
  },

  /* número com vírgula, que é o que a planilha em português entende */
  num(v, casas = 2) {
    return Number(v || 0).toFixed(casas).replace('.', ',');
  },

  baixarCSV() {
    const d = Livros._dados;
    if (!d) return UI.erro('Gere o livro antes de baixar.');
    const nome = `${Livros._aba}-${Livros._de}-a-${Livros._ate}`;
    if (Livros._aba === 'cfop' || Livros._aba === 'uf') {
      const colunas = Livros.colunasResumo(Livros._aba);
      const linhas = [];
      [['Entradas', d.entradas], ['Saídas', d.saidas]].forEach(([sentido, parte]) => {
        parte.linhas.forEach((x) => linhas.push([sentido, ...colunas.map((c) => c.csv(x))]));
      });
      return UI.exportarCSV(nome, ['Sentido', ...colunas.map((c) => c.titulo)], linhas);
    }
    const colunas = Livros._aba === 'estoque' ? Livros.colunasEstoque() : Livros.colunasNotas();
    return UI.exportarCSV(nome, colunas.map((c) => c.titulo),
      d.linhas.map((x) => colunas.map((c) => c.csv(x))));
  },

  ligar() {
    const pagina = document.getElementById('pagina');
    pagina.querySelectorAll('[data-aba]').forEach((b) => {
      b.onclick = () => App.irPara(`/livros/${b.dataset.aba}`);
    });
    const gerar = pagina.querySelector('#btn-livro-gerar');
    if (gerar) {
      gerar.onclick = () => {
        const f = UI.lerFormulario(pagina.querySelector('.filtros'));
        if (!f.de || !f.ate) return UI.erro('Informe as duas datas do período.');
        Livros._de = f.de;
        Livros._ate = f.ate;
        Livros._soMovimento = !!pagina.querySelector('[name="so_movimento"]')?.checked;
        return Livros.tela();
      };
    }
    pagina.querySelector('#btn-livro-imprimir').onclick = () => UI.imprimir();
    pagina.querySelector('#btn-livro-csv').onclick = () => Livros.baixarCSV();
  },
};
