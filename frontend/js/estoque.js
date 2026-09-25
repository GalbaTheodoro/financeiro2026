/* Estoque: a posição de cada produto e o extrato dos movimentos.

   O estoque aqui não é um número que alguém digita: é a soma dos movimentos.
   A entrada vem do botão da nota de entrada, a saída é baixada sozinha quando
   a SEFAZ autoriza a nota de saída ou o cupom, e o que sobra — inventário,
   perda, saldo inicial — é o acerto à mão desta tela, que sempre pede o motivo. */
const Estoque = {
  _aba: 'posicao',
  _posicao: null,
  _extrato: null,
  _filtros: { produto_id: '', de: '', ate: '', origem: '' },
  _busca: '',
  _apenasComSaldo: false,

  ORIGENS: {
    NOTA: 'Nota de entrada',
    SAIDA: 'Nota de saída',
    CUPOM: 'Cupom fiscal',
    AJUSTE: 'Acerto à mão',
    SALDO_INICIAL: 'Saldo inicial',
    ESTORNO: 'Estorno',
  },

  async tela(aba) {
    if (aba) Estoque._aba = aba;
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';
    try {
      if (Estoque._aba === 'extrato') await Estoque.carregarExtrato();
      else await Estoque.carregarPosicao();
    } catch (e) {
      alvo.innerHTML = `<div class="cartao"><div class="vazio">${UI.escapar(e.message)}</div></div>`;
    }
  },

  async carregarPosicao() {
    Estoque._posicao = await Api.get('/api/estoque', {
      empresa_id: Estado.empresaId, busca: Estoque._busca,
      apenas_com_saldo: Estoque._apenasComSaldo,
    });
    Estoque.desenhar();
  },

  async carregarExtrato() {
    // o filtro de produto sai da posição — carrega junto quando se entra
    // direto no extrato pelo endereço
    if (!Estoque._posicao) {
      Estoque._posicao = await Api.get('/api/estoque', { empresa_id: Estado.empresaId });
    }
    Estoque._extrato = await Api.get('/api/estoque/extrato', {
      empresa_id: Estado.empresaId, ...Estoque._filtros,
    });
    Estoque.desenhar();
  },

  /* ------------------------------------------------------------------ tela */
  desenhar() {
    const r = (Estoque._posicao && Estoque._posicao.resumo) || {};
    document.getElementById('pagina').innerHTML = `
      ${Estoque._aba === 'posicao' ? `
      <div class="grade g4" style="margin-bottom:12px">
        ${Estoque.cartao('Produtos', r.produtos, 'com controle de estoque', 'azul')}
        ${Estoque.cartao('Valor parado', UI.moeda(r.valor_total || 0),
          'quantidade x custo médio', 'verde')}
        ${Estoque.cartao('Abaixo do mínimo', r.abaixo_do_minimo, 'hora de comprar',
          r.abaixo_do_minimo ? 'ambar' : '')}
        ${Estoque.cartao('Saldo negativo', r.negativos, 'saiu mais do que entrou',
          r.negativos ? 'vermelho' : '')}
      </div>` : ''}

      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Estoque</h3>
            <div class="mini">a entrada vem da nota; a saída é baixada sozinha na autorização</div></div>
          <div class="espaco">
            <button class="btn" id="btn-exportar-estoque">Exportar</button>
            <button class="btn btn-primario" id="btn-ajuste">Acerto de estoque</button>
          </div>
        </div>
        <div class="cartao-corpo">
          <div class="abas">
            <button class="aba ${Estoque._aba === 'posicao' ? 'ativa' : ''}" data-aba="posicao">Posição</button>
            <button class="aba ${Estoque._aba === 'extrato' ? 'ativa' : ''}" data-aba="extrato">Extrato</button>
          </div>
          ${Estoque._aba === 'posicao' ? Estoque.telaPosicao() : Estoque.telaExtrato()}
        </div>
      </div>`;
    Estoque.ligar();
  },

  cartao(titulo, valor, dica, cor = '') {
    return `<div class="kpi ${cor ? `destaque-${cor}` : ''}">
      <div class="kpi-rotulo">${UI.escapar(titulo)}</div>
      <div class="kpi-valor" ${cor ? `style="color:var(--${cor})"` : ''}>${
        typeof valor === 'string' ? valor : Number(valor || 0)}</div>
      <div class="kpi-nota">${UI.escapar(dica)}</div></div>`;
  },

  /* --------------------------------------------------------------- posição */
  telaPosicao() {
    const lista = (Estoque._posicao && Estoque._posicao.produtos) || [];
    return `
      <div class="linha-campos" data-nao-suja>
        ${UI.campo('Procurar', `<input name="busca" value="${UI.escapar(Estoque._busca)}"
          placeholder="código ou nome do produto">`)}
        <label class="campo">Mostrar
          <span class="espaco" style="margin-top:6px">
            <input type="checkbox" name="apenas_com_saldo" ${Estoque._apenasComSaldo ? 'checked' : ''}>
            <span class="mini">só quem tem saldo</span>
          </span>
        </label>
      </div>
      <div id="lista-estoque" style="margin-top:12px">${UI.tabela({
        vazio: 'Nenhum produto controla estoque ainda. Marque "controla estoque" no cadastro '
          + 'do produto — comissão, frete e serviço ficam de fora.',
        colunas: [
          { titulo: 'Produto', chave: 'produto', valor: (p) => `<b>${UI.escapar(p.nome)}</b>
              <div class="mini">${UI.escapar(p.codigo)}</div>` },
          { titulo: 'Saldo', classe: 'direita', valor: (p) => `
              <span class="forte ${p.negativo ? 'negativo' : p.abaixo_do_minimo ? 'alerta' : ''}">
                ${UI.numero(p.saldo, 0)} ${UI.escapar(p.unidade || '')}</span>
              ${p.abaixo_do_minimo ? `<div class="mini alerta">mínimo ${UI.numero(p.minimo, 0)}</div>` : ''}
              ${p.negativo ? '<div class="mini negativo">saiu mais do que entrou</div>' : ''}` },
          { titulo: 'Custo médio', classe: 'direita', valor: (p) => UI.moeda(p.custo_medio) },
          { titulo: 'Valor em estoque', classe: 'direita', chave: 'valor',
            valor: (p) => `<b>${UI.moeda(p.valor)}</b>` },
          { titulo: '', classe: 'direita', valor: (p, i) => `
              <button class="btn btn-mini" data-extrato="${i}">Extrato</button>
              <button class="btn btn-mini" data-acerto="${i}">Acertar</button>` },
        ],
        linhas: lista,
        rodape: lista.length ? {
          produto: `<b>${lista.length} produto(s)</b>`,
          valor: `<b>${UI.moeda((Estoque._posicao.resumo || {}).valor_total)}</b>`,
        } : null,
      })}</div>`;
  },

  /* --------------------------------------------------------------- extrato */
  telaExtrato() {
    const dados = Estoque._extrato || { movimentos: [], resumo: {} };
    const produtos = ((Estoque._posicao && Estoque._posicao.produtos) || []);
    return `
      <div class="linha-campos" data-nao-suja>
        ${UI.campo('Produto', UI.select('produto_id',
          produtos.map((p) => ({ valor: p.produto_id, rotulo: p.nome })),
          Estoque._filtros.produto_id, { vazio: 'Todos' }))}
        ${UI.campo('De', `<input type="date" name="de" value="${Estoque._filtros.de}">`)}
        ${UI.campo('Até', `<input type="date" name="ate" value="${Estoque._filtros.ate}">`)}
        ${UI.campo('Origem', UI.select('origem',
          Object.entries(Estoque.ORIGENS).map(([v, r]) => ({ valor: v, rotulo: r })),
          Estoque._filtros.origem, { vazio: 'Todas' }))}
      </div>
      <div id="lista-estoque" style="margin-top:12px">${UI.tabela({
        vazio: 'Nenhum movimento neste filtro.',
        colunas: [
          { titulo: 'Data', chave: 'data', valor: (m) => UI.data(m.data) },
          { titulo: 'Produto', valor: (m) => `${UI.escapar(m.produto_nome)}
              <div class="mini">${UI.escapar(Estoque.ORIGENS[m.origem] || m.origem)}${
                m.documento ? ` · nota ${UI.escapar(m.documento)}` : ''}</div>` },
          { titulo: 'Histórico', valor: (m) => `<span class="mini">${UI.escapar(m.historico || '')}</span>` },
          { titulo: 'Entrada', classe: 'direita', chave: 'entrada',
            valor: (m) => (m.tipo === 'E'
              ? `<span class="positivo forte">${UI.numero(m.quantidade, 0)}</span>` : '') },
          { titulo: 'Saída', classe: 'direita', chave: 'saida',
            valor: (m) => (m.tipo === 'S'
              ? `<span class="negativo forte">${UI.numero(m.quantidade, 0)}</span>` : '') },
          { titulo: 'Custo unit.', classe: 'direita', valor: (m) => UI.moeda(m.custo_unitario) },
          { titulo: 'Saldo depois', classe: 'direita',
            valor: (m) => `<b>${UI.numero(m.saldo, 0)}</b>
              <div class="mini">médio ${UI.moeda(m.custo_medio)}</div>` },
        ],
        linhas: dados.movimentos,
        rodape: dados.movimentos.length ? {
          data: `<b>${dados.resumo.linhas} movimento(s)</b>`,
          entrada: `<b class="positivo">${UI.numero(dados.resumo.entradas, 0)}</b>`,
          saida: `<b class="negativo">${UI.numero(dados.resumo.saidas, 0)}</b>`,
        } : null,
      })}</div>
      ${dados.resumo.linhas >= 500
        ? '<div class="mini" style="margin-top:8px">Mostrando os 500 movimentos mais recentes — aperte o filtro para ver mais atrás.</div>'
        : ''}`;
  },

  ligar() {
    const pagina = document.getElementById('pagina');
    pagina.querySelectorAll('[data-aba]').forEach((b) => {
      b.onclick = () => Estoque.tela(b.dataset.aba);
    });
    pagina.querySelector('#btn-ajuste').onclick = () => Estoque.formularioAcerto(null);
    pagina.querySelector('#btn-exportar-estoque').onclick = () =>
      UI.exportarTabela(`estoque-${Estoque._aba}`, '#lista-estoque table');

    const busca = pagina.querySelector('[name="busca"]');
    if (busca) {
      let tempo = null;
      busca.oninput = () => {
        clearTimeout(tempo);
        tempo = setTimeout(() => {
          Estoque._busca = busca.value;
          Estoque.carregarPosicao();
        }, 400);
      };
    }
    const soComSaldo = pagina.querySelector('[name="apenas_com_saldo"]');
    if (soComSaldo) {
      soComSaldo.onchange = () => {
        Estoque._apenasComSaldo = soComSaldo.checked;
        Estoque.carregarPosicao();
      };
    }
    ['produto_id', 'de', 'ate', 'origem'].forEach((nome) => {
      const campo = pagina.querySelector(`[name="${nome}"]`);
      if (!campo) return;
      campo.onchange = () => {
        Estoque._filtros[nome] = campo.value;
        Estoque.carregarExtrato();
      };
    });
    pagina.querySelectorAll('[data-extrato]').forEach((b) => {
      b.onclick = () => {
        const p = Estoque._posicao.produtos[Number(b.dataset.extrato)];
        Estoque._filtros = { produto_id: String(p.produto_id), de: '', ate: '', origem: '' };
        Estoque.tela('extrato');
      };
    });
    pagina.querySelectorAll('[data-acerto]').forEach((b) => {
      b.onclick = () => Estoque.formularioAcerto(
        Estoque._posicao.produtos[Number(b.dataset.acerto)]);
    });
  },

  /* ------------------------------------------------- acerto e saldo inicial */
  formularioAcerto(produto) {
    const lista = (Estoque._posicao && Estoque._posicao.produtos) || [];
    const corpo = UI.abrirModal({
      titulo: 'Acerto de estoque',
      corpo: `
        <div class="ok-caixa">
          O acerto é para <b>inventário, perda e saldo inicial</b>. Entrada de mercadoria
          vem da nota (botão <b>Gerar estoque</b> na nota de entrada) e a saída da venda
          é baixada sozinha — não precisa acertar nada nesses dois casos.
        </div>
        <div class="linha-campos">
          ${UI.campo('Produto', UI.select('produto_id',
            lista.map((p) => ({ valor: p.produto_id, rotulo: `${p.codigo} — ${p.nome}` })),
            produto ? produto.produto_id : '', { vazio: 'Escolha o produto', obrigatorio: true }))}
          ${UI.campo('O que aconteceu', UI.select('tipo', [
            { valor: 'E', rotulo: 'Entrou no estoque' },
            { valor: 'S', rotulo: 'Saiu do estoque' },
          ], 'E', { vazio: false }))}
          ${UI.campo('Quantidade', '<input name="quantidade" inputmode="decimal">')}
          ${UI.campo('Custo unitário', '<input name="custo_unitario" inputmode="decimal">',
            'só na entrada — entra na média do custo')}
          ${UI.campo('Data', `<input type="date" name="data" value="${UI.hoje()}">`)}
          ${UI.campo('Motivo *', '<input name="historico" placeholder="ex.: contagem do dia 30, perda por umidade">',
            'é ele que explica o movimento daqui a seis meses')}
        </div>
        <div id="saldo-do-produto" class="mini" style="margin-top:10px"></div>`,
      largo: true,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        { rotulo: 'Lançar o acerto', classe: 'btn-primario',
          acao: () => Estoque.salvarAcerto() },
      ],
    });
    const mostrarSaldo = () => {
      const id = Number(corpo.querySelector('[name="produto_id"]').value || 0);
      const p = lista.find((x) => x.produto_id === id);
      corpo.querySelector('#saldo-do-produto').innerHTML = p
        ? `Hoje: <b>${UI.numero(p.saldo, 0)} ${UI.escapar(p.unidade || '')}</b>,
           custo médio ${UI.moeda(p.custo_medio)}.`
        : '';
    };
    corpo.querySelector('[name="produto_id"]').onchange = mostrarSaldo;
    mostrarSaldo();
  },

  async salvarAcerto() {
    const corpo = document.getElementById('modal-corpo');
    const d = UI.lerFormulario(corpo);
    if (!d.produto_id) return UI.erro('Escolha o produto.');
    try {
      const r = await Api.post('/api/estoque/ajuste', {
        empresa_id: Estado.empresaId,
        produto_id: Number(d.produto_id),
        tipo: d.tipo,
        quantidade: Number(String(d.quantidade || '0').replace(',', '.')),
        custo_unitario: Number(String(d.custo_unitario || '0').replace(',', '.')),
        data: d.data,
        historico: d.historico,
      });
      UI.modalSalvo();
      UI.fecharModal();
      UI.sucesso(`Acerto lançado. Saldo agora: ${UI.numero(r.produto.saldo, 0)} `
        + `${r.produto.unidade || ''}.`);
      await Estoque.carregarPosicao();
    } catch (e) {
      UI.erro(e.message);
    }
  },
};
