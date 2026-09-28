/* Formação do preço de venda — o markup e a conta que o gera.

   A tela existe porque quase todo mundo forma preço errado do mesmo jeito: pega
   o custo e soma a margem que quer ganhar. Imposto, comissão e cartão saem do
   PREÇO, não do custo, então somar 20% ao custo não dá 20% de lucro — dá bem
   menos, e às vezes dá prejuízo.

   A conta certa está em backend/precificacao.py e é a única: esta tela não
   calcula nada por conta própria, para o número que aparece aqui e o número
   gravado no produto nunca divergirem. Cada mudança de campo chama o servidor.

   Nada é gravado sozinho. Há dois botões, e eles fazem coisas diferentes de
   propósito: "Salvar os percentuais" guarda o estudo, "Usar este preço" muda o
   que o balcão vai cobrar. */
const Precos = {
  _produto: null,
  _dados: null,
  _calculando: false,

  /* Campos que a tela manda ao servidor a cada mudança. */
  CAMPOS: ['custo_compra', 'outros_custos', 'markup', 'preco_atual',
    'perc_icms', 'perc_pis', 'perc_cofins', 'perc_ipi', 'perc_simples',
    'perc_despesas', 'perc_comissao', 'perc_cartao', 'perc_frete', 'perc_lucro'],

  async abrir(produto) {
    Precos._produto = produto;
    try {
      Precos._dados = await Api.get('/api/precificacao', {
        empresa_id: Estado.empresaId, produto_id: produto.id,
      });
    } catch (e) {
      return UI.erro(e.message);
    }
    UI.abrirModal({
      titulo: `Formação do preço — ${produto.nome}`,
      largo: true,
      corpo: Precos.corpo(),
      botoes: [
        { rotulo: 'Salvar os percentuais', acao: () => Precos.gravar(false) },
        { rotulo: 'Usar este preço', classe: 'btn-primario',
          acao: () => Precos.gravar(true) },
      ],
    });
    Precos.ligar();
  },

  /* ----------------------------------------------------------------- corpo */
  corpo() {
    const e = Precos._dados.estado;
    return `
      <div class="mini" style="margin-bottom:10px">
        O preço sai do custo dividido pelo que <b>não</b> é seu: imposto, comissão,
        cartão, frete e despesa fixa saem de dentro do preço de venda, não do custo.
        Por isso somar o lucro ao custo não dá o lucro desejado.
      </div>

      <div class="secao-campos"><b>Custo</b><span class="mini"> — o que a mercadoria
        custa por unidade</span></div>
      <div class="linha-campos">
        ${UI.campo('Custo de compra (reposição)',
          `<input type="number" step="0.000001" name="custo_compra" value="${e.custo_compra}">`,
          'o que custa comprar hoje; em branco usa o custo médio')}
        ${UI.campo('Custo médio do estoque',
          `<input type="number" value="${e.custo_medio}" disabled>`,
          'mantido pelo controle de estoque')}
        ${UI.campo('Outros custos por unidade',
          `<input type="number" step="0.000001" name="outros_custos" value="${e.outros_custos}">`,
          'embalagem, rótulo — em reais, não em %')}
      </div>

      <div class="secao-campos"><b>Impostos</b><span class="mini"> — ${e.simples
        ? 'empresa do Simples Nacional: vale a alíquota do DAS, não o ICMS/PIS/COFINS do cadastro'
        : 'as alíquotas do cadastro fiscal do produto'}</span></div>
      <div class="linha-campos">
        ${e.simples
          ? UI.campo('Simples Nacional (DAS) %',
              `<input type="number" step="0.01" name="perc_simples" value="${e.perc_simples}">`,
              'o percentual que a empresa paga na guia')
          : `${UI.campo('ICMS %', `<input type="number" step="0.01" name="perc_icms" value="${e.perc_icms}">`)}
             ${UI.campo('PIS %', `<input type="number" step="0.01" name="perc_pis" value="${e.perc_pis}">`)}
             ${UI.campo('COFINS %', `<input type="number" step="0.01" name="perc_cofins" value="${e.perc_cofins}">`)}`}
        ${UI.campo('IPI %', `<input type="number" step="0.01" name="perc_ipi" value="${e.perc_ipi}">`,
          'por fora: soma ao preço, não come a margem')}
      </div>

      <div class="secao-campos"><b>Custos da venda e lucro</b><span class="mini">
        — percentuais sobre o preço de venda</span></div>
      <div class="linha-campos">
        ${UI.campo('Comissão %', `<input type="number" step="0.01" name="perc_comissao" value="${e.perc_comissao}">`)}
        ${UI.campo('Taxa de cartão %', `<input type="number" step="0.01" name="perc_cartao" value="${e.perc_cartao}">`)}
        ${UI.campo('Frete %', `<input type="number" step="0.01" name="perc_frete" value="${e.perc_frete}">`)}
        ${UI.campo('Despesa fixa %', `<input type="number" step="0.01" name="perc_despesas" value="${e.perc_despesas}">`,
          'aluguel, energia e salários rateados')}
        ${UI.campo('Lucro desejado %', `<input type="number" step="0.01" name="perc_lucro" value="${e.perc_lucro}">`,
          'sobre o preço, não sobre o custo')}
      </div>

      <div class="secao-campos"><b>Markup</b><span class="mini"> — o índice que
        multiplica o custo. Em branco (ou zero), sai da conta acima; preenchido,
        manda na conta</span></div>
      <div class="linha-campos">
        ${UI.campo('Markup', `<input type="number" step="0.0001" name="markup" value="${e.markup}">`,
          'ex.: 1,80 = custo x 1,80')}
        ${UI.campo('Preço praticado hoje',
          `<input type="number" step="0.01" name="preco_atual" value="${e.preco_atual}">`,
          'para comparar com o sugerido')}
        <label class="campo" style="align-self:end">
          <span class="mini">&nbsp;</span>
          <button type="button" class="btn" id="btn-limpar-markup">Tirar o markup fixo</button>
        </label>
      </div>

      <div id="resultado-preco">${Precos.resultado()}</div>`;
  },

  /* ------------------------------------------------------------ resultado */
  resultado() {
    const c = Precos._dados.calculo;
    const e = Precos._dados.estado;
    const composicao = c.composicao || [];
    return `
      <div class="grade g4" style="margin:14px 0 10px">
        ${Precos.cartao('Custo total', UI.moeda(c.custo.custo_total),
          c.custo.origem + (c.custo.outros_custos ? ' + outros custos' : ''))}
        ${Precos.cartao('Markup', c.markup ? UI.numero(c.markup, 4) : '—',
          c.markup_digitado ? 'digitado à mão' : `${UI.numero(c.soma, 2)}% saem do preço`,
          'azul')}
        ${Precos.cartao('Preço sugerido', UI.moeda(c.preco),
          c.perc_ipi ? `com IPI: ${UI.moeda(c.preco_com_ipi)}` : 'por unidade', 'verde')}
        ${Precos.cartao('Lucro', UI.moeda(c.lucro_valor),
          `${UI.numero(c.lucro_percentual, 2)}% do preço`,
          c.lucro_valor < 0 ? 'vermelho' : '')}
      </div>

      ${(c.avisos || []).length ? `<div class="aviso-caixa">
        <ul class="lista-simples">${c.avisos.map((a) => `<li>${UI.escapar(a)}</li>`).join('')}</ul>
      </div>` : ''}

      <div class="linha-campos">
        <div style="flex:1;min-width:320px">
          <b class="mini">Para onde vai cada real do preço</b>
          ${UI.tabela({
            vazio: 'Preencha o custo para a conta aparecer.',
            colunas: [
              { titulo: 'Item', chave: 'rotulo', valor: (l) => UI.escapar(l.rotulo) },
              { titulo: '%', classe: 'direita', valor: (l) => `${UI.numero(l.percentual, 2)}%` },
              { titulo: 'Valor', classe: 'direita', chave: 'valor',
                valor: (l) => `<span class="${l.valor < 0 ? 'negativo' : ''}">${UI.moeda(l.valor)}</span>` },
            ],
            linhas: composicao,
            rodape: composicao.length ? {
              rotulo: '<b>Preço de venda</b>',
              valor: `<b>${UI.moeda(c.preco)}</b>`,
            } : null,
          })}
        </div>
        <div style="flex:1;min-width:280px">
          <b class="mini">O preço de hoje</b>
          ${c.atual ? `
            <div class="tabela-wrap"><table>
              <tr><td>Preço praticado</td><td class="direita">${UI.moeda(c.atual.preco)}</td></tr>
              <tr><td>Markup desse preço</td><td class="direita">${UI.numero(c.atual.markup, 4)}</td></tr>
              <tr><td>Sobra de lucro</td><td class="direita ${c.atual.lucro_valor < 0 ? 'negativo' : ''}">
                <b>${UI.moeda(c.atual.lucro_valor)}</b>
                <div class="mini">${UI.numero(c.atual.lucro_percentual, 2)}% do preço</div></td></tr>
              <tr><td>Diferença para o sugerido</td><td class="direita">
                ${UI.moeda(c.atual.diferenca)}</td></tr>
            </table></div>`
            : '<div class="mini">Informe o preço praticado hoje para comparar.</div>'}
          ${e.simples ? '' : `<div class="mini" style="margin-top:10px">
            O custo médio é o valor da nota de entrada. Empresa de regime normal que se
            credita do ICMS da compra tem custo real menor — nesse caso informe o custo
            líquido no campo Custo de compra.</div>`}
        </div>
      </div>`;
  },

  cartao(titulo, valor, dica, cor = '') {
    return `<div class="kpi ${cor ? `destaque-${cor}` : ''}">
      <div class="kpi-rotulo">${UI.escapar(titulo)}</div>
      <div class="kpi-valor" ${cor ? `style="color:var(--${cor})"` : ''}>${UI.escapar(String(valor))}</div>
      <div class="kpi-nota">${UI.escapar(dica)}</div></div>`;
  },

  /* ---------------------------------------------------------------- ações */
  ligar() {
    const corpo = document.getElementById('modal-corpo');
    // `change` e não `input`: recalcular a cada tecla digitada mandaria uma
    // chamada por dígito, e o número piscaria enquanto a pessoa ainda escreve
    Precos.CAMPOS.forEach((nome) => {
      const campo = corpo.querySelector(`[name="${nome}"]`);
      if (campo) campo.onchange = () => Precos.calcular();
    });
    const limpar = corpo.querySelector('#btn-limpar-markup');
    if (limpar) {
      limpar.onclick = () => {
        const campo = corpo.querySelector('[name=markup]');
        if (campo) campo.value = 0;
        Precos.calcular();
      };
    }
  },

  lerCampos() {
    const corpo = document.getElementById('modal-corpo');
    const dados = { empresa_id: Estado.empresaId, produto_id: Precos._produto.id };
    Precos.CAMPOS.forEach((nome) => {
      const campo = corpo.querySelector(`[name="${nome}"]`);
      if (campo) dados[nome] = Number(campo.value || 0);
    });
    return dados;
  },

  async calcular() {
    if (Precos._calculando) return;
    Precos._calculando = true;
    try {
      Precos._dados = await Api.post('/api/precificacao', Precos.lerCampos());
      document.getElementById('resultado-preco').innerHTML = Precos.resultado();
      UI.modalComEdicao();
    } catch (e) {
      UI.erro(e.message);
    } finally {
      Precos._calculando = false;
    }
  },

  async gravar(usarPreco) {
    const dados = Precos.lerCampos();
    if (usarPreco) {
      const preco = Precos._dados.calculo.preco;
      if (!preco) {
        return UI.erro('Não há preço sugerido para usar — confira o custo e os percentuais.');
      }
      dados.preco_venda = preco;
    }
    try {
      const r = await Api.put('/api/precificacao', dados);
      Precos._dados = r;
      UI.modalSalvo();
      UI.fecharModal();
      UI.sucesso(r.mensagem);
      await Api.carregarCache(true);
      App.recarregar();
    } catch (e) {
      UI.erro(e.message);
    }
  },
};
