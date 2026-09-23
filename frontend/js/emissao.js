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
  async abrir(notaId, contratoId, etapa = 0, item = null) {
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
    Emissao.formulario(dados, preparo, etapa);
    // quando a recusa apontou um item, abre já rolando até ele
    if (item) setTimeout(() => Emissao.mostrarItem(item - 1), 400);
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
    Emissao._itens.forEach((i) => Emissao.seguirRegra(i));
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

  /** A SEFAZ costuma dizer em qual item deu o problema: "[nItem: 3]". */
  itemDoErro(mensagem) {
    const achado = /nItem:\s*(\d+)/i.exec(String(mensagem || ''));
    return achado ? Number(achado[1]) : null;
  },

  /** O aviso que fica na tela quando a SEFAZ recusa. É o texto mais importante
      da tela, então vem em destaque e na ordem em que se lê: o que houve, o que
      fazer, e por último as palavras exatas da SEFAZ (que servem para o
      contador e para o suporte). */
  cartaoErro(erro) {
    if (!erro) return '';
    const conserto = Emissao.CONSERTO[erro.onde];
    const item = Emissao.itemDoErro(erro.mensagem);
    const rotulo = conserto && conserto.rota ? conserto.rotulo
      : item ? `Ir para o item ${item}` : 'Ir para a etapa do conserto';
    const atalho = conserto
      ? `<button type="button" class="btn btn-mini" data-conserto="${UI.escapar(erro.onde)}"
           ${item ? `data-item="${item}"` : ''}
           style="margin-top:12px">${UI.escapar(rotulo)}</button>`
      : '';
    return `
      <div class="recusa">
        <div class="recusa-topo">
          <b>A SEFAZ NÃO ACEITOU A NOTA</b>
          ${erro.codigo ? `<span class="recusa-selo">código ${UI.escapar(erro.codigo)}</span>` : ''}
          ${item ? `<span class="recusa-selo">item ${item}</span>` : ''}
        </div>
        <div class="recusa-corpo">
          <div class="recusa-causa">${UI.escapar(erro.causa || 'A SEFAZ recusou a nota.')}</div>
          ${erro.corrigir ? `<div class="recusa-corrigir">
            ${UI.escapar(erro.corrigir)}</div>` : ''}
          ${erro.denegada ? `<div class="recusa-corrigir"><b>Nota denegada:</b> o número foi
            consumido e essa nota não pode ser reaproveitada. Depois de resolver a
            pendência, emita outra.</div>` : ''}
          ${Emissao.fichaDoItemRecusado(erro.item)}
          <div class="recusa-sefaz">
            <div class="rotulo">Palavras da SEFAZ${erro.codigo
              ? ` — código ${UI.escapar(erro.codigo)}` : ''}</div>
            ${UI.escapar(erro.mensagem || '(a SEFAZ não devolveu texto)')}
          </div>
          ${erro.detalhe ? `<details style="margin-top:10px">
            <summary class="mini" style="cursor:pointer">Detalhes técnicos (para o suporte)</summary>
            <pre class="mini" style="white-space:pre-wrap;word-break:break-all;margin:6px 0 0;
              max-height:220px;overflow:auto">${UI.escapar(erro.detalhe)}</pre>
          </details>` : ''}
          ${atalho}
        </div></div>`;
  },

  /** O que foi realmente enviado no item que a SEFAZ apontou. Sem isso, dá para
      ler a recusa e mesmo assim não saber qual CST saiu na nota. */
  fichaDoItemRecusado(item) {
    if (!item) return '';
    const dado = (rotulo, valor) => (valor === null || valor === undefined || valor === ''
      ? `<div>${UI.escapar(rotulo)}: <b>em branco</b></div>`
      : `<div>${UI.escapar(rotulo)}: <b>${UI.escapar(String(valor))}</b></div>`);
    return `
      <div class="recusa-sefaz">
        <div class="rotulo">O que foi enviado no item ${item.numero}</div>
        <div>${UI.escapar(item.descricao || '')}</div>
        <div style="margin-top:6px;display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:2px 14px">
          ${dado('CFOP', item.cfop)}
          ${dado('CST do ICMS', item.icms_cst)}
          ${dado('CST do IBS/CBS', item.ibs_cbs_cst)}
          ${dado('cClassTrib', item.ibs_cbs_classe)}
          ${dado('Alíquota de CBS', `${UI.numero(item.cbs_aliquota, 2)}%`)}
          ${dado('Alíquota de IBS', `${UI.numero(item.ibs_uf_aliquota, 2)}%`)}
        </div>
        <div style="margin-top:6px">Base e alíquota de IBS/CBS
          <b>${item.levou_grupo_ibs_cbs ? 'foram enviadas' : 'não foram enviadas'}</b>
          (é o CST do IBS/CBS que decide isso).</div>
      </div>`;
  },

  /** Liga os botões de atalho do aviso de erro. Quando a SEFAZ apontou um item,
      o atalho abre a etapa dos itens já rolando até ele, com os impostos à vista. */
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
        const item = Number(botao.dataset.item || 0);
        if (item) setTimeout(() => Emissao.mostrarItem(item - 1), 250);
      };
    });
  },

  /** Rola até um item e abre o bloco de impostos dele. */
  mostrarItem(indice) {
    const bloco = document.querySelector(`[data-impostos="${indice}"]`);
    if (!bloco) return;
    bloco.open = true;
    Emissao._abertos = Emissao._abertos || {};
    Emissao._abertos[indice] = true;
    bloco.scrollIntoView({ block: 'center', behavior: 'smooth' });
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
  /* Tabelas curtas dos códigos fiscais — o rótulo explica o que cada um é,
     para não precisar consultar manual a cada nota. */
  CSOSN: [
    { valor: '101', rotulo: '101 — tributada com crédito do Simples' },
    { valor: '102', rotulo: '102 — tributada sem crédito' },
    { valor: '103', rotulo: '103 — isenção do ICMS na faixa de receita' },
    { valor: '300', rotulo: '300 — imune' },
    { valor: '400', rotulo: '400 — não tributada pelo Simples' },
    { valor: '500', rotulo: '500 — ICMS já cobrado por substituição' },
    { valor: '900', rotulo: '900 — outros' },
  ],
  CST_ICMS: [
    { valor: '00', rotulo: '00 — tributada integralmente' },
    { valor: '20', rotulo: '20 — com redução de base' },
    { valor: '40', rotulo: '40 — isenta' },
    { valor: '41', rotulo: '41 — não tributada' },
    { valor: '50', rotulo: '50 — suspensão' },
    { valor: '51', rotulo: '51 — diferimento (café em MG)' },
    { valor: '60', rotulo: '60 — ICMS já cobrado por substituição' },
    { valor: '90', rotulo: '90 — outras' },
  ],
  ORIGENS: [
    { valor: '0', rotulo: '0 — nacional' },
    { valor: '1', rotulo: '1 — importação direta' },
    { valor: '2', rotulo: '2 — adquirida no mercado interno, importada' },
    { valor: '3', rotulo: '3 — nacional com mais de 40% de conteúdo importado' },
    { valor: '4', rotulo: '4 — nacional por processo produtivo básico' },
    { valor: '5', rotulo: '5 — nacional com até 40% de conteúdo importado' },
    { valor: '6', rotulo: '6 — importação direta sem similar nacional' },
    { valor: '7', rotulo: '7 — mercado interno sem similar nacional' },
    { valor: '8', rotulo: '8 — nacional com mais de 70% de conteúdo importado' },
  ],
  CST_PISCOFINS: [
    { valor: '01', rotulo: '01 — tributada, alíquota básica' },
    { valor: '02', rotulo: '02 — tributada, alíquota diferenciada' },
    { valor: '04', rotulo: '04 — monofásica, alíquota zero' },
    { valor: '06', rotulo: '06 — alíquota zero' },
    { valor: '07', rotulo: '07 — isenta' },
    { valor: '08', rotulo: '08 — sem incidência' },
    { valor: '09', rotulo: '09 — com suspensão' },
    { valor: '49', rotulo: '49 — outras operações de saída (Simples)' },
    { valor: '99', rotulo: '99 — outras operações' },
  ],
  CST_IBSCBS: [
    { valor: '000', rotulo: '000 — tributação integral' },
    { valor: '200', rotulo: '200 — alíquota zero' },
    { valor: '400', rotulo: '400 — isenção' },
    { valor: '410', rotulo: '410 — imunidade' },
    { valor: '510', rotulo: '510 — diferimento' },
    { valor: '550', rotulo: '550 — suspensão' },
    { valor: '620', rotulo: '620 — tributação monofásica' },
  ],

  itemVazio() {
    return { produto_id: '', descricao: '', unidade: '', quantidade: 0, valor_unitario: 0,
             cfop: '', ncm: '', icms_cst: '', desconto: 0, origem_mercadoria: '0',
             icms_base: null, icms_aliquota: 0, icms_reducao: 0, icms_valor: 0,
             cst_pis: '', pis_cofins_base: null, aliquota_pis: 0, pis_valor: 0,
             cst_cofins: '', aliquota_cofins: 0, cofins_valor: 0,
             cst_ipi: '', aliquota_ipi: 0, ipi_valor: 0,
             ibs_cbs_cst: '', ibs_cbs_classe: '', ibs_cbs_base: null,
             ibs_cbs_reducao_aliquota: 0,
             ibs_uf_aliquota: Emissao.IBS_UF, ibs_mun_aliquota: Emissao.IBS_MUN,
             cbs_aliquota: Emissao.CBS };
  },

  /* Alíquotas de teste de 2026 da reforma tributária (IBS 0,1% e CBS 0,9%).
     Servem só de ponto de partida: cada item pode ser alterado à mão. */
  IBS_UF: 0.1,
  IBS_MUN: 0,
  CBS: 0.9,

  /** Campos de imposto que são número (para ler e gravar com vírgula). */
  CAMPOS_NUMERO: ['quantidade', 'valor_unitario', 'desconto', 'icms_base', 'icms_aliquota',
    'icms_reducao', 'icms_valor', 'pis_cofins_base', 'aliquota_pis', 'pis_valor',
    'aliquota_cofins', 'cofins_valor', 'aliquota_ipi', 'ipi_valor', 'ibs_cbs_base',
    'ibs_cbs_reducao_aliquota', 'ibs_uf_aliquota', 'ibs_uf_valor', 'ibs_mun_aliquota',
    'ibs_mun_valor', 'cbs_aliquota', 'cbs_valor'],

  /** Campos calculados: enquanto ninguém digita neles, seguem a base e a alíquota. */
  CALCULADOS: ['icms_base', 'icms_valor', 'pis_cofins_base', 'pis_valor', 'cofins_valor',
    'ipi_valor', 'ibs_cbs_base', 'ibs_uf_valor', 'ibs_mun_valor', 'cbs_valor'],

  /** Percentuais que vivem só na regra fiscal. O item guarda a base já em reais,
      então estes não são campos do item: a tela usa para montar a base. */
  PERCENTUAIS_DA_REGRA: ['icms_base', 'pis_cofins_base', 'pis_cofins_reducao',
    'ibs_cbs_base', 'ibs_cbs_reducao_base'],

  /** Campos de imposto que **seguem a regra fiscal** enquanto ninguém digitar
      neles. Quem for digitado fica marcado e é mandado para o servidor; o resto
      vai em branco, e a conta sai da regra a cada gravação — por isso corrigir a
      tabela de regras já conserta os rascunhos abertos. */
  SEGUEM_A_REGRA: ['icms_cst', 'icms_base', 'icms_reducao', 'icms_aliquota', 'icms_valor',
    'cst_pis', 'cst_cofins', 'pis_cofins_base', 'aliquota_pis', 'pis_valor',
    'aliquota_cofins', 'cofins_valor', 'cst_ipi', 'aliquota_ipi', 'ipi_valor',
    'ibs_cbs_cst', 'ibs_cbs_classe', 'ibs_cbs_base', 'ibs_cbs_reducao_aliquota',
    'cbs_aliquota', 'cbs_valor', 'ibs_uf_aliquota', 'ibs_uf_valor',
    'ibs_mun_aliquota', 'ibs_mun_valor'],

  /** Um percentual da regra deste item, com o padrão de quando a regra não diz. */
  percentualDaRegra(item, campo, padrao) {
    const valor = Number((item.regra_valores || {})[campo]);
    return Number.isFinite(valor) ? valor : padrao;
  },

  /* ICMS que não destaca valor: isento, não tributado, diferido, ST. */
  SEM_VALOR_ICMS: ['40', '41', '50', '51', '60', '102', '103', '300', '400', '500'],

  /** Refaz os impostos do item a partir da base e das alíquotas. O que a pessoa
      digitou à mão é respeitado (o campo fica marcado em `_mao`). */
  recalcularImpostos(item) {
    const mao = item._mao || {};
    const total = Emissao.totalItem(item);
    const perc = (campo, padrao) => Emissao.percentualDaRegra(item, campo, padrao);
    // a base é o percentual do valor do item que a regra manda entrar no cálculo;
    // a redução desconta dela depois. 100% e 0% é o caso normal.
    const reducao = Emissao.numero(item.icms_reducao);
    if (!mao.icms_base) {
      item.icms_base = Math.round(total * perc('icms_base', 100) / 100
        * (1 - reducao / 100) * 100) / 100;
    }
    const base = Emissao.numero(item.icms_base);
    const cst = String(item.icms_cst || '');
    if (!mao.icms_valor) {
      item.icms_valor = Emissao.SEM_VALOR_ICMS.includes(cst) || Emissao.SEM_VALOR_ICMS.includes(cst.padStart(3, '0'))
        ? 0
        : Math.round(base * Emissao.numero(item.icms_aliquota)) / 100;
    }
    if (!mao.pis_cofins_base) {
      item.pis_cofins_base = Math.round(total * perc('pis_cofins_base', 100) / 100
        * (1 - perc('pis_cofins_reducao', 0) / 100) * 100) / 100;
    }
    const basePis = Emissao.numero(item.pis_cofins_base);
    if (!mao.pis_valor) item.pis_valor = Math.round(basePis * Emissao.numero(item.aliquota_pis)) / 100;
    if (!mao.cofins_valor) item.cofins_valor = Math.round(basePis * Emissao.numero(item.aliquota_cofins)) / 100;
    if (!mao.ipi_valor) item.ipi_valor = Math.round(total * Emissao.numero(item.aliquota_ipi)) / 100;
    if (!mao.ibs_cbs_base) {
      item.ibs_cbs_base = Math.round(total * perc('ibs_cbs_base', 100) / 100
        * (1 - perc('ibs_cbs_reducao_base', 0) / 100) * 100) / 100;
    }
    const baseIbs = Emissao.numero(item.ibs_cbs_base);
    // o redutor de alíquota da reforma desconta das três alíquotas de uma vez
    const fator = 1 - Emissao.numero(item.ibs_cbs_reducao_aliquota) / 100;
    if (!mao.ibs_uf_valor) item.ibs_uf_valor = Math.round(baseIbs * Emissao.numero(item.ibs_uf_aliquota) * fator) / 100;
    if (!mao.ibs_mun_valor) item.ibs_mun_valor = Math.round(baseIbs * Emissao.numero(item.ibs_mun_aliquota) * fator) / 100;
    if (!mao.cbs_valor) item.cbs_valor = Math.round(baseIbs * Emissao.numero(item.cbs_aliquota) * fator) / 100;
  },

  /** Um campo de imposto dentro do cartão do item. */
  campoImposto(i, nome, rotulo, casas, dica) {
    const item = Emissao._itens[i];
    return UI.campo(rotulo,
      `<input data-campo="${nome}" data-linha="${i}" inputmode="decimal"
         value="${UI.escapar(Emissao.mostrar(item[nome], casas))}">`, dica);
  },

  selecaoImposto(i, nome, rotulo, opcoes, dica) {
    const item = Emissao._itens[i];
    return UI.campo(rotulo,
      UI.select(`${nome}__${i}`, opcoes, item[nome] || '', { vazio: 'Do cadastro' })
        .replace('<select', `<select data-campo="${nome}" data-linha="${i}"`), dica);
  },

  /** Bloco de impostos do item — já vem aberto, com os CST e os valores à vista.
      Quem não quiser ver fecha, e a escolha vale para os próximos desenhos. */
  blocoImpostos(i) {
    const simples = ['1', '4'].includes(String(Emissao._preparo?.empresa?.crt || '1'));
    const aberto = (Emissao._abertos || {})[i] !== false;
    return `
      <details class="impostos-item" ${aberto ? 'open' : ''} data-impostos="${i}">
        <summary style="cursor:pointer;margin-top:12px">
          <b>Impostos do item</b>
          <span class="mini" data-resumo-imposto="${i}"></span>
        </summary>
        ${Emissao._itens[i].regra_nome ? `<div class="cartao"
          style="margin-top:10px;border-left:4px solid var(--verde)">
          <div class="cartao-corpo">
            <b class="mini">Regra fiscal: ${UI.escapar(Emissao._itens[i].regra_nome)}</b>
            <div class="mini">${UI.escapar(Emissao._itens[i].regra_resumo || '')}</div>
            <button type="button" class="btn btn-mini" data-regra="${i}"
              style="margin-top:8px">Refazer os impostos por esta regra</button>
          </div></div>`
          : `<div class="mini" style="margin-top:10px">Nenhuma regra fiscal casou com este
             cliente e este item — os impostos vieram do cadastro do produto.
             <button type="button" class="btn btn-mini" data-regra="${i}">Procurar regra</button>
             </div>`}
        <h5 class="titulo-bloco" style="margin:10px 0 0">ICMS</h5>
        <div class="linha-campos">
          ${Emissao.selecaoImposto(i, 'origem_mercadoria', 'Origem', Emissao.ORIGENS)}
          ${Emissao.selecaoImposto(i, 'icms_cst', simples ? 'CSOSN' : 'CST do ICMS',
            simples ? Emissao.CSOSN : Emissao.CST_ICMS,
            simples ? 'Simples Nacional' : 'regime normal')}
          ${Emissao.campoImposto(i, 'icms_reducao', 'Redução da base (%)', 4)}
          ${Emissao.campoImposto(i, 'icms_base', 'Base de cálculo', 2,
            'em branco = calculado pela regra fiscal')}
          ${Emissao.campoImposto(i, 'icms_aliquota', 'Alíquota ICMS (%)', 4)}
          ${Emissao.campoImposto(i, 'icms_valor', 'Valor do ICMS', 2, 'calculado')}
        </div>
        <h5 class="titulo-bloco" style="margin:12px 0 0">PIS e COFINS</h5>
        <div class="linha-campos">
          ${Emissao.selecaoImposto(i, 'cst_pis', 'CST do PIS', Emissao.CST_PISCOFINS)}
          ${Emissao.campoImposto(i, 'pis_cofins_base', 'Base de cálculo', 2,
            'em branco = calculado pela regra fiscal')}
          ${Emissao.campoImposto(i, 'aliquota_pis', 'Alíquota PIS (%)', 4)}
          ${Emissao.campoImposto(i, 'pis_valor', 'Valor do PIS', 2, 'calculado')}
          ${Emissao.selecaoImposto(i, 'cst_cofins', 'CST da COFINS', Emissao.CST_PISCOFINS)}
          ${Emissao.campoImposto(i, 'aliquota_cofins', 'Alíquota COFINS (%)', 4)}
          ${Emissao.campoImposto(i, 'cofins_valor', 'Valor da COFINS', 2, 'calculado')}
        </div>
        <h5 class="titulo-bloco" style="margin:12px 0 0">IPI</h5>
        <div class="linha-campos">
          ${UI.campo('CST do IPI',
            `<input data-campo="cst_ipi" data-linha="${i}" inputmode="numeric"
               value="${UI.escapar(Emissao._itens[i].cst_ipi || '')}" maxlength="2">`,
            'em branco = sem IPI')}
          ${Emissao.campoImposto(i, 'aliquota_ipi', 'Alíquota IPI (%)', 4)}
          ${Emissao.campoImposto(i, 'ipi_valor', 'Valor do IPI', 2, 'calculado')}
        </div>
        <h5 class="titulo-bloco" style="margin:12px 0 0">IBS e CBS — reforma tributária</h5>
        <p class="mini" style="margin:4px 0 0">2026 é ano de teste: as alíquotas são simbólicas
        (IBS 0,1% e CBS 0,9%) e a apuração é só informativa.${simples
          ? ' No Simples Nacional o destaque começa em 2027.' : ''}</p>
        <div class="linha-campos">
          ${Emissao.selecaoImposto(i, 'ibs_cbs_cst', 'CST do IBS/CBS', Emissao.CST_IBSCBS)}
          ${UI.campo('Classificação (cClassTrib)',
            `<input data-campo="ibs_cbs_classe" data-linha="${i}" inputmode="numeric"
               value="${UI.escapar(Emissao._itens[i].ibs_cbs_classe || '')}" maxlength="6"
               placeholder="000001">`, 'tabela da NT 2025.002')}
          ${Emissao.campoImposto(i, 'ibs_cbs_base', 'Base do IBS/CBS', 2,
            'em branco = calculado pela regra fiscal')}
          ${Emissao.campoImposto(i, 'ibs_cbs_reducao_aliquota', 'Redução de alíquota (%)', 4,
            'desconta das três alíquotas')}
          ${Emissao.campoImposto(i, 'ibs_uf_aliquota', 'IBS estadual (%)', 4)}
          ${Emissao.campoImposto(i, 'ibs_uf_valor', 'Valor IBS estadual', 2, 'calculado')}
          ${Emissao.campoImposto(i, 'ibs_mun_aliquota', 'IBS municipal (%)', 4)}
          ${Emissao.campoImposto(i, 'ibs_mun_valor', 'Valor IBS municipal', 2, 'calculado')}
          ${Emissao.campoImposto(i, 'cbs_aliquota', 'CBS (%)', 4)}
          ${Emissao.campoImposto(i, 'cbs_valor', 'Valor da CBS', 2, 'calculado')}
        </div>
      </details>`;
  },

  /** Cada item é um cartão: no celular os campos empilham sozinhos. */
  desenharItens() {
    const alvo = document.getElementById('itens-nfe');
    if (!alvo) return;
    const editavel = Emissao._editavel;
    const produtos = Api.produtosAtivos();
    Emissao._itens.forEach((item) => Emissao.recalcularImpostos(item));

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
              'traz NCM e CFOP do cadastro; o imposto vem da regra fiscal')}
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
          ${Emissao.blocoImpostos(i)}
          <div class="mini" style="margin-top:8px;text-align:right">
            Total do item: <b data-total-item="${i}">${UI.moeda(Emissao.totalItem(item))}</b>
          </div>
        </div>
      </div>`).join('');

    // digitação livre: só recalcula os totais, sem redesenhar (o campo não perde o foco)
    alvo.querySelectorAll('[data-campo]').forEach((campo) => {
      const anotar = () => {
        const item = Emissao._itens[Number(campo.dataset.linha)];
        const nome = campo.dataset.campo;
        // campo de imposto que a pessoa apagou volta a seguir a regra fiscal
        item._mao = item._mao || {};
        if (Emissao.SEGUEM_A_REGRA.includes(nome)) {
          item._mao[nome] = String(campo.value).trim() !== '';
        }
        item[nome] = Emissao.CAMPOS_NUMERO.includes(nome)
          ? Emissao.numero(campo.value) : campo.value;
        Emissao.recalcularImpostos(item);
        Emissao.atualizarTotais(campo);
      };
      campo.oninput = anotar;
      campo.onchange = () => {
        anotar();
        // o CFOP faz parte do cruzamento: mudou o CFOP, a legislação pode ser outra
        if (campo.dataset.campo === 'cfop') {
          Emissao.aplicarRegra(Number(campo.dataset.linha), true);
        }
      };
    });
    // lembrar quais blocos de imposto ficaram abertos entre um desenho e outro
    alvo.querySelectorAll('[data-impostos]').forEach((bloco) => {
      bloco.ontoggle = () => {
        Emissao._abertos = Emissao._abertos || {};
        Emissao._abertos[Number(bloco.dataset.impostos)] = bloco.open;
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
            origem_mercadoria: produto.origem || Emissao._itens[i].origem_mercadoria || '0',
            icms_aliquota: Number(produto.aliquota_icms || 0),
            icms_reducao: Number(produto.reducao_base_icms || 0),
            cst_pis: produto.cst_pis || '',
            aliquota_pis: Number(produto.aliquota_pis || 0),
            cst_cofins: produto.cst_cofins || '',
            aliquota_cofins: Number(produto.aliquota_cofins || 0),
            cst_ipi: produto.cst_ipi || '',
            aliquota_ipi: Number(produto.aliquota_ipi || 0),
          });
        }
        Emissao.desenharItens();
      };
    });
    alvo.querySelectorAll('[data-regra]').forEach((botao) => {
      botao.onclick = () => Emissao.aplicarRegra(Number(botao.dataset.regra));
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

  /** Busca a regra fiscal do par (cliente x item) e refaz os impostos do item.
      Apaga as marcas de "digitado à mão": a regra passa a mandar de novo. */
  async aplicarRegra(indice, silencioso) {
    Emissao.lerItensDaTela();
    const item = Emissao._itens[indice];
    const area = document.getElementById('modal-corpo');
    const parceiroId = area?.querySelector('[name=parceiro_id]')?.value || null;
    if (!parceiroId) {
      if (silencioso) return;
      return UI.erro('Escolha o cliente na etapa Nota antes de buscar a regra.');
    }
    try {
      const r = await Api.post('/api/fiscal/simular', {
        empresa_id: Estado.empresaId,
        parceiro_id: parceiroId,
        produto_id: item.produto_id || null,
        cfop: item.cfop || null,
        operacao: 'SAIDA',
      });
      if (!r.regra) {
        item.regra_nome = null;
        item.regra_resumo = null;
        Emissao.desenharItens();
        return UI.erro('Nenhuma regra fiscal serve para este CFOP, este cliente e este item. '
          + 'Cadastre em Cadastros > Regras fiscais.');
      }
      item._mao = {};
      item.regra_valores = r.regra.valores || {};
      // os percentuais de base ficam guardados na regra; o item leva a base em reais
      const doItem = { ...item.regra_valores };
      Emissao.PERCENTUAIS_DA_REGRA.forEach((campo) => { delete doItem[campo]; });
      Object.assign(item, doItem);
      if (r.regra.valores && r.regra.valores.icms_origem) {
        item.origem_mercadoria = r.regra.valores.icms_origem;
      }
      item.regra_nome = r.regra.nome;
      item.regra_resumo = r.regra.resumo;
      Emissao.recalcularImpostos(item);
      Emissao.desenharItens();
      UI.sucesso(`Impostos refeitos pela regra "${r.regra.nome}".`);
    } catch (e) {
      if (!silencioso) UI.erro(e.message);
    }
  },

  /** Campo calculado só é mandado para o servidor quando foi **digitado à mão**.
      Em branco, quem monta a base e o valor é a regra fiscal — senão a base que
      a tela calculou voltaria como se tivesse sido digitada e a regra nunca
      valeria de novo. */
  digitado(item, nome) {
    if (!item._mao || !item._mao[nome]) return null;
    return Emissao.CAMPOS_NUMERO.includes(nome)
      ? Emissao.numero(item[nome]) : (item[nome] || null);
  },

  /** Quais campos desta linha foram digitados à mão — vai gravado no item para
      o rascunho reaberto saber o que é da regra e o que é da pessoa. */
  camposManuais(item) {
    return Emissao.SEGUEM_A_REGRA.filter((nome) => item._mao && item._mao[nome]);
  },

  /** Ao abrir o rascunho: os campos que ninguém digitou voltam a sair da regra
      fiscal de hoje. Se a tabela de regras mudou, o item já abre com a
      legislação nova; o que foi digitado à mão continua como estava. */
  seguirRegra(item) {
    item._mao = {};
    (item.campos_manuais ? String(item.campos_manuais).split(',') : [])
      .forEach((nome) => { if (nome) item._mao[nome.trim()] = true; });
    const daRegra = item.regra_valores || {};
    Emissao.SEGUEM_A_REGRA.forEach((nome) => {
      // a base e os valores não vêm da regra prontos: são calculados abaixo
      if (item._mao[nome] || Emissao.CALCULADOS.includes(nome)) return;
      if (daRegra[nome] !== undefined) item[nome] = daRegra[nome];
      else item[nome] = Emissao.CAMPOS_NUMERO.includes(nome) ? 0 : '';
    });
    if (!item._mao.icms_cst && daRegra.icms_origem) {
      item.origem_mercadoria = daRegra.icms_origem;
    }
    Emissao.recalcularImpostos(item);
  },

  /** Número para mostrar num campo de valor. **Zero aparece como 0**, nunca em
      branco: campo vazio deixa dúvida se é zero mesmo ou se falta preencher — e,
      no imposto, essa dúvida vira recusa da SEFAZ. */
  mostrar(valor, casas) {
    const n = Number(valor || 0);
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
      item[nome] = Emissao.CAMPOS_NUMERO.includes(nome)
        ? Emissao.numero(campo.value)
        : campo.value;
    });
    Emissao._itens.forEach((item) => Emissao.recalcularImpostos(item));
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

  /* Quantas casas cada campo calculado mostra. */
  CASAS: { icms_base: 2, icms_valor: 2, pis_cofins_base: 2, pis_valor: 2, cofins_valor: 2,
           ipi_valor: 2, ibs_cbs_base: 2, ibs_uf_valor: 2, ibs_mun_valor: 2, cbs_valor: 2 },

  /** Só os textos de total e os valores calculados mudam enquanto se digita —
      nada é redesenhado, então o campo em uso não perde o foco nem o cursor. */
  atualizarTotais(campoAtivo) {
    const total = Emissao.total();
    Emissao._itens.forEach((item, i) => {
      const alvo = document.querySelector(`[data-total-item="${i}"]`);
      if (alvo) alvo.textContent = UI.moeda(Emissao.totalItem(item));
      // valores de imposto que ninguém digitou à mão acompanham a base e a alíquota
      Emissao.CALCULADOS.forEach((nome) => {
        if (item._mao && item._mao[nome]) return;
        const entrada = document.querySelector(
          `[data-campo="${nome}"][data-linha="${i}"]`);
        if (!entrada || entrada === campoAtivo) return;
        entrada.value = Emissao.mostrar(item[nome], Emissao.CASAS[nome] || 2);
      });
      const selo = document.querySelector(`[data-resumo-imposto="${i}"]`);
      if (selo) {
        selo.textContent = `— ICMS ${item.icms_cst || '?'} `
          + `${UI.moeda(Emissao.numero(item.icms_valor))}`
          + ` · PIS ${item.cst_pis || '?'}/COFINS ${item.cst_cofins || '?'} `
          + `${UI.moeda(Emissao.numero(item.pis_valor) + Emissao.numero(item.cofins_valor))}`
          + ` · IBS/CBS ${item.ibs_cbs_cst || '?'} `
          + `${UI.moeda(Emissao.numero(item.ibs_uf_valor)
            + Emissao.numero(item.ibs_mun_valor) + Emissao.numero(item.cbs_valor))}`;
      }
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
    if (itens.some((i) => !i.icms_cst)) avisos.push('Tem item sem CST/CSOSN do ICMS.');
    if (!['1', '4'].includes(String(Emissao._preparo?.empresa?.crt || '1'))
        && itens.some((i) => !i.ibs_cbs_cst || !i.ibs_cbs_classe)) {
      avisos.push('Regime regular: desde 2026 o IBS/CBS precisa de CST e cClassTrib no item.');
    }
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
          { titulo: 'Impostos', valor: (i) => `
              <div class="mini">ICMS ${UI.escapar(i.icms_cst || '-')} ·
                base ${UI.moeda(Emissao.numero(i.icms_base))} ·
                ${UI.numero(Emissao.numero(i.icms_aliquota), 2)}% =
                <b>${UI.moeda(Emissao.numero(i.icms_valor))}</b></div>
              <div class="mini">PIS ${UI.moeda(Emissao.numero(i.pis_valor))} ·
                COFINS ${UI.moeda(Emissao.numero(i.cofins_valor))}
                ${Emissao.numero(i.ipi_valor) ? `· IPI ${UI.moeda(Emissao.numero(i.ipi_valor))}` : ''}</div>
              <div class="mini">IBS ${UI.moeda(Emissao.numero(i.ibs_uf_valor)
                + Emissao.numero(i.ibs_mun_valor))} ·
                CBS ${UI.moeda(Emissao.numero(i.cbs_valor))}</div>` },
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
        origem_mercadoria: i.origem_mercadoria || null,
        // imposto: só vai o que foi digitado à mão. O que estiver em branco é
        // calculado no servidor pela regra fiscal — é isso que faz a base de
        // cálculo sair sempre da tabela de regras, e não do que a tela guardou.
        ...Object.fromEntries(Emissao.SEGUEM_A_REGRA
          .map((nome) => [nome, Emissao.digitado(i, nome)])),
        campos_manuais: Emissao.camposManuais(i),
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
    // o atalho do aviso reabre a nota já na etapa (e no item) do conserto
    Emissao.ligarConserto(corpo, (etapa) => Emissao.abrir(
      n.id, null, etapa, Emissao.itemDoErro(dados.mensagem)));
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
