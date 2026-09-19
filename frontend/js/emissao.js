/* Emissão de NF-e — a nota que a sua empresa emite e manda para a SEFAZ.

   Fluxo: rascunho -> conferir na prévia -> transmitir -> autorizada.
   Rascunho não gasta número da série; o número só é usado na transmissão.
   Nota autorizada não se apaga: se precisar, cancela na SEFAZ (com justificativa).

   A tela é dividida em etapas curtas, uma por vez, como o contrato: no celular
   cabe na mão, no computador as etapas viram uma trilha no alto. Quantidade e
   valor são campos de texto livre (aceitam vírgula) e a lista não se redesenha
   enquanto você digita — só o total é recalculado. */
const Emissao = {
  ETAPAS: [
    { id: 'nota', rotulo: 'Nota' },
    { id: 'itens', rotulo: 'Itens' },
    { id: 'pagamento', rotulo: 'Pagamento' },
    { id: 'transporte', rotulo: 'Transporte' },
    { id: 'conferir', rotulo: 'Conferir e enviar' },
  ],

  /** Lê número digitado à vontade: "1.320,50", "1320.50" ou "1320". */
  numero(texto) {
    if (typeof texto === 'number') return texto;
    const limpo = String(texto ?? '').trim().replace(/\s/g, '');
    if (!limpo) return 0;
    // com vírgula, ela é a decimal e o ponto é separador de milhar (1.320,55)
    // sem vírgula, ponto em grupos de 3 também é milhar (1.320 é mil trezentos e vinte)
    // e só sobra o jeito americano (1320.55)
    let normalizado = limpo;
    if (limpo.includes(',')) {
      normalizado = limpo.replace(/\./g, '').replace(',', '.');
    } else if (/^-?\d{1,3}(\.\d{3})+$/.test(limpo)) {
      normalizado = limpo.replace(/\./g, '');
    }
    const valor = Number(normalizado);
    return Number.isFinite(valor) ? valor : 0;
  },

  /* Abre o formulário de uma nota nova (ou de um rascunho já existente). */
  async abrir(notaId, contratoId) {
    const preparo = await Api.get('/api/nfe/preparo', { empresa_id: Estado.empresaId });
    // nota nova só começa com o cadastro completo; rascunho já existente sempre abre
    if (!preparo.pronto && !notaId) return Emissao.pendencias(preparo);

    let dados = null;
    if (notaId) {
      dados = await Api.get(`/api/nfe/${notaId}`);
    } else {
      dados = await Api.post('/api/nfe/rascunho', {
        empresa_id: Estado.empresaId,
        contrato_id: contratoId || null,
        ambiente: preparo.ambiente_certificado || '2',
      });
      UI.sucesso('Rascunho criado. Preencha e transmita quando estiver certo.');
    }
    Emissao.formulario(dados, preparo);
  },

  pendencias(preparo) {
    UI.abrirModal({
      titulo: 'Ainda falta cadastrar para emitir nota',
      corpo: `
        <p class="mini" style="margin-top:0">A SEFAZ exige estes dados. Complete e volte aqui:</p>
        <ul>${preparo.pendencias.map((p) => `<li>${UI.escapar(p)}</li>`).join('')}</ul>`,
      botoes: [
        { rotulo: 'Fechar', acao: UI.fecharModal },
        { rotulo: 'Ir para Empresas', classe: 'btn-primario',
          acao: () => { UI.fecharModal(); App.irPara('/cadastros/empresas'); } },
      ],
    });
  },

  /* ============================================================= FORMULÁRIO */
  formulario(dados, preparo, etapaInicial = 0) {
    const n = dados.nota;
    const editavel = n.pode_editar;
    Emissao._nota = n;
    Emissao._preparo = preparo;
    Emissao._editavel = editavel;
    Emissao._itens = (dados.itens || []).map((i) => ({ ...i }));
    Emissao._parcelas = (dados.parcelas || []).map((p) => ({ ...p }));
    if (!Emissao._itens.length) Emissao._itens.push(Emissao.itemVazio());

    const paineis = {
      nota: `
        <div class="linha-campos">
          ${UI.campo('Cliente', UI.select('parceiro_id', UI.opcoesParceiros(),
            n.parceiro_id || '', { obrigatorio: true }), 'para quem é a nota')}
          ${UI.campo('Natureza da operação',
            `<input name="natureza_operacao" value="${UI.escapar(n.natureza_operacao || 'VENDA DE MERCADORIA')}">`,
            'sai impresso na DANFE')}
          ${UI.campo('Data de emissão',
            `<input type="date" name="data_emissao" value="${(n.data_emissao || UI.hoje()).slice(0, 10)}">`)}
          ${UI.campo('Série', `<input name="serie" value="${UI.escapar(n.serie || '1')}" inputmode="numeric">`,
            'o número é automático')}
          ${UI.campo('Finalidade', UI.select('finalidade',
            (preparo.finalidades || []).map((f) => ({ valor: f.codigo, rotulo: f.nome })),
            n.finalidade || '1', { vazio: false }))}
          ${UI.campo('Ambiente', UI.select('ambiente', [
            { valor: '2', rotulo: 'Homologação (teste)' },
            { valor: '1', rotulo: 'Produção (vale de verdade)' },
          ], n.ambiente || '2', { vazio: false }), 'comece sempre em homologação')}
        </div>`,

      itens: `
        <div id="itens-nfe"></div>
        ${editavel ? `<button type="button" class="btn" id="btn-add-item"
          style="margin-top:10px">+ Adicionar item</button>` : ''}
        <div class="resumo-contrato" style="margin-top:14px" id="total-itens"></div>`,

      pagamento: `
        <p class="mini" style="margin-top:0">Cada parcela vira uma <b>duplicata</b> na nota.
        Sem parcela, a nota sai como pagamento à vista.</p>
        <div id="parcelas-nfe"></div>
        ${editavel ? `<div class="espaco" style="margin-top:10px">
          <button type="button" class="btn" id="btn-add-parcela">+ Adicionar parcela</button>
          <button type="button" class="btn" id="btn-parcela-unica">Uma parcela com o total</button>
          <button type="button" class="btn" id="btn-dividir">Dividir igualmente</button>
        </div>` : ''}
        <div class="resumo-contrato" style="margin-top:14px" id="total-parcelas"></div>`,

      transporte: `
        <div class="linha-campos">
          ${UI.campo('Frete por conta', UI.select('frete_modalidade',
            (preparo.modalidades_frete || []).map((f) => ({ valor: f.codigo, rotulo: f.nome })),
            n.frete_modalidade || '9', { vazio: false }))}
          ${UI.campo('Transportadora', UI.select('transportadora_id', UI.opcoesParceiros(),
            n.transportadora_id || '', { vazio: 'Nenhuma' }))}
          ${UI.campo('Placa do veículo',
            `<input name="placa_veiculo" value="${UI.escapar(n.placa_veiculo || '')}" maxlength="8">`)}
          ${UI.campo('UF do veículo',
            `<input name="uf_veiculo" value="${UI.escapar(n.uf_veiculo || '')}" maxlength="2">`)}
          ${UI.campo('Volumes',
            `<input name="volumes" inputmode="numeric" value="${n.volumes ?? ''}">`, 'quantidade')}
          ${UI.campo('Espécie',
            `<input name="especie_volume" value="${UI.escapar(n.especie_volume || '')}" placeholder="sacas, caixas...">`)}
          ${UI.campo('Peso líquido (kg)',
            `<input name="peso_liquido" inputmode="decimal" value="${UI.numero(n.peso_liquido || 0, 3)}">`)}
          ${UI.campo('Peso bruto (kg)',
            `<input name="peso_bruto" inputmode="decimal" value="${UI.numero(n.peso_bruto || 0, 3)}">`)}
        </div>`,

      conferir: `
        <div id="conferencia-nfe"></div>
        <h4 class="titulo-bloco" style="margin-top:14px">Informações complementares</h4>
        <div class="linha-campos">
          ${UI.campo('Texto que sai na nota',
            `<textarea name="informacoes_complementares" rows="3">${UI.escapar(n.informacoes_complementares || '')}</textarea>`,
            'contrato, pedido, observações fiscais')}
        </div>`,
    };

    const corpo = document.createElement('div');
    corpo.className = 'formulario-etapas';
    corpo.innerHTML = `
      ${Emissao.faixaPendencias(preparo)}
      ${Emissao.faixaSituacao(n)}
      <div class="etapas" id="barra-etapas-nfe">
        ${Emissao.ETAPAS.map((e, i) => `
          <button type="button" class="etapa" data-etapa="${i}">
            <span class="etapa-numero">${i + 1}</span>
            <span class="etapa-rotulo">${UI.escapar(e.rotulo)}</span>
          </button>`).join('')}
      </div>
      <div class="etapa-progresso"><span id="progresso-nfe"></span></div>
      ${Emissao.ETAPAS.map((e, i) => `
        <section class="painel-etapa ${i ? 'oculto' : ''}" data-painel="${i}">
          <h4 class="titulo-etapa">${i + 1}. ${UI.escapar(e.rotulo)}</h4>
          ${paineis[e.id]}
        </section>`).join('')}`;

    /* ------------------------------------------------------ navegação das etapas */
    let atual = 0;
    const ultima = Emissao.ETAPAS.length - 1;

    const validar = (indice) => {
      if (!editavel) return true;
      if (indice === 0 && !corpo.querySelector('[name=parceiro_id]').value) {
        UI.erro('Escolha o cliente da nota.');
        return false;
      }
      if (indice === 1 && !Emissao.itensValidos().length) {
        UI.erro('Coloque pelo menos um item com quantidade e valor.');
        return false;
      }
      return true;
    };

    const botoes = () => {
      const lista = [];
      if (atual > 0) lista.push({ rotulo: 'Voltar', acao: () => irPara(atual - 1) });
      else lista.push({ rotulo: 'Fechar', acao: () => UI.tentarFecharModal() });

      if (atual < ultima) {
        // salvar dá para fazer em qualquer etapa — não precisa chegar até o fim
        if (editavel) lista.push({ rotulo: 'Salvar', acao: () => Emissao.salvar(n.id, false) });
        lista.push({
          rotulo: 'Próximo',
          classe: 'btn-primario',
          acao: () => { if (validar(atual)) irPara(atual + 1); },
        });
        return lista;
      }
      // última etapa: só o essencial no rodapé — prévia, excluir e cancelar
      // ficam dentro do painel de conferência (no celular o rodapé não pode crescer)
      if (editavel) {
        lista.push({ rotulo: 'Salvar rascunho', acao: () => Emissao.salvar(n.id, false) });
        lista.push({ rotulo: 'Transmitir à SEFAZ', classe: 'btn-primario',
          acao: () => Emissao.salvar(n.id, true) });
      } else {
        lista.push({ rotulo: 'Prévia (DANFE)', classe: 'btn-primario',
          acao: () => Emissao.previa(n.id) });
      }
      return lista;
    };

    const irPara = (indice) => {
      atual = Math.max(0, Math.min(indice, ultima));
      Emissao._etapa = atual;     // para voltar à mesma etapa depois de salvar
      corpo.querySelectorAll('[data-painel]').forEach((p) => {
        p.classList.toggle('oculto', Number(p.dataset.painel) !== atual);
      });
      corpo.querySelectorAll('[data-etapa]').forEach((b) => {
        const i = Number(b.dataset.etapa);
        b.classList.toggle('ativa', i === atual);
        b.classList.toggle('feita', i < atual);
      });
      corpo.querySelector('#progresso-nfe').style.width =
        `${((atual + 1) / (ultima + 1)) * 100}%`;
      corpo.querySelector('.etapa.ativa')?.scrollIntoView(
        { block: 'nearest', inline: 'center', behavior: 'smooth' });
      document.getElementById('modal-corpo').scrollTop = 0;
      if (Emissao.ETAPAS[atual].id === 'conferir') Emissao.desenharConferencia();
      UI.trocarBotoes(botoes(), corpo);
    };

    corpo.querySelectorAll('[data-etapa]').forEach((b) => {
      b.onclick = () => {
        const destino = Number(b.dataset.etapa);
        if (destino > atual && !validar(atual)) return;
        irPara(destino);
      };
    });

    UI.abrirModal({
      titulo: n.numero ? `NF-e ${n.numero} — série ${n.serie}` : 'Nova NF-e (rascunho)',
      corpo,
      largo: true,
      aoSalvar: editavel ? () => Emissao.salvar(n.id, false, true) : null,
      botoes: botoes(),
    });

    Emissao.desenharItens();
    Emissao.desenharParcelas();
    if (editavel) {
      corpo.querySelector('#btn-add-item').onclick = () => {
        Emissao.lerItensDaTela();
        Emissao._itens.push(Emissao.itemVazio());
        Emissao.desenharItens();
      };
      corpo.querySelector('#btn-add-parcela').onclick = () => {
        Emissao.lerParcelasDaTela();
        Emissao._parcelas.push({ vencimento: UI.hoje(), valor: 0 });
        Emissao.desenharParcelas();
      };
      corpo.querySelector('#btn-parcela-unica').onclick = () => {
        Emissao.lerItensDaTela();
        Emissao._parcelas = [{ vencimento: UI.hoje(), valor: Emissao.total() }];
        Emissao.desenharParcelas();
      };
      corpo.querySelector('#btn-dividir').onclick = () => Emissao.dividirParcelas();
    } else {
      corpo.querySelectorAll('input,select,textarea').forEach((c) => { c.disabled = true; });
    }
    Emissao.ligarConserto(corpo, irPara);
    irPara(etapaInicial);
  },

  /* Aviso no alto do formulário quando ainda falta cadastro para transmitir. */
  faixaPendencias(preparo) {
    if (preparo.pronto) return '';
    return `<div class="cartao" style="margin-bottom:12px;border-left:4px solid var(--ambar)">
      <div class="cartao-corpo"><b>Dá para montar a nota, mas ainda não dá para transmitir.</b>
        <div class="mini">Falta: ${preparo.pendencias.map((p) => UI.escapar(p)).join(' · ')}</div>
      </div></div>`;
  },

  /* Onde cada tipo de recusa se conserta — vira o botão de atalho do aviso. */
  CONSERTO: {
    empresa: { rotulo: 'Abrir cadastro da empresa', rota: '/cadastros/empresas' },
    cliente: { rotulo: 'Abrir cadastro de clientes', rota: '/cadastros/parceiros' },
    produto: { rotulo: 'Abrir cadastro de produtos', rota: '/cadastros/produtos' },
    certificado: { rotulo: 'Abrir o certificado digital', rota: '/dfe/certificado' },
    nota: { etapa: 0 },
    itens: { etapa: 1 },
    pagamento: { etapa: 2 },
  },

  /** O aviso que fica na tela: código, frase da SEFAZ, o que é e como arrumar. */
  cartaoErro(erro) {
    if (!erro) return '';
    const conserto = Emissao.CONSERTO[erro.onde];
    const atalho = conserto && conserto.rota
      ? `<button type="button" class="btn btn-mini" data-conserto="${UI.escapar(erro.onde)}"
           style="margin-top:10px">${UI.escapar(conserto.rotulo)}</button>`
      : conserto && conserto.etapa !== undefined
        ? `<button type="button" class="btn btn-mini" data-conserto="${UI.escapar(erro.onde)}"
             style="margin-top:10px">Ir para a etapa do conserto</button>`
        : '';
    return `
      <div class="cartao" style="margin-bottom:12px;border-left:4px solid var(--vermelho)">
        <div class="cartao-corpo">
          <b>${UI.escapar(erro.causa || 'A SEFAZ recusou a nota.')}</b>
          <div style="margin-top:8px">${UI.escapar(erro.corrigir || '')}</div>
          <div class="mini" style="margin-top:10px">
            Resposta da SEFAZ${erro.codigo ? ` — código <b>${UI.escapar(erro.codigo)}</b>` : ''}:
            <i>${UI.escapar(erro.mensagem || '')}</i>
          </div>
          ${erro.denegada ? `<div class="mini" style="margin-top:6px">
            <b>Nota denegada:</b> o número foi consumido e essa nota não pode ser reaproveitada.
            Depois de resolver a pendência, emita outra.</div>` : ''}
          ${erro.detalhe ? `<details style="margin-top:10px">
            <summary class="mini" style="cursor:pointer">Detalhes técnicos (para o suporte)</summary>
            <pre class="mini" style="white-space:pre-wrap;word-break:break-all;margin:6px 0 0;
              max-height:220px;overflow:auto">${UI.escapar(erro.detalhe)}</pre>
          </details>` : ''}
          ${atalho}
        </div></div>`;
  },

  /** Liga os botões de atalho do aviso de erro. */
  ligarConserto(corpo, irPara) {
    corpo.querySelectorAll('[data-conserto]').forEach((botao) => {
      botao.onclick = () => {
        const conserto = Emissao.CONSERTO[botao.dataset.conserto];
        if (!conserto) return;
        if (conserto.rota) {
          UI.fecharModal();
          return App.irPara(conserto.rota);
        }
        if (irPara) irPara(conserto.etapa);
      };
    });
  },

  faixaSituacao(n) {
    const cores = {
      RASCUNHO: 'var(--ambar)', ENVIADA: 'var(--azul)', AUTORIZADA: 'var(--verde)',
      REJEITADA: 'var(--vermelho)', CANCELADA: 'var(--cinza-500)',
    };
    const textos = {
      RASCUNHO: 'Rascunho — ainda não foi para a SEFAZ e não gastou número.',
      ENVIADA: 'Enviada para a SEFAZ, aguardando resposta.',
      AUTORIZADA: 'Autorizada pela SEFAZ. O XML e a DANFE já valem.',
      REJEITADA: 'A SEFAZ não aceitou. Corrija e transmita de novo.',
      CANCELADA: 'Cancelada na SEFAZ.',
    };
    const situacao = n.status_emissao || 'RASCUNHO';
    return `<div class="cartao" style="margin-bottom:12px;border-left:4px solid ${cores[situacao]}">
      <div class="cartao-corpo">
        <b>${UI.escapar(textos[situacao] || situacao)}</b>
        ${n.ambiente === '2' ? '<div class="mini">Ambiente de <b>homologação</b>: a nota não tem valor fiscal.</div>' : ''}
        ${n.protocolo ? `<div class="mini">Protocolo ${UI.escapar(n.protocolo)} · chave ${UI.escapar(n.chave_formatada || '')}</div>` : ''}
      </div></div>
      ${Emissao.cartaoErro(n.erro)}`;
  },

  /* ================================================================== ITENS */
  itemVazio() {
    return { produto_id: '', descricao: '', unidade: '', quantidade: 0, valor_unitario: 0,
             cfop: '', ncm: '', icms_cst: '', desconto: 0 };
  },

  /** Cada item é um cartão: no celular os campos empilham sozinhos. */
  desenharItens() {
    const alvo = document.getElementById('itens-nfe');
    if (!alvo) return;
    const editavel = Emissao._editavel;
    const produtos = Api.produtosAtivos();

    alvo.innerHTML = Emissao._itens.map((item, i) => `
      <div class="cartao item-nota" data-item="${i}" style="margin-bottom:10px">
        <div class="cartao-corpo">
          <div class="espaco" style="justify-content:space-between;margin-bottom:8px">
            <b class="mini">Item ${i + 1}</b>
            ${editavel && Emissao._itens.length > 1
              ? `<button type="button" class="btn btn-mini btn-perigo" data-remover="${i}">Remover</button>`
              : ''}
          </div>
          <div class="linha-campos">
            ${UI.campo('Produto', UI.select(`produto_${i}`,
              produtos.map((p) => ({ valor: p.id, rotulo: `${p.codigo} — ${p.nome}` })),
              item.produto_id || '', { vazio: 'Digitar à mão' }),
              'traz NCM, CFOP e CST do cadastro')}
            ${UI.campo('Descrição',
              `<input data-campo="descricao" data-linha="${i}" value="${UI.escapar(item.descricao || '')}">`)}
            ${UI.campo('Quantidade',
              `<input data-campo="quantidade" data-linha="${i}" inputmode="decimal"
                 value="${UI.escapar(Emissao.mostrar(item.quantidade, 3))}">`,
              'pode usar vírgula')}
            ${UI.campo('Unidade',
              `<input data-campo="unidade" data-linha="${i}" value="${UI.escapar(item.unidade || '')}" placeholder="SC, KG, UN">`)}
            ${UI.campo('Valor unitário',
              `<input data-campo="valor_unitario" data-linha="${i}" inputmode="decimal"
                 value="${UI.escapar(Emissao.mostrar(item.valor_unitario, 4))}">`,
              'pode usar vírgula')}
            ${UI.campo('Desconto',
              `<input data-campo="desconto" data-linha="${i}" inputmode="decimal"
                 value="${UI.escapar(Emissao.mostrar(item.desconto, 2))}">`)}
            ${UI.campo('CFOP',
              `<input data-campo="cfop" data-linha="${i}" inputmode="numeric" value="${UI.escapar(item.cfop || '')}">`)}
            ${UI.campo('NCM',
              `<input data-campo="ncm" data-linha="${i}" inputmode="numeric" value="${UI.escapar(item.ncm || '')}">`)}
          </div>
          <div class="mini" style="margin-top:8px;text-align:right">
            Total do item: <b data-total-item="${i}">${UI.moeda(Emissao.totalItem(item))}</b>
          </div>
        </div>
      </div>`).join('');

    // digitação livre: só recalcula os totais, sem redesenhar (o campo não perde o foco)
    alvo.querySelectorAll('[data-campo]').forEach((campo) => {
      campo.oninput = () => {
        const item = Emissao._itens[Number(campo.dataset.linha)];
        const nome = campo.dataset.campo;
        item[nome] = ['quantidade', 'valor_unitario', 'desconto'].includes(nome)
          ? Emissao.numero(campo.value)
          : campo.value;
        Emissao.atualizarTotais();
      };
    });
    alvo.querySelectorAll('select[name^=produto_]').forEach((select) => {
      select.onchange = () => {
        Emissao.lerItensDaTela();
        const i = Number(select.name.split('_')[1]);
        const produto = produtos.find((p) => String(p.id) === select.value);
        Emissao._itens[i].produto_id = select.value || '';
        if (produto) {
          Object.assign(Emissao._itens[i], {
            descricao: produto.nome,
            unidade: produto.unidade_comercial || Emissao._itens[i].unidade || '',
            cfop: produto.cfop_padrao || '',
            ncm: produto.ncm || '',
            icms_cst: produto.cst_icms || '',
          });
        }
        Emissao.desenharItens();
      };
    });
    alvo.querySelectorAll('[data-remover]').forEach((botao) => {
      botao.onclick = () => {
        Emissao.lerItensDaTela();
        Emissao._itens.splice(Number(botao.dataset.remover), 1);
        if (!Emissao._itens.length) Emissao._itens.push(Emissao.itemVazio());
        Emissao.desenharItens();
      };
    });
    Emissao.atualizarTotais();
  },

  /** Número para mostrar no campo: em branco quando é zero, para não atrapalhar. */
  mostrar(valor, casas) {
    const n = Number(valor || 0);
    if (!n) return '';
    return UI.numero(n, casas).replace(/,?0+$/, (t) => (t.startsWith(',') ? '' : t));
  },

  totalItem(item) {
    return Emissao.numero(item.quantidade) * Emissao.numero(item.valor_unitario)
      - Emissao.numero(item.desconto);
  },

  total() {
    return Emissao._itens.reduce((s, i) => s + Emissao.totalItem(i), 0);
  },

  itensValidos() {
    return Emissao._itens.filter((i) => Emissao.numero(i.quantidade) > 0
      && Emissao.numero(i.valor_unitario) > 0);
  },

  /** Relê o que está digitado (o estado só é atualizado no oninput; isto é a rede de segurança). */
  lerItensDaTela() {
    const alvo = document.getElementById('itens-nfe');
    if (!alvo) return;
    alvo.querySelectorAll('[data-campo]').forEach((campo) => {
      const item = Emissao._itens[Number(campo.dataset.linha)];
      if (!item) return;
      const nome = campo.dataset.campo;
      item[nome] = ['quantidade', 'valor_unitario', 'desconto'].includes(nome)
        ? Emissao.numero(campo.value)
        : campo.value;
    });
  },

  lerParcelasDaTela() {
    const alvo = document.getElementById('parcelas-nfe');
    if (!alvo) return;
    alvo.querySelectorAll('[data-parc]').forEach((campo) => {
      const parcela = Emissao._parcelas[Number(campo.dataset.linha)];
      if (!parcela) return;
      parcela[campo.dataset.parc] = campo.dataset.parc === 'valor'
        ? Emissao.numero(campo.value) : campo.value;
    });
  },

  /** Só os textos de total mudam enquanto se digita — nada é redesenhado. */
  atualizarTotais() {
    const total = Emissao.total();
    Emissao._itens.forEach((item, i) => {
      const alvo = document.querySelector(`[data-total-item="${i}"]`);
      if (alvo) alvo.textContent = UI.moeda(Emissao.totalItem(item));
    });
    const resumo = document.getElementById('total-itens');
    if (resumo) {
      resumo.innerHTML = `<div class="espaco" style="justify-content:space-between">
        <span>${Emissao._itens.length} item(ns)</span>
        <span class="forte">Total da nota: ${UI.moeda(total)}</span></div>`;
    }
    const parcelas = Emissao._parcelas.reduce((s, p) => s + Emissao.numero(p.valor), 0);
    const caixa = document.getElementById('total-parcelas');
    if (caixa) {
      const diferenca = Math.round((total - parcelas) * 100) / 100;
      caixa.innerHTML = `<div class="espaco" style="justify-content:space-between">
        <span>Total da nota: <b>${UI.moeda(total)}</b></span>
        <span>Parcelas: <b>${UI.moeda(parcelas)}</b>${diferenca
          ? ` <span class="negativo">(faltam ${UI.moeda(diferenca)})</span>` : ''}</span></div>`;
    }
  },

  /* ============================================================== PARCELAS */
  desenharParcelas() {
    const alvo = document.getElementById('parcelas-nfe');
    if (!alvo) return;
    const editavel = Emissao._editavel;
    if (!Emissao._parcelas.length) {
      alvo.innerHTML = '<div class="vazio">Sem parcelas — a nota sai como pagamento à vista.</div>';
      Emissao.atualizarTotais();
      return;
    }
    alvo.innerHTML = `<div class="linha-campos">${Emissao._parcelas.map((p, i) => `
      ${UI.campo(`Parcela ${i + 1} — vencimento`,
        `<input type="date" data-parc="vencimento" data-linha="${i}" value="${(p.vencimento || '').slice(0, 10)}">`)}
      ${UI.campo('Valor',
        `<input data-parc="valor" data-linha="${i}" inputmode="decimal"
           value="${UI.escapar(Emissao.mostrar(p.valor, 2))}">`)}
      ${editavel ? `<div class="campo"><span>&nbsp;</span>
        <button type="button" class="btn btn-perigo" data-rem-parc="${i}">Remover</button></div>` : ''}
    `).join('')}</div>`;

    alvo.querySelectorAll('[data-parc]').forEach((campo) => {
      campo.oninput = () => {
        const p = Emissao._parcelas[Number(campo.dataset.linha)];
        p[campo.dataset.parc] = campo.dataset.parc === 'valor'
          ? Emissao.numero(campo.value) : campo.value;
        Emissao.atualizarTotais();
      };
    });
    alvo.querySelectorAll('[data-rem-parc]').forEach((botao) => {
      botao.onclick = () => {
        Emissao.lerParcelasDaTela();
        Emissao._parcelas.splice(Number(botao.dataset.remParc), 1);
        Emissao.desenharParcelas();
      };
    });
    Emissao.atualizarTotais();
  },

  /** Divide o total da nota entre as parcelas já criadas, mês a mês. */
  dividirParcelas() {
    Emissao.lerItensDaTela();
    Emissao.lerParcelasDaTela();
    const quantas = Math.max(1, Emissao._parcelas.length || 1);
    const total = Emissao.total();
    const parcela = Math.floor((total / quantas) * 100) / 100;
    const hoje = new Date();
    Emissao._parcelas = Array.from({ length: quantas }, (_, i) => {
      const vencimento = new Date(hoje.getFullYear(), hoje.getMonth() + i + 1, hoje.getDate());
      const valor = i < quantas - 1
        ? parcela
        : Math.round((total - parcela * (quantas - 1)) * 100) / 100;
      return { vencimento: vencimento.toISOString().slice(0, 10), valor };
    });
    Emissao.desenharParcelas();
  },

  /* ============================================================== CONFERIR */
  desenharConferencia() {
    const alvo = document.getElementById('conferencia-nfe');
    if (!alvo) return;
    Emissao.lerItensDaTela();
    Emissao.lerParcelasDaTela();
    const area = document.getElementById('modal-corpo');
    const dados = UI.lerFormulario(area);
    const cliente = (Estado.cache.parceiros || [])
      .find((p) => String(p.id) === String(dados.parceiro_id));
    const total = Emissao.total();
    const itens = Emissao.itensValidos();
    const parcelas = Emissao._parcelas.filter((p) => p.vencimento && Emissao.numero(p.valor) > 0);

    const avisos = [];
    if (!cliente) avisos.push('Escolha o cliente na etapa Nota.');
    if (!itens.length) avisos.push('Nenhum item com quantidade e valor.');
    if (itens.some((i) => !i.cfop)) avisos.push('Tem item sem CFOP.');
    if (itens.some((i) => !i.ncm)) avisos.push('Tem item sem NCM.');
    if (cliente && !cliente.codigo_municipio) {
      avisos.push(`Falta o código do município no cadastro de ${cliente.nome}.`);
    }
    const soma = parcelas.reduce((s, p) => s + Emissao.numero(p.valor), 0);
    if (parcelas.length && Math.abs(soma - total) > 0.01) {
      avisos.push(`As parcelas somam ${UI.moeda(soma)} e a nota é de ${UI.moeda(total)}.`);
    }

    alvo.innerHTML = `
      <div class="grade g3" style="margin-bottom:12px">
        <div class="kpi"><div class="kpi-rotulo">Cliente</div>
          <div class="kpi-valor" style="font-size:16px">${UI.escapar(cliente ? cliente.nome : '—')}</div>
          <div class="kpi-nota">${UI.escapar((cliente && cliente.cpf_cnpj) || '')}</div></div>
        <div class="kpi"><div class="kpi-rotulo">Total da nota</div>
          <div class="kpi-valor">${UI.moeda(total)}</div>
          <div class="kpi-nota">${itens.length} item(ns) · ${parcelas.length || 'sem'} parcela(s)</div></div>
        <div class="kpi ${dados.ambiente === '1' ? 'destaque-vermelho' : 'destaque-ambar'}">
          <div class="kpi-rotulo">Ambiente</div>
          <div class="kpi-valor" style="font-size:16px">${dados.ambiente === '1' ? 'Produção' : 'Homologação'}</div>
          <div class="kpi-nota">série ${UI.escapar(dados.serie || '1')}</div></div>
      </div>
      ${avisos.length ? `<div class="cartao" style="border-left:4px solid var(--ambar);margin-bottom:12px">
        <div class="cartao-corpo"><b>Confira antes de transmitir:</b>
          <ul style="margin:6px 0 0">${avisos.map((a) => `<li class="mini">${UI.escapar(a)}</li>`).join('')}</ul>
        </div></div>` : ''}
      ${UI.tabela({
        vazio: 'Sem itens.',
        colunas: [
          { titulo: 'Produto', valor: (i) => `${UI.escapar(i.descricao || '-')}
              <div class="mini">NCM ${UI.escapar(i.ncm || '-')} · CFOP ${UI.escapar(i.cfop || '-')}</div>` },
          { titulo: 'Qtde', classe: 'num',
            valor: (i) => `${UI.numero(Emissao.numero(i.quantidade), 3)} ${UI.escapar(i.unidade || '')}` },
          { titulo: 'Unitário', classe: 'num', valor: (i) => UI.numero(Emissao.numero(i.valor_unitario), 4) },
          { titulo: 'Total', classe: 'num', valor: (i) => UI.moeda(Emissao.totalItem(i)) },
        ],
        linhas: itens,
      })}
      ${parcelas.length ? `<h4 class="titulo-bloco" style="margin-top:14px">Parcelas</h4>
        ${UI.tabela({
          colunas: [
            { titulo: 'Parcela', classe: 'centro', valor: (p, i) => i + 1 },
            { titulo: 'Vencimento', classe: 'centro', valor: (p) => UI.data(p.vencimento) },
            { titulo: 'Valor', classe: 'num', valor: (p) => UI.moeda(Emissao.numero(p.valor)) },
          ],
          linhas: parcelas,
        })}` : ''}
      <div class="espaco" style="margin-top:14px;flex-wrap:wrap" id="acoes-nfe">
        <button type="button" class="btn" id="btn-previa-nfe">Prévia (DANFE)</button>
        ${Emissao._nota.status_emissao === 'RASCUNHO'
          ? '<button type="button" class="btn btn-perigo" id="btn-excluir-nfe">Excluir rascunho</button>' : ''}
        ${Emissao._nota.pode_cancelar
          ? '<button type="button" class="btn btn-perigo" id="btn-cancelar-nfe">Cancelar na SEFAZ</button>' : ''}
      </div>`;

    const n = Emissao._nota;
    alvo.querySelector('#btn-previa-nfe').onclick = () => Emissao.previa(n.id);
    const excluir = alvo.querySelector('#btn-excluir-nfe');
    if (excluir) excluir.onclick = () => Emissao.excluir(n);
    const cancelar = alvo.querySelector('#btn-cancelar-nfe');
    if (cancelar) cancelar.onclick = () => Emissao.cancelar(n);
  },

  /* ================================================================= AÇÕES */
  corpoFormulario() {
    Emissao.lerItensDaTela();
    Emissao.lerParcelasDaTela();
    const area = document.getElementById('modal-corpo');
    const dados = UI.lerFormulario(area);
    return {
      empresa_id: Estado.empresaId,
      parceiro_id: dados.parceiro_id || null,
      serie: dados.serie || '1',
      ambiente: dados.ambiente || '2',
      data_emissao: dados.data_emissao || null,
      natureza_operacao: dados.natureza_operacao || 'VENDA DE MERCADORIA',
      finalidade: dados.finalidade || '1',
      frete_modalidade: dados.frete_modalidade || '9',
      transportadora_id: dados.transportadora_id || null,
      placa_veiculo: dados.placa_veiculo || null,
      uf_veiculo: dados.uf_veiculo || null,
      volumes: dados.volumes ? Math.round(Emissao.numero(dados.volumes)) : null,
      especie_volume: dados.especie_volume || null,
      peso_liquido: Emissao.numero(dados.peso_liquido),
      peso_bruto: Emissao.numero(dados.peso_bruto),
      informacoes_complementares: dados.informacoes_complementares || null,
      itens: Emissao.itensValidos().map((i) => ({
        produto_id: i.produto_id || null,
        descricao: i.descricao || null,
        cfop: i.cfop || null,
        ncm: i.ncm || null,
        unidade: i.unidade || null,
        quantidade: Emissao.numero(i.quantidade),
        valor_unitario: Emissao.numero(i.valor_unitario),
        desconto: Emissao.numero(i.desconto),
        icms_cst: i.icms_cst || null,
      })),
      parcelas: Emissao._parcelas
        .filter((p) => p.vencimento && Emissao.numero(p.valor) > 0)
        .map((p, i) => ({ numero: String(i + 1).padStart(3, '0'),
                          vencimento: p.vencimento, valor: Emissao.numero(p.valor) })),
    };
  },

  /** Grava o rascunho. `sair` fecha a janela depois de gravar; senão volta
      para a mesma etapa em que você estava, com os valores já conferidos. */
  async salvar(notaId, transmitir, sair = false) {
    const payload = Emissao.corpoFormulario();
    if (!payload.parceiro_id) return UI.erro('Escolha o cliente da nota.');
    if (!payload.itens.length) return UI.erro('A nota precisa de pelo menos um item com quantidade e valor.');
    const etapa = Emissao._etapa || 0;
    try {
      const salvo = await Api.put(`/api/nfe/${notaId}`, payload);
      UI.modalSalvo();
      if (transmitir) return Emissao.confirmarTransmissao(salvo.nota);
      UI.sucesso('Rascunho salvo.');
      if (sair) return UI.fecharModal();
      return Emissao.formulario(salvo, Emissao._preparo, etapa);
    } catch (e) {
      UI.erro(e.message);
    }
  },

  confirmarTransmissao(n) {
    const producao = n.ambiente === '1';
    UI.abrirModal({
      titulo: 'Transmitir a nota para a SEFAZ',
      corpo: `
        <p style="margin-top:0">Vai sair uma <b>NF-e da série ${UI.escapar(n.serie)}</b> no valor de
        <b>${UI.moeda(n.valor_total)}</b> para <b>${UI.escapar(n.parceiro_nome || '')}</b>.</p>
        ${producao ? `<div class="cartao" style="border-left:4px solid var(--vermelho)">
            <div class="cartao-corpo">
              <b>Esta nota vai para PRODUÇÃO.</b>
              <div class="mini">Depois de autorizada ela vale de verdade: entra na sua escrituração
              e só sai por cancelamento na SEFAZ (com prazo e justificativa).</div>
              <label class="campo" style="margin-top:10px">
                <span><input type="checkbox" name="confirmo_producao"> Entendi, pode transmitir em produção</span>
              </label>
            </div></div>`
          : `<div class="mini">Ambiente de <b>homologação</b>: a nota não tem valor fiscal —
             é assim que se testa antes de valer.</div>`}`,
      botoes: [
        { rotulo: 'Voltar', acao: () => Emissao.abrir(n.id) },
        {
          rotulo: 'Transmitir agora',
          classe: 'btn-primario',
          acao: async (corpo) => {
            const marcado = corpo.querySelector('[name=confirmo_producao]');
            if (producao && !(marcado && marcado.checked)) {
              return UI.erro('Marque a confirmação para transmitir em produção.');
            }
            UI.trocarBotoes([{ rotulo: 'Falando com a SEFAZ...', acao: () => {} }], corpo);
            try {
              const r = await Api.post(`/api/nfe/${n.id}/transmitir`, {
                empresa_id: Estado.empresaId, confirmo_producao: true,
              });
              if (typeof Notas !== 'undefined' && Notas._linhas) Notas.tela();
              if (!r.ok) return Emissao.painelRecusa(r.nota || n, r.erro, 'transmitir');
              UI.fecharModal();
              UI.sucesso(r.mensagem);
              Emissao.abrir(n.id);
            } catch (e) {
              Emissao.painelRecusa(n, { causa: 'Não deu para transmitir a nota.',
                                        corrigir: e.message, mensagem: '' }, 'transmitir');
            }
          },
        },
      ],
    });
  },

  /** Quando a SEFAZ recusa: um painel que fica na tela dizendo o que houve,
      o que fazer e com o atalho para o lugar do conserto. */
  painelRecusa(n, erro, origem) {
    const dados = erro || { causa: 'A SEFAZ não aceitou a nota.', corrigir: '', mensagem: '' };
    const conserto = Emissao.CONSERTO[dados.onde];
    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <p style="margin-top:0">A nota <b>não foi autorizada</b>${origem === 'cancelar'
        ? ' — o cancelamento não passou' : ''}.
      ${n.status_emissao === 'RASCUNHO'
        ? 'Ela voltou a ser rascunho e <b>não gastou número</b>: é só corrigir e mandar de novo.'
        : ''}</p>
      ${Emissao.cartaoErro({ ...dados, denegada: dados.denegada })}
      <p class="mini">Guarde o código acima se precisar falar com o seu contador
      ou com o suporte — é por ele que se identifica a recusa.</p>`;

    const botoes = [{ rotulo: 'Fechar', acao: UI.fecharModal }];
    if (dados.mensagem || dados.causa) {
      botoes.push({
        rotulo: 'Copiar a mensagem',
        acao: () => {
          const texto = `NF-e ${n.numero || '(rascunho)'} — SEFAZ ${dados.codigo || ''}: `
            + `${dados.mensagem || dados.corrigir || ''}`
            + (dados.detalhe ? `\n\nResposta completa:\n${dados.detalhe}` : '');
          navigator.clipboard?.writeText(texto)
            .then(() => UI.sucesso('Mensagem copiada.'))
            .catch(() => UI.erro('O navegador não deixou copiar. Selecione o texto na tela.'));
        },
      });
    }
    if (conserto && conserto.rota) {
      botoes.push({ rotulo: conserto.rotulo, classe: 'btn-primario',
        acao: () => { UI.fecharModal(); App.irPara(conserto.rota); } });
    } else if (n.pode_editar !== false) {
      botoes.push({ rotulo: 'Corrigir a nota', classe: 'btn-primario',
        acao: () => Emissao.abrir(n.id) });
    }

    UI.abrirModal({ titulo: 'A SEFAZ não autorizou', corpo, largo: true, botoes });
    Emissao.ligarConserto(corpo, null);
  },

  async previa(notaId) {
    const aba = window.open('', '_blank');
    try {
      const resposta = await fetch(`/api/nfe/${notaId}/previa`, {
        headers: Estado.token ? { Authorization: `Bearer ${Estado.token}` } : {},
      });
      const texto = await resposta.text();
      if (!resposta.ok) {
        if (aba) aba.close();
        let corpo = {};
        try { corpo = JSON.parse(texto); } catch { corpo = {}; }
        throw new Error(corpo.detail || 'Não foi possível gerar a prévia.');
      }
      if (!aba) return UI.erro('O navegador bloqueou a aba nova. Libere as janelas deste site.');
      aba.document.open();
      aba.document.write(texto);
      aba.document.close();
    } catch (e) {
      UI.erro(e.message);
    }
  },

  async excluir(n) {
    const ok = await UI.confirmar(
      'Apagar este rascunho? Ele nunca foi para a SEFAZ, então nada é perdido lá.', 'Apagar');
    if (!ok) return;
    try {
      await Api.del(`/api/nfe/${n.id}`);
      UI.fecharModal();
      UI.sucesso('Rascunho apagado.');
      if (typeof Notas !== 'undefined') Notas.tela();
    } catch (e) {
      UI.erro(e.message);
    }
  },

  cancelar(n) {
    UI.abrirModal({
      titulo: `Cancelar a NF-e ${n.numero} na SEFAZ`,
      corpo: `
        <div class="cartao" style="border-left:4px solid var(--vermelho);margin-bottom:12px">
          <div class="cartao-corpo">
            <b>O cancelamento é definitivo e fica registrado na SEFAZ.</b>
            <div class="mini">Só é aceito dentro do prazo legal (em regra, 24 horas da
            autorização) e se a mercadoria não tiver circulado. Passado o prazo, o caminho
            é a nota de devolução — fale com o seu contador.</div>
          </div></div>
        <div class="linha-campos">
          ${UI.campo('Justificativa',
            '<textarea name="justificativa" rows="3" placeholder="mínimo de 15 letras"></textarea>',
            'vai gravada no evento, na SEFAZ')}
        </div>`,
      botoes: [
        { rotulo: 'Voltar', acao: () => Emissao.abrir(n.id) },
        {
          rotulo: 'Cancelar na SEFAZ',
          classe: 'btn-perigo',
          acao: async (corpo) => {
            const dados = UI.lerFormulario(corpo);
            if ((dados.justificativa || '').trim().length < 15) {
              return UI.erro('Escreva a justificativa com pelo menos 15 letras.');
            }
            UI.trocarBotoes([{ rotulo: 'Falando com a SEFAZ...', acao: () => {} }], corpo);
            try {
              const r = await Api.post(`/api/nfe/${n.id}/cancelar`, {
                empresa_id: Estado.empresaId, justificativa: dados.justificativa,
              });
              if (typeof Notas !== 'undefined') Notas.tela();
              if (r.ok === false) return Emissao.painelRecusa(r.nota || n, r.erro, 'cancelar');
              UI.fecharModal();
              UI.sucesso(r.mensagem);
            } catch (e) {
              Emissao.painelRecusa(n, { causa: 'Não deu para cancelar a nota.',
                                        corrigir: e.message, mensagem: '' }, 'cancelar');
            }
          },
        },
      ],
    });
  },

  /* ---------------------------------------------------- numeração das séries */
  async series() {
    const linhas = await Api.get('/api/nfe/series', { empresa_id: Estado.empresaId });
    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <p class="mini" style="margin-top:0">Cada ambiente tem a sua sequência. Se você já emitia
      notas em outro sistema, ajuste aqui o <b>próximo número</b> para a numeração continuar
      de onde parou.</p>
      ${UI.tabela({
        vazio: 'Nenhuma série ainda — ela é criada na primeira transmissão.',
        colunas: [
          { titulo: 'Série', classe: 'centro', valor: (s) => `<b>${UI.escapar(s.serie)}</b>` },
          { titulo: 'Ambiente', valor: (s) => UI.escapar(s.ambiente === '1' ? 'Produção' : 'Homologação') },
          { titulo: 'Próximo número', classe: 'num', valor: (s) => s.proximo_numero },
          { titulo: 'Descrição', valor: (s) => UI.escapar(s.descricao || '-') },
        ],
        linhas,
      })}
      <h4 class="titulo-bloco" style="margin-top:16px">Ajustar</h4>
      <div class="linha-campos">
        ${UI.campo('Série', '<input name="serie" value="1" inputmode="numeric">')}
        ${UI.campo('Ambiente', UI.select('ambiente', [
          { valor: '2', rotulo: 'Homologação' }, { valor: '1', rotulo: 'Produção' },
        ], '2', { vazio: false }))}
        ${UI.campo('Próximo número', '<input name="proximo_numero" value="1" inputmode="numeric">')}
        ${UI.campo('Descrição', '<input name="descricao" placeholder="opcional">')}
      </div>`;
    UI.abrirModal({
      titulo: 'Numeração das notas emitidas',
      corpo,
      largo: true,
      botoes: [
        { rotulo: 'Fechar', acao: UI.fecharModal },
        {
          rotulo: 'Salvar',
          classe: 'btn-primario',
          acao: async (area) => {
            const dados = UI.lerFormulario(area);
            try {
              await Api.post('/api/nfe/series', {
                empresa_id: Estado.empresaId,
                serie: dados.serie || '1',
                ambiente: dados.ambiente || '2',
                proximo_numero: Math.round(Emissao.numero(dados.proximo_numero)) || 1,
                descricao: dados.descricao || null,
              });
              UI.sucesso('Numeração salva.');
              Emissao.series();
            } catch (e) {
              UI.erro(e.message);
            }
          },
        },
      ],
    });
  },
};
