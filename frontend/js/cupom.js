/* Cupom fiscal (NFC-e): a tela do balcão.

   É o oposto da tela de NF-e. Lá a nota é montada com calma, em cinco etapas,
   porque cada campo importa. Aqui o consumidor está esperando: escolhe o
   produto, a quantidade, o pagamento e pronto — uma tela só, e o cupom sai
   impresso. Por isso a venda é uma chamada só ao servidor. */
const Cupom = {
  _itens: [],
  _config: null,

  async tela() {
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';
    try {
      Cupom._config = await Api.get('/api/cupom/config', { empresa_id: Estado.empresaId });
    } catch (e) {
      alvo.innerHTML = `<div class="cartao"><div class="vazio">${UI.escapar(e.message)}</div></div>`;
      return;
    }
    Cupom._itens = [];
    Cupom.desenhar();
  },

  /** O que ainda falta para o cupom sair — dito antes de a pessoa digitar a venda. */
  pendencias() {
    const c = Cupom._config || {};
    const falta = [];
    if (!c.uf_atendida) {
      falta.push(`o cupom ainda não está ligado à SEFAZ de ${c.uf || 'sua UF'} `
        + `(hoje: ${(c.ufs_com_cupom || []).join(', ')})`);
    }
    if (!c.tem_csc_homologacao && !c.tem_csc_producao) {
      falta.push('o CSC da empresa (Cadastros > Cupom fiscal)');
    }
    return falta;
  },

  desenhar() {
    const falta = Cupom.pendencias();
    const total = Cupom.total();
    document.getElementById('pagina').innerHTML = `
      ${falta.length ? `<div class="cartao" style="margin-bottom:12px;
        border-left:4px solid var(--ambar)"><div class="cartao-corpo">
        <b>Dá para montar a venda, mas ainda não dá para emitir.</b>
        <div class="mini">Falta: ${falta.map((f) => UI.escapar(f)).join(' · ')}</div>
        <button class="btn btn-mini" id="btn-config-cupom" style="margin-top:8px">
          Abrir a configuração do cupom</button>
        </div></div>` : ''}

      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Nova venda</h3>
            <div class="mini">o cupom vale para consumidor final, dentro do estado</div></div>
          <div class="espaco">
            ${UI.select('ambiente', [
              { valor: '2', rotulo: 'Homologação (teste)' },
              { valor: '1', rotulo: 'Produção (vale de verdade)' },
            ], Cupom._ambiente || '2', { vazio: false })}
          </div>
        </div>
        <div class="cartao-corpo">
          <div class="linha-campos">
            ${UI.campo('Produto', UI.select('produto_id',
              Api.produtosAtivos().map((p) => ({ valor: p.id, rotulo: `${p.codigo} — ${p.nome}` })),
              '', { vazio: 'Escolha o produto' }))}
            ${UI.campo('Quantidade', '<input name="quantidade" inputmode="decimal" value="1">')}
            ${UI.campo('Valor unitário', '<input name="valor_unitario" inputmode="decimal" value="">')}
            ${UI.campo('Desconto', '<input name="desconto" inputmode="decimal" value="">')}
            <label class="campo" style="justify-content:flex-end">
              <button class="btn btn-primario" id="btn-add-item">Adicionar item</button>
            </label>
          </div>

          <div id="itens-cupom" style="margin-top:12px"></div>

          <div class="linha-campos" style="margin-top:14px">
            ${UI.campo('Forma de pagamento', UI.select('forma', [
              { valor: '01', rotulo: 'Dinheiro' },
              { valor: '03', rotulo: 'Cartão de crédito' },
              { valor: '04', rotulo: 'Cartão de débito' },
              { valor: '17', rotulo: 'Pix' },
              { valor: '99', rotulo: 'Outros' },
            ], '01', { vazio: false }))}
            ${UI.campo('Valor recebido', '<input name="recebido" inputmode="decimal">',
              'em dinheiro, para calcular o troco')}
            ${UI.campo('CPF/CNPJ na nota', '<input name="consumidor_documento" inputmode="numeric">',
              'opcional — em branco sai sem identificação')}
            ${UI.campo('Nome do consumidor', '<input name="consumidor_nome">', 'opcional')}
          </div>

          <div class="espaco" style="justify-content:space-between;margin-top:14px">
            <div>
              <div class="mini">Total da venda</div>
              <div style="font-size:26px;font-weight:700">${UI.moeda(total)}</div>
              <div class="mini" id="troco-cupom"></div>
            </div>
            <div class="espaco">
              <button class="btn" id="btn-limpar-cupom">Limpar</button>
              <button class="btn btn-primario" id="btn-emitir-cupom"
                ${falta.length || !Cupom._itens.length ? 'disabled' : ''}>Emitir cupom</button>
            </div>
          </div>
        </div>
      </div>

      <div id="ultimos-cupons"></div>`;

    Cupom.desenharItens();
    Cupom.ligar();
  },

  ligar() {
    const pagina = document.getElementById('pagina');
    const config = pagina.querySelector('#btn-config-cupom');
    if (config) config.onclick = () => App.irPara('/cadastros/cupom');
    pagina.querySelector('#btn-add-item').onclick = () => Cupom.adicionar();
    pagina.querySelector('#btn-limpar-cupom').onclick = () => {
      Cupom._itens = [];
      Cupom.desenhar();
    };
    pagina.querySelector('#btn-emitir-cupom').onclick = () => Cupom.emitir();
    pagina.querySelector('[name=ambiente]').onchange = (e) => {
      Cupom._ambiente = e.target.value;
    };
    const recebido = pagina.querySelector('[name=recebido]');
    recebido.oninput = () => Cupom.mostrarTroco();
    // Enter no valor unitário já adiciona o item: no balcão, tirar a mão do
    // teclado para clicar custa tempo
    pagina.querySelector('[name=valor_unitario]').onkeydown = (e) => {
      if (e.key === 'Enter') { e.preventDefault(); Cupom.adicionar(); }
    };
    Cupom.mostrarTroco();
  },

  numero(texto) {
    return Emissao.numero(texto);
  },

  total() {
    return Cupom._itens.reduce((soma, i) => soma + i.valor_total, 0);
  },

  mostrarTroco() {
    const alvo = document.getElementById('troco-cupom');
    if (!alvo) return;
    const recebido = Cupom.numero(
      document.querySelector('[name=recebido]')?.value || 0);
    const troco = recebido - Cupom.total();
    alvo.textContent = recebido && troco >= 0 ? `Troco: ${UI.moeda(troco)}` : '';
  },

  adicionar() {
    const pagina = document.getElementById('pagina');
    const id = pagina.querySelector('[name=produto_id]').value;
    const produto = Api.produtosAtivos().find((p) => String(p.id) === String(id));
    if (!produto) return UI.erro('Escolha o produto.');
    const quantidade = Cupom.numero(pagina.querySelector('[name=quantidade]').value) || 1;
    const unitario = Cupom.numero(pagina.querySelector('[name=valor_unitario]').value);
    const desconto = Cupom.numero(pagina.querySelector('[name=desconto]').value);
    if (unitario <= 0) return UI.erro('Digite o valor unitário do produto.');
    Cupom._itens.push({
      produto_id: produto.id,
      descricao: produto.nome,
      quantidade,
      valor_unitario: unitario,
      desconto,
      valor_total: Math.round((quantidade * unitario - desconto) * 100) / 100,
    });
    Cupom.desenhar();
    document.querySelector('[name=produto_id]')?.focus();
  },

  desenharItens() {
    const alvo = document.getElementById('itens-cupom');
    if (!alvo) return;
    if (!Cupom._itens.length) {
      alvo.innerHTML = '<div class="vazio">Nenhum item na venda ainda.</div>';
      return;
    }
    alvo.innerHTML = UI.tabela({
      colunas: [
        { titulo: '#', classe: 'centro', valor: (_i, n) => n + 1 },
        { titulo: 'Produto', valor: (i) => UI.escapar(i.descricao) },
        { titulo: 'Qtd', classe: 'num', valor: (i) => UI.numero(i.quantidade, 3) },
        { titulo: 'Valor unit.', classe: 'num', valor: (i) => UI.moeda(i.valor_unitario) },
        { titulo: 'Desconto', classe: 'num', valor: (i) => UI.moeda(i.desconto, false) },
        { titulo: 'Total', classe: 'num', valor: (i) => `<b>${UI.moeda(i.valor_total)}</b>` },
        { titulo: '', classe: 'centro',
          valor: (_i, n) => `<button class="btn btn-mini btn-perigo" data-tirar="${n}">Tirar</button>` },
      ],
      linhas: Cupom._itens,
    });
    alvo.querySelectorAll('[data-tirar]').forEach((b) => {
      b.onclick = () => {
        Cupom._itens.splice(Number(b.dataset.tirar), 1);
        Cupom.desenhar();
      };
    });
  },

  async emitir() {
    const pagina = document.getElementById('pagina');
    const botao = pagina.querySelector('#btn-emitir-cupom');
    const ambiente = pagina.querySelector('[name=ambiente]').value;
    const total = Cupom.total();
    const recebido = Cupom.numero(pagina.querySelector('[name=recebido]').value);
    const forma = pagina.querySelector('[name=forma]').value;

    if (ambiente === '1' && !confirm(
      'Este cupom vai para PRODUÇÃO e passa a valer de verdade. Confirma?')) return;

    botao.disabled = true;
    botao.textContent = 'Falando com a SEFAZ...';
    try {
      const r = await Api.post('/api/cupom/venda', {
        empresa_id: Estado.empresaId,
        ambiente,
        itens: Cupom._itens.map((i) => ({
          produto_id: i.produto_id, quantidade: i.quantidade,
          valor_unitario: i.valor_unitario, desconto: i.desconto,
        })),
        pagamentos: [{ codigo: forma, valor: forma === '01' && recebido > total
          ? total : (recebido || total) }],
        troco: forma === '01' && recebido > total ? recebido - total : 0,
        consumidor_documento: pagina.querySelector('[name=consumidor_documento]').value,
        consumidor_nome: pagina.querySelector('[name=consumidor_nome]').value,
        confirmo_producao: ambiente === '1',
      });
      if (!r.ok) {
        botao.disabled = false;
        botao.textContent = 'Emitir cupom';
        return Emissao.painelRecusa(r.nota || {}, r.erro, 'transmitir');
      }
      UI.sucesso(r.mensagem);
      Cupom._itens = [];
      Cupom.desenhar();
      Cupom.imprimir(r.cupom_id);
    } catch (e) {
      UI.erro(e.message);
      botao.disabled = false;
      botao.textContent = 'Emitir cupom';
    }
  },

  /** Abre o cupom numa aba nova, já no tamanho da bobina, com o botão imprimir. */
  async imprimir(cupomId) {
    const aba = window.open('', '_blank');
    try {
      const resposta = await fetch(`/api/cupom/${cupomId}/impressao`, {
        headers: Estado.token ? { Authorization: `Bearer ${Estado.token}` } : {},
      });
      const texto = await resposta.text();
      if (!resposta.ok) {
        if (aba) aba.close();
        let corpo = {};
        try { corpo = JSON.parse(texto); } catch { corpo = {}; }
        throw new Error(corpo.detail || 'Não foi possível montar o cupom.');
      }
      if (!aba) return UI.erro('O navegador bloqueou a aba nova. Libere as janelas deste site.');
      aba.document.open();
      aba.document.write(texto);
      aba.document.close();
    } catch (e) {
      UI.erro(e.message);
    }
  },
};
