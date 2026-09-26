/* Pedido de venda e orçamento — a tela de balcão em três colunas.

   O desenho é o de um PDV: categorias à esquerda, produtos no meio, carrinho à
   direita. A pessoa que atende não digita código nem procura em lista: clica na
   categoria, clica no produto, e o item entra no carrinho.

   Há um botão só de finalizar. Ele abre a segunda tela — à vista ou a prazo,
   quantas parcelas, e que documento fiscal sai. Separar as duas coisas é
   proposital: montar a venda e decidir como recebe são momentos diferentes, e
   misturá-los é o que faz o operador errar a forma de pagamento com o cliente
   esperando. */
const Pedidos = {
  _lista: null,
  _atual: null,          // o pedido que está sendo montado (ou editado)
  _itens: [],
  _categoriaId: '',
  _busca: '',

  /* =========================================================== a lista */
  async tela() {
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando pedidos...</div></div>';
    const dados = await Api.get('/api/pedidos', { empresa_id: Estado.empresaId });
    Pedidos._lista = dados;
    const r = dados.resumo;

    alvo.innerHTML = `
      <div class="grade g3" style="margin-bottom:16px">
        <div class="kpi destaque-azul"><div class="kpi-rotulo">Em aberto</div>
          <div class="kpi-valor">${r.abertos}</div>
          <div class="kpi-nota">orçamentos e pedidos esperando</div></div>
        <div class="kpi"><div class="kpi-rotulo">Valor em aberto</div>
          <div class="kpi-valor">${UI.moeda(r.valor_aberto)}</div></div>
        <div class="kpi destaque-verde"><div class="kpi-rotulo">Finalizados</div>
          <div class="kpi-valor">${r.finalizados}</div>
          <div class="kpi-nota">já viraram venda</div></div>
      </div>

      <div class="cartao">
        <div class="cartao-cabecalho espaco">
          <div><h3>Pedidos e orçamentos</h3>
            <div class="mini">o orçamento aprovado vira pedido, com o mesmo número</div></div>
          <div class="espaco">
            <button class="btn" id="btn-novo-orcamento">+ Orçamento</button>
            <button class="btn btn-primario" id="btn-novo-pedido">+ Nova venda</button>
          </div>
        </div>
        <div class="cartao-corpo sem-padding" id="lista-pedidos"></div>
      </div>`;

    alvo.querySelector('#lista-pedidos').innerHTML = UI.tabela({
      colunas: [
        { titulo: 'Nº', valor: (p) => `<b>${UI.escapar(p.numero)}</b>
            <div class="mini">${UI.escapar(p.tipo_rotulo)}</div>` },
        { titulo: 'Data', valor: (p) => UI.data(p.data) },
        { titulo: 'Cliente', valor: (p) => UI.escapar(p.cliente) },
        { titulo: 'Itens', classe: 'centro', valor: (p) => p.itens },
        { titulo: 'Total', classe: 'num', valor: (p) => `<b>${UI.moeda(p.valor_total)}</b>` },
        { titulo: 'Pagamento', valor: (p) => (p.condicao_rotulo
          ? `${UI.escapar(p.condicao_rotulo)}${p.parcelas > 1 ? ` em ${p.parcelas}x` : ''}
             <div class="mini">${UI.escapar(p.documento_rotulo || '')}</div>`
          : '<span class="mini">-</span>') },
        { titulo: 'Situação', classe: 'centro', valor: (p) => {
          const cor = p.situacao === 'FINALIZADO' ? 'tag-pago'
            : p.situacao === 'CANCELADO' ? 'tag-cancelado' : 'tag-aberto';
          return `<span class="tag ${cor}">${UI.escapar(p.situacao_rotulo)}</span>`;
        } },
        { titulo: 'Ações', classe: 'centro', valor: (p, i) => `
            <button class="btn btn-mini" data-abrir="${i}">
              ${p.situacao === 'ABERTO' ? 'Abrir' : 'Ver'}</button>
            ${p.situacao === 'ABERTO'
              ? `<button class="btn btn-mini btn-perigo" data-cancelar="${i}">Cancelar</button>`
              : ''}` },
      ],
      linhas: dados.linhas,
      vazio: 'Nenhum pedido ainda. Clique em "Nova venda" para começar.',
    });

    alvo.querySelector('#btn-novo-pedido').onclick = () => Pedidos.novo('PEDIDO');
    alvo.querySelector('#btn-novo-orcamento').onclick = () => Pedidos.novo('ORCAMENTO');
    alvo.querySelectorAll('[data-abrir]').forEach((b) => {
      b.onclick = () => Pedidos.abrir(dados.linhas[Number(b.dataset.abrir)].id);
    });
    alvo.querySelectorAll('[data-cancelar]').forEach((b) => {
      b.onclick = async () => {
        const p = dados.linhas[Number(b.dataset.cancelar)];
        if (!(await UI.confirmar(`Cancelar o ${p.tipo_rotulo.toLowerCase()} nº ${p.numero}?`,
          'Cancelar pedido'))) return;
        try {
          await Api.post(`/api/pedidos/${p.id}/cancelar`);
          UI.sucesso('Pedido cancelado.');
          Pedidos.tela();
        } catch (e) { UI.erro(e.message); }
      };
    });
  },

  /* ====================================================== a tela de venda */
  novo(tipo) {
    Pedidos._atual = {
      id: null, tipo, numero: null, situacao: 'ABERTO', desconto: 0,
      parceiro_id: '', cliente_nome: '', cliente_documento: '', observacao: '',
      validade: '', data: UI.hoje(),
    };
    Pedidos._itens = [];
    Pedidos._categoriaId = '';
    Pedidos.venda();
  },

  async abrir(id) {
    const dados = await Api.get(`/api/pedidos/${id}`);
    Pedidos._atual = dados.pedido;
    Pedidos._itens = dados.pedido.itens.map((i) => ({ ...i }));
    Pedidos._categoriaId = '';
    Pedidos.venda();
  },

  total() {
    const produtos = Pedidos._itens.reduce(
      (s, i) => s + Math.max(i.quantidade * i.valor_unitario - (i.desconto || 0), 0), 0);
    const desconto = Math.min(Number(Pedidos._atual.desconto) || 0, produtos);
    const cent = (v) => Math.round(v * 100) / 100;
    return { produtos: cent(produtos), desconto, total: cent(produtos - desconto) };
  },

  /** Os produtos que a coluna do meio mostra agora. */
  produtosVisiveis() {
    const termo = (Pedidos._busca || '').toLowerCase();
    return Api.produtosAtivos().filter((p) => {
      if (Pedidos._categoriaId && String(p.categoria_id) !== String(Pedidos._categoriaId)) return false;
      if (termo && !`${p.codigo} ${p.nome}`.toLowerCase().includes(termo)) return false;
      return true;
    });
  },

  venda() {
    const p = Pedidos._atual;
    const t = Pedidos.total();
    const fechado = p.situacao !== 'ABERTO';
    document.getElementById('pagina').innerHTML = `
      <div class="pdv">
        <!-- categorias -->
        <div class="pdv-coluna">
          <div class="pdv-titulo">Categorias</div>
          <div class="pdv-categorias" id="pdv-categorias">
            <button class="pdv-categoria ${!Pedidos._categoriaId ? 'ativa' : ''}" data-cat="">
              Todos os produtos</button>
            ${Api.categoriasAtivas().map((c) => `
              <button class="pdv-categoria ${String(Pedidos._categoriaId) === String(c.id) ? 'ativa' : ''}"
                      data-cat="${c.id}">${UI.escapar(c.nome)}</button>`).join('')}
          </div>
        </div>

        <!-- produtos -->
        <div class="pdv-coluna">
          <div class="pdv-titulo espaco">
            <span>Produtos</span>
            <input id="pdv-busca" placeholder="Procurar..." value="${UI.escapar(Pedidos._busca)}">
          </div>
          <div class="pdv-produtos" id="pdv-produtos"></div>
        </div>

        <!-- carrinho -->
        <div class="pdv-coluna pdv-carrinho">
          <div class="pdv-titulo espaco">
            <span>${UI.escapar(p.tipo === 'ORCAMENTO' ? 'Orçamento' : 'Venda')}
              ${p.numero ? `nº ${UI.escapar(p.numero)}` : '(novo)'}</span>
            ${fechado ? `<span class="tag tag-pago">${UI.escapar(p.situacao_rotulo || '')}</span>` : ''}
          </div>
          <div id="pdv-itens"></div>

          <div class="pdv-cliente linha-campos">
            ${UI.campo('Cliente', UI.select('parceiro_id',
              Api.parceirosPorTipo('CLIENTE').map((c) => ({ valor: c.id, rotulo: c.nome })),
              p.parceiro_id || '', { vazio: 'Consumidor não identificado' }),
              'a nota fiscal precisa do cliente; o cupom aceita sem')}
            ${UI.campo('Desconto no total (R$)',
              `<input name="desconto" inputmode="decimal" value="${p.desconto || ''}">`)}
          </div>

          <div class="pdv-totais">
            <div class="pdv-linha"><span>Subtotal</span><b>${UI.moeda(t.produtos)}</b></div>
            <div class="pdv-linha"><span>Desconto</span><b>${UI.moeda(t.desconto)}</b></div>
            <div class="pdv-total"><span>TOTAL</span><b>${UI.moeda(t.total)}</b></div>
          </div>

          <div class="pdv-acoes">
            ${fechado ? `
              <button class="btn btn-bloco" id="btn-voltar-lista">Voltar para a lista</button>
              ${p.nota_id ? '<button class="btn btn-bloco" id="btn-ver-nota">Ver o documento fiscal</button>' : ''}
              ${p.lancamento_id ? '<button class="btn btn-bloco" id="btn-ver-titulo">Ver as contas a receber</button>' : ''}
            ` : `
              <button class="btn btn-bloco" id="btn-gravar">Gravar</button>
              ${p.tipo === 'ORCAMENTO' && p.id
                ? '<button class="btn btn-bloco btn-verde" id="btn-aprovar">Aprovar orçamento</button>'
                : ''}
              <button class="btn btn-bloco btn-primario" id="btn-finalizar"
                ${Pedidos._itens.length && p.tipo === 'PEDIDO' ? '' : 'disabled'}>
                FINALIZAR</button>
            `}
          </div>
        </div>
      </div>`;

    Pedidos.desenharProdutos();
    Pedidos.desenharItens();
    Pedidos.ligar();
  },

  desenharProdutos() {
    const lista = Pedidos.produtosVisiveis();
    const alvo = document.getElementById('pdv-produtos');
    if (!lista.length) {
      alvo.innerHTML = '<div class="vazio">Nenhum produto nesta categoria.</div>';
      return;
    }
    alvo.innerHTML = lista.map((p, i) => `
      <button class="pdv-produto" data-produto="${i}">
        <div class="pdv-produto-nome">${UI.escapar(p.nome)}</div>
        <div class="mini">${UI.escapar(p.codigo)}${p.marca_nome ? ` · ${UI.escapar(p.marca_nome)}` : ''}</div>
        <div class="pdv-produto-valor">${UI.moeda(p.preco_venda || 0)}</div>
      </button>`).join('');
    alvo.querySelectorAll('[data-produto]').forEach((b) => {
      b.onclick = () => Pedidos.adicionar(lista[Number(b.dataset.produto)]);
    });
  },

  desenharItens() {
    const fechado = Pedidos._atual.situacao !== 'ABERTO';
    document.getElementById('pdv-itens').innerHTML = UI.tabela({
      colunas: [
        { titulo: 'Item', valor: (i) => `${UI.escapar(i.descricao)}
            <div class="mini">${UI.numero(i.quantidade, 0)} ${UI.escapar(i.unidade || '')}
              x ${UI.moeda(i.valor_unitario)}</div>` },
        { titulo: 'Total', classe: 'num',
          valor: (i) => UI.moeda(Math.max(i.quantidade * i.valor_unitario - (i.desconto || 0), 0)) },
        { titulo: '', classe: 'centro', valor: (i, pos) => (fechado ? '' : `
            <button class="btn btn-mini" data-menos="${pos}">−</button>
            <button class="btn btn-mini" data-mais="${pos}">+</button>
            <button class="btn btn-mini btn-perigo" data-tirar="${pos}">x</button>`) },
      ],
      linhas: Pedidos._itens,
      vazio: 'Clique nos produtos para montar a venda.',
    });
    const alvo = document.getElementById('pdv-itens');
    alvo.querySelectorAll('[data-mais]').forEach((b) => {
      b.onclick = () => Pedidos.mudarQuantidade(Number(b.dataset.mais), 1);
    });
    alvo.querySelectorAll('[data-menos]').forEach((b) => {
      b.onclick = () => Pedidos.mudarQuantidade(Number(b.dataset.menos), -1);
    });
    alvo.querySelectorAll('[data-tirar]').forEach((b) => {
      b.onclick = () => { Pedidos._itens.splice(Number(b.dataset.tirar), 1); Pedidos.venda(); };
    });
  },

  /** Clicar de novo no mesmo produto soma quantidade, não repete a linha. */
  adicionar(produto) {
    if (Pedidos._atual.situacao !== 'ABERTO') return;
    const existente = Pedidos._itens.find((i) => i.produto_id === produto.id);
    if (existente) existente.quantidade += 1;
    else {
      Pedidos._itens.push({
        produto_id: produto.id,
        descricao: produto.nome,
        unidade: produto.unidade_comercial || 'UN',
        quantidade: 1,
        valor_unitario: Number(produto.preco_venda || 0),
        desconto: 0,
      });
    }
    Pedidos.venda();
  },

  mudarQuantidade(posicao, passo) {
    const item = Pedidos._itens[posicao];
    if (!item) return;
    item.quantidade = Math.max(0, item.quantidade + passo);
    if (!item.quantidade) Pedidos._itens.splice(posicao, 1);
    Pedidos.venda();
  },

  ligar() {
    const pagina = document.getElementById('pagina');
    pagina.querySelectorAll('[data-cat]').forEach((b) => {
      b.onclick = () => { Pedidos._categoriaId = b.dataset.cat; Pedidos.venda(); };
    });
    const busca = pagina.querySelector('#pdv-busca');
    if (busca) {
      busca.oninput = () => { Pedidos._busca = busca.value; Pedidos.desenharProdutos(); };
    }
    const desconto = pagina.querySelector('[name=desconto]');
    if (desconto) {
      desconto.onchange = () => {
        Pedidos._atual.desconto = Emissao.numero(desconto.value);
        Pedidos.venda();
      };
    }
    const cliente = pagina.querySelector('[name=parceiro_id]');
    if (cliente) cliente.onchange = () => { Pedidos._atual.parceiro_id = cliente.value || null; };

    const ligar = (id, acao) => {
      const botao = pagina.querySelector(id);
      if (botao) botao.onclick = acao;
    };
    ligar('#btn-gravar', () => Pedidos.gravar());
    ligar('#btn-aprovar', () => Pedidos.aprovar());
    ligar('#btn-finalizar', () => Pedidos.finalizar());
    ligar('#btn-voltar-lista', () => Pedidos.tela());
    ligar('#btn-ver-nota', () => App.irPara('/notas'));
    ligar('#btn-ver-titulo', () => App.irPara('/receber'));
  },

  corpo() {
    const p = Pedidos._atual;
    return {
      empresa_id: Estado.empresaId,
      tipo: p.tipo,
      data: p.data || UI.hoje(),
      validade: p.validade || null,
      parceiro_id: p.parceiro_id || null,
      cliente_nome: p.cliente_nome || null,
      cliente_documento: p.cliente_documento || null,
      observacao: p.observacao || null,
      desconto: Number(p.desconto) || 0,
      itens: Pedidos._itens.map((i) => ({
        produto_id: i.produto_id, descricao: i.descricao, unidade: i.unidade,
        quantidade: i.quantidade, valor_unitario: i.valor_unitario, desconto: i.desconto || 0,
      })),
    };
  },

  async gravar(silencioso = false) {
    if (!Pedidos._itens.length) {
      UI.erro('Monte a venda primeiro: clique nos produtos.');
      return null;
    }
    try {
      const r = Pedidos._atual.id
        ? await Api.put(`/api/pedidos/${Pedidos._atual.id}`, Pedidos.corpo())
        : await Api.post('/api/pedidos', Pedidos.corpo());
      Pedidos._atual = r.pedido;
      Pedidos._itens = r.pedido.itens.map((i) => ({ ...i }));
      if (!silencioso) {
        UI.sucesso(r.mensagem);
        Pedidos.venda();
      }
      return r.pedido;
    } catch (e) {
      UI.erro(e.message);
      return null;
    }
  },

  async aprovar() {
    const pedido = await Pedidos.gravar(true);
    if (!pedido) return;
    try {
      const r = await Api.post(`/api/pedidos/${pedido.id}/aprovar`);
      Pedidos._atual = r.pedido;
      UI.sucesso(r.mensagem);
      Pedidos.venda();
    } catch (e) { UI.erro(e.message); }
  },

  /* ================================================= a tela de finalizar */
  async finalizar() {
    const pedido = await Pedidos.gravar(true);
    if (!pedido) return;
    Pedidos.telaFinalizar(pedido);
  },

  telaFinalizar(pedido) {
    const corpo = document.createElement('div');
    const hoje = UI.hoje();
    corpo.innerHTML = `
      <div class="finalizar-total">
        <span>Total do pedido nº ${UI.escapar(pedido.numero)}</span>
        <b>${UI.moeda(pedido.valor_total)}</b>
      </div>

      <h4 class="titulo-bloco">1. Como o cliente paga</h4>
      <div class="escolha-grande">
        <button class="escolha ativa" data-condicao="VISTA">
          <div class="forte">À VISTA</div>
          <div class="mini">recebe agora; não gera conta a receber</div></button>
        <button class="escolha" data-condicao="PRAZO">
          <div class="forte">A PRAZO</div>
          <div class="mini">gera as parcelas em Contas a Receber</div></button>
      </div>

      <div class="linha-campos" style="margin-top:12px">
        ${UI.campo('Forma de pagamento', UI.select('forma_pagamento', [
          { valor: '01', rotulo: 'Dinheiro' },
          { valor: '03', rotulo: 'Cartão de crédito' },
          { valor: '04', rotulo: 'Cartão de débito' },
          { valor: '17', rotulo: 'Pix' },
          { valor: '15', rotulo: 'Boleto' },
          { valor: '99', rotulo: 'Outros' },
        ], '01', { vazio: false }))}
      </div>

      <div id="bloco-prazo" class="oculto">
        <div class="linha-campos">
          ${UI.campo('Parcelas', '<input type="number" name="parcelas" min="1" max="36" value="2">')}
          ${UI.campo('1º vencimento', `<input type="date" name="primeiro_vencimento" value="${hoje}">`)}
          ${UI.campo('Intervalo', UI.select('intervalo_dias', [
            { valor: '30', rotulo: 'Mensal (30/60/90)' },
            { valor: '15', rotulo: 'Quinzenal' },
            { valor: '7', rotulo: 'Semanal' },
          ], '30', { vazio: false }))}
        </div>
        <div id="previa-parcelas" class="previa-parcelas"></div>
      </div>

      <h4 class="titulo-bloco">2. Que documento sai</h4>
      <div class="escolha-grande">
        <button class="escolha ativa" data-documento="CUPOM">
          <div class="forte">CUPOM FISCAL</div>
          <div class="mini">NFC-e — balcão, consumidor final, dentro do estado</div></button>
        <button class="escolha" data-documento="NFE">
          <div class="forte">NOTA FISCAL</div>
          <div class="mini">NF-e — para empresa ou fora do estado; exige o cliente cadastrado</div></button>
      </div>

      <div class="linha-campos" style="margin-top:12px">
        ${UI.campo('Ambiente', UI.select('ambiente', [
          { valor: '2', rotulo: 'Homologação (teste)' },
          { valor: '1', rotulo: 'Produção (vale de verdade)' },
        ], '2', { vazio: false }), 'em produção o documento vale de verdade')}
        <label class="campo" style="grid-column:span 2">
          <span>Confirmação</span>
          <span><input type="checkbox" name="confirmo_producao">
            <span class="mini">confirmo a emissão em produção</span></span>
        </label>
      </div>`;

    let condicao = 'VISTA';
    let documento = 'CUPOM';

    const marcar = (seletor, atributo, valor) => {
      corpo.querySelectorAll(`[${atributo}]`).forEach((b) => {
        b.classList.toggle('ativa', b.getAttribute(atributo) === valor);
      });
    };

    const atualizarPrazo = async () => {
      const bloco = corpo.querySelector('#bloco-prazo');
      bloco.classList.toggle('oculto', condicao !== 'PRAZO');
      if (condicao !== 'PRAZO') return;
      const d = UI.lerFormulario(corpo);
      try {
        // a conta das parcelas é do servidor: o que aparece aqui é exatamente o
        // que vira duplicata e conta a receber, centavo por centavo
        const r = await Api.post(`/api/pedidos/${pedido.id}/parcelas`, {
          condicao: 'PRAZO', parcelas: Number(d.parcelas) || 1,
          primeiro_vencimento: d.primeiro_vencimento,
          intervalo_dias: Number(d.intervalo_dias) || 30,
          documento,
        });
        corpo.querySelector('#previa-parcelas').innerHTML = `
          <div class="mini" style="margin-bottom:6px">As parcelas ficam assim:</div>
          ${r.parcelas.map((p) => `<div class="previa-linha">
            <span>${UI.escapar(p.numero)} · ${UI.data(p.vencimento)}</span>
            <b>${UI.moeda(p.valor)}</b></div>`).join('')}
          <div class="previa-linha forte"><span>Soma</span><b>${UI.moeda(r.total)}</b></div>`;
      } catch (e) {
        corpo.querySelector('#previa-parcelas').innerHTML =
          `<div class="mini alerta">${UI.escapar(e.message)}</div>`;
      }
    };

    corpo.querySelectorAll('[data-condicao]').forEach((b) => {
      b.onclick = () => {
        condicao = b.dataset.condicao;
        marcar('[data-condicao]', 'data-condicao', condicao);
        atualizarPrazo();
      };
    });
    corpo.querySelectorAll('[data-documento]').forEach((b) => {
      b.onclick = () => {
        documento = b.dataset.documento;
        marcar('[data-documento]', 'data-documento', documento);
      };
    });
    ['parcelas', 'primeiro_vencimento', 'intervalo_dias'].forEach((nome) => {
      const campo = corpo.querySelector(`[name="${nome}"]`);
      if (campo) campo.onchange = atualizarPrazo;
    });

    UI.abrirModal({
      titulo: 'Finalizar venda',
      corpo,
      largo: true,
      botoes: [
        { rotulo: 'Voltar', acao: () => UI.tentarFecharModal() },
        {
          rotulo: 'Confirmar venda',
          classe: 'btn-primario',
          acao: async () => {
            const d = UI.lerFormulario(corpo);
            try {
              const r = await Api.post(`/api/pedidos/${pedido.id}/finalizar`, {
                condicao,
                documento,
                forma_pagamento: d.forma_pagamento,
                parcelas: Number(d.parcelas) || 1,
                intervalo_dias: Number(d.intervalo_dias) || 30,
                primeiro_vencimento: d.primeiro_vencimento || null,
                ambiente: d.ambiente,
                confirmo_producao: Boolean(d.confirmo_producao),
              });
              Pedidos._atual = r.pedido;
              Pedidos._itens = r.pedido.itens.map((i) => ({ ...i }));
              if (r.ok) {
                UI.fecharModal();
                UI.sucesso(r.mensagem);
              } else {
                // a venda não se perde: o pedido continua aberto para corrigir
                UI.erro(r.mensagem);
              }
              Pedidos.venda();
            } catch (e) { UI.erro(e.message); }
          },
        },
      ],
    });
  },
};
