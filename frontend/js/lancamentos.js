/* Contas a receber, contas a pagar e o formulário de lançamento. */
const Lancamentos = {
  filtros: {},

  /* ================================================================ LISTAGEM */
  async contas(tipo) {
    const alvo = document.getElementById('pagina');
    const eh_receber = tipo === 'RECEBER';
    const f = Object.assign(
      { situacao: 'ABERTAS', de: '', ate: '', parceiro_id: '', q: '' },
      Lancamentos.filtros[tipo] || {},
    );

    alvo.innerHTML = `
      <div id="kpis" class="grade g4" style="margin-bottom:18px"></div>
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div>
            <h3>${eh_receber ? 'Contas a Receber' : 'Contas a Pagar'}</h3>
            <div class="mini" id="resumo-lista"></div>
          </div>
          <div class="espaco">
            <button class="btn" id="btn-baixar-lote">Baixar selecionadas</button>
            <button class="btn" id="btn-exportar">Exportar CSV</button>
            <button class="btn btn-primario" id="btn-novo-titulo">+ Novo título</button>
          </div>
        </div>
        <div class="filtros">
          ${UI.campo('Situação', UI.select('situacao', [
            { valor: 'ABERTAS', rotulo: 'Em aberto' },
            { valor: 'VENCIDAS', rotulo: 'Vencidas' },
            { valor: 'PAGAS', rotulo: eh_receber ? 'Recebidas' : 'Pagas' },
            { valor: 'TODAS', rotulo: 'Todas' },
          ], f.situacao, { vazio: false }))}
          ${UI.campo('Vencimento de', `<input type="date" name="de" value="${f.de}">`)}
          ${UI.campo('Vencimento até', `<input type="date" name="ate" value="${f.ate}">`)}
          ${UI.campo(eh_receber ? 'Cliente' : 'Fornecedor', UI.select('parceiro_id',
            UI.opcoesParceiros(eh_receber ? 'CLIENTE' : 'FORNECEDOR'), f.parceiro_id, { vazio: 'Todos' }))}
          ${UI.campo('Buscar', `<input name="q" value="${UI.escapar(f.q)}" placeholder="descrição ou documento">`)}
          <div class="acoes"><button class="btn btn-primario" id="btn-filtrar">Filtrar</button></div>
        </div>
        <div class="cartao-corpo sem-padding" id="lista-parcelas"><div class="vazio">Carregando...</div></div>
      </div>`;

    const lerFiltros = () => {
      const dados = UI.lerFormulario(alvo.querySelector('.filtros'));
      Lancamentos.filtros[tipo] = {
        situacao: dados.situacao || 'ABERTAS',
        de: dados.de || '', ate: dados.ate || '',
        parceiro_id: dados.parceiro_id || '', q: dados.q || '',
      };
      return Lancamentos.filtros[tipo];
    };

    alvo.querySelector('#btn-filtrar').onclick = () => { lerFiltros(); Lancamentos.contas(tipo); };
    alvo.querySelector('#btn-novo-titulo').onclick = () => Lancamentos.formulario(tipo);
    alvo.querySelector('#btn-exportar').onclick = () =>
      UI.exportarTabela(eh_receber ? 'contas-a-receber' : 'contas-a-pagar', '#lista-parcelas table');
    alvo.querySelector('#btn-baixar-lote').onclick = () => Lancamentos.baixarLote(tipo);

    const parcelas = await Api.get('/api/parcelas', {
      empresa_id: Estado.empresaId, tipo, situacao: f.situacao,
      de: f.de, ate: f.ate, parceiro_id: f.parceiro_id, q: f.q,
    });
    Lancamentos._parcelas = parcelas;

    const total = parcelas.reduce((s, p) => s + p.valor, 0);
    const saldo = parcelas.reduce((s, p) => s + p.saldo, 0);
    const vencidas = parcelas.filter((p) => p.vencida);
    const saldoVencido = vencidas.reduce((s, p) => s + p.saldo, 0);
    const hoje = UI.hoje();
    const saldoHoje = parcelas.filter((p) => p.data_vencimento === hoje).reduce((s, p) => s + p.saldo, 0);

    alvo.querySelector('#kpis').innerHTML = `
      <div class="kpi destaque-azul"><div class="kpi-rotulo">Títulos listados</div>
        <div class="kpi-valor">${parcelas.length}</div><div class="kpi-nota">valor total ${UI.moeda(total)}</div></div>
      <div class="kpi destaque-${eh_receber ? 'verde' : 'vermelho'}"><div class="kpi-rotulo">Saldo em aberto</div>
        <div class="kpi-valor">${UI.moeda(saldo)}</div><div class="kpi-nota">${eh_receber ? 'a receber' : 'a pagar'}</div></div>
      <div class="kpi destaque-vermelho"><div class="kpi-rotulo">Vencidos</div>
        <div class="kpi-valor negativo">${UI.moeda(saldoVencido)}</div><div class="kpi-nota">${vencidas.length} título(s)</div></div>
      <div class="kpi destaque-ambar"><div class="kpi-rotulo">Vencendo hoje</div>
        <div class="kpi-valor">${UI.moeda(saldoHoje)}</div><div class="kpi-nota">${UI.data(hoje)}</div></div>`;

    alvo.querySelector('#resumo-lista').textContent =
      `${parcelas.length} parcela(s) — saldo ${UI.moeda(saldo)}`;

    const colunas = [
      {
        titulo: '', classe: 'centro',
        valor: (p, i) => (['ABERTO', 'PARCIAL'].includes(p.status)
          ? `<input type="checkbox" class="sel-parcela" data-indice="${i}">` : ''),
      },
      { titulo: 'Vencimento', valor: (p) => UI.data(p.data_vencimento) },
      { titulo: 'Documento', valor: (p) => UI.escapar(p.numero_documento || '-') },
      { titulo: eh_receber ? 'Cliente' : 'Fornecedor', valor: (p) => UI.escapar(p.parceiro_nome || '-') },
      { titulo: 'Descrição', valor: (p) => UI.escapar(p.descricao) },
      { titulo: 'Parcela', classe: 'centro', valor: (p) => `${p.numero}/${p.total_parcelas}` },
      { titulo: 'Classificação', valor: (p) => `<span class="mini">${UI.escapar(p.classificacao || '-')}</span>` },
      { titulo: 'C. Custo', valor: (p) => `<span class="mini">${UI.escapar(p.centros_custo || '-')}</span>` },
      { titulo: 'Valor', classe: 'num', valor: (p) => UI.moeda(p.valor) },
      { titulo: 'Baixado', classe: 'num', valor: (p) => UI.moeda(p.valor_baixado) },
      { titulo: 'Saldo', classe: 'num', valor: (p) => `<span class="forte">${UI.moeda(p.saldo)}</span>` },
      {
        titulo: 'Situação', classe: 'centro',
        valor: (p) => UI.tagStatus(p.status, p.vencida) +
          (p.dias_atraso ? `<div class="mini">${p.dias_atraso} dia(s)</div>` : ''),
      },
      {
        titulo: 'Ações', classe: 'centro',
        valor: (p, i) => `
          ${['ABERTO', 'PARCIAL'].includes(p.status) ? `<button class="btn btn-mini btn-verde" data-baixar="${i}">${eh_receber ? 'Receber' : 'Pagar'}</button>` : ''}
          <button class="btn btn-mini" data-ver="${i}">Ver</button>`,
      },
    ];

    const rodape = {};
    alvo.querySelector('#lista-parcelas').innerHTML = UI.tabela({
      colunas, linhas: parcelas, rodape,
      vazio: 'Nenhum título encontrado com os filtros informados.',
    });

    alvo.querySelectorAll('[data-baixar]').forEach((b) => {
      b.onclick = () => Lancamentos.baixar(parcelas[Number(b.dataset.baixar)], tipo);
    });
    alvo.querySelectorAll('[data-ver]').forEach((b) => {
      b.onclick = () => Lancamentos.verTitulo(parcelas[Number(b.dataset.ver)].lancamento_id);
    });
  },

  /* ================================================================ FORMULÁRIO */
  formulario(tipo, base = {}) {
    const eh_receber = tipo === 'RECEBER';
    const tiposConta = eh_receber ? ['RECEITA'] : ['DESPESA', 'CUSTO', 'ATIVO', 'PASSIVO'];

    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <div class="abas" style="margin-bottom:14px">
        <button class="aba ativa" data-modo="SIMPLES" type="button">Lançamento simples</button>
        <button class="aba" data-modo="MULTIPLO" type="button">Lançamento múltiplo</button>
      </div>
      <div class="mini" id="ajuda-modo" style="margin-bottom:12px">
        Uma classificação e uma parcela — ideal para o dia a dia.
      </div>

      <div class="linha-campos">
        ${UI.campo('Descrição *', `<input name="descricao" required value="${UI.escapar(base.descricao || '')}" placeholder="ex.: Honorários de assessoria - maio">`)}
        ${UI.campo('Nº documento', `<input name="numero_documento" placeholder="NF, contrato, boleto...">`)}
        ${UI.campo(eh_receber ? 'Cliente' : 'Fornecedor',
          UI.select('parceiro_id', UI.opcoesParceiros(eh_receber ? 'CLIENTE' : 'FORNECEDOR'), '', { vazio: 'Não informado' }))}
        ${UI.campo('Operação', UI.select('operacao_id', UI.opcoesOperacoes(eh_receber ? 'ENTRADA' : 'SAIDA'), '', { vazio: 'Não informada' }))}
        ${UI.campo('Data de emissão', `<input type="date" name="data_emissao" value="${UI.hoje()}">`)}
        ${UI.campo('Competência', `<input type="date" name="data_competencia" value="${UI.hoje()}">`, 'mês de referência no DRE')}
        ${UI.campo('Valor total *', `<input type="number" step="0.01" min="0.01" name="valor_total" required placeholder="0,00">`)}
      </div>

      <!-- ------------------------------------------------------- modo simples -->
      <div id="area-simples">
        <div class="linha-campos" style="margin-top:14px">
          ${UI.campo('Conta contábil *', UI.select('conta_simples', UI.opcoesContas(tiposConta), '', { obrigatorio: true }))}
          ${UI.campo('Centro de custo', UI.select('centro_simples', UI.opcoesCentros(), '', { vazio: 'Não informado' }))}
          ${UI.campo('Vencimento', `<input type="date" name="vencimento_simples" value="${UI.hoje()}">`)}
        </div>
        <div class="linha-campos" style="margin-top:10px">
          ${UI.campo('Baixa imediata', `<span><input type="checkbox" name="baixar_agora"> ${eh_receber ? 'Já recebido' : 'Já pago'}</span>`)}
          ${UI.campo('Conta bancária da baixa', UI.select('banco_id', UI.opcoesBancos(), '', { vazio: 'Selecione' }))}
        </div>
      </div>

      <!-- ------------------------------------------------------ modo múltiplo -->
      <div id="area-multiplo" class="oculto">
        <div class="cartao" style="margin-top:14px;box-shadow:none">
          <div class="cartao-cabecalho">
            <h3 style="font-size:14px">Rateio da classificação</h3>
            <button class="btn btn-mini" type="button" id="btn-add-item">+ Adicionar linha</button>
          </div>
          <div class="cartao-corpo">
            <div class="linha-itens cabecalho">
              <span>Conta contábil</span><span>Centro de custo</span><span>Operação</span><span>Valor</span><span></span>
            </div>
            <div id="itens"></div>
            <div class="mini" id="soma-itens" style="margin-top:8px"></div>
          </div>
        </div>

        <div class="cartao" style="box-shadow:none">
          <div class="cartao-cabecalho">
            <h3 style="font-size:14px">Parcelamento</h3>
            <div class="espaco">
              <button class="btn btn-mini" type="button" id="btn-gerar-parcelas">Gerar parcelas</button>
              <button class="btn btn-mini" type="button" id="btn-add-parcela">+ Linha</button>
            </div>
          </div>
          <div class="cartao-corpo">
            <div class="linha-campos" style="margin-bottom:12px">
              ${UI.campo('Qtd. parcelas', '<input type="number" min="1" max="360" id="qtd-parcelas" value="1">')}
              ${UI.campo('1º vencimento', `<input type="date" id="primeiro-vencimento" value="${UI.hoje()}">`)}
              ${UI.campo('Periodicidade', UI.select('periodicidade', [
                { valor: 'MENSAL', rotulo: 'Mensal' }, { valor: 'DIAS', rotulo: 'A cada N dias' },
              ], 'MENSAL', { vazio: false }))}
              ${UI.campo('Intervalo (dias)', '<input type="number" name="intervalo_dias" value="30">')}
            </div>
            <div class="linha-parcelas cabecalho" style="font-size:11px;text-transform:uppercase;color:var(--cinza-500);font-weight:700">
              <span>Nº</span><span>Vencimento</span><span>Valor</span><span></span>
            </div>
            <div id="parcelas"></div>
            <div class="mini" id="soma-parcelas" style="margin-top:8px"></div>
          </div>
        </div>
      </div>

      ${UI.campo('Observações', '<textarea name="observacao"></textarea>')}`;

    let modo = 'SIMPLES';
    const q = (s) => corpo.querySelector(s);

    /* ---- linhas de rateio ---- */
    const addItem = (valor = '') => {
      const linha = document.createElement('div');
      linha.className = 'linha-itens';
      linha.innerHTML = `
        ${UI.select('item_conta', UI.opcoesContas(tiposConta), '', { vazio: 'Conta...' })}
        ${UI.select('item_centro', UI.opcoesCentros(), '', { vazio: 'C. custo...' })}
        ${UI.select('item_operacao', UI.opcoesOperacoes(eh_receber ? 'ENTRADA' : 'SAIDA'), '', { vazio: 'Operação...' })}
        <input type="number" step="0.01" class="item-valor" value="${valor}" placeholder="0,00">
        <button class="btn btn-mini btn-perigo" type="button">&times;</button>`;
      linha.querySelector('button').onclick = () => { linha.remove(); somarItens(); };
      linha.querySelector('.item-valor').oninput = somarItens;
      q('#itens').appendChild(linha);
      somarItens();
    };
    const somarItens = () => {
      const total = [...corpo.querySelectorAll('.item-valor')].reduce((s, i) => s + Number(i.value || 0), 0);
      const informado = Number(q('[name=valor_total]').value || 0);
      const diferenca = +(informado - total).toFixed(2);
      q('#soma-itens').innerHTML =
        `Soma do rateio: <span class="forte">${UI.moeda(total)}</span> — valor do lançamento: ${UI.moeda(informado)}` +
        (Math.abs(diferenca) > 0.01 ? ` <span class="negativo forte">(diferença ${UI.moeda(diferenca)})</span>` : ' <span class="positivo forte">(confere)</span>');
    };

    /* ---- linhas de parcela ---- */
    const addParcela = (numero, vencimento, valor) => {
      const linha = document.createElement('div');
      linha.className = 'linha-parcelas';
      linha.innerHTML = `
        <input class="parcela-num" value="${numero}" readonly>
        <input type="date" class="parcela-venc" value="${vencimento}">
        <input type="number" step="0.01" class="parcela-valor" value="${valor}">
        <button class="btn btn-mini btn-perigo" type="button">&times;</button>`;
      linha.querySelector('button').onclick = () => { linha.remove(); somarParcelas(); };
      linha.querySelector('.parcela-valor').oninput = somarParcelas;
      q('#parcelas').appendChild(linha);
      somarParcelas();
    };
    const somarParcelas = () => {
      const total = [...corpo.querySelectorAll('.parcela-valor')].reduce((s, i) => s + Number(i.value || 0), 0);
      const informado = Number(q('[name=valor_total]').value || 0);
      const diferenca = +(informado - total).toFixed(2);
      q('#soma-parcelas').innerHTML =
        `Soma das parcelas: <span class="forte">${UI.moeda(total)}</span>` +
        (Math.abs(diferenca) > 0.01 ? ` <span class="negativo forte">(diferença ${UI.moeda(diferenca)})</span>` : ' <span class="positivo forte">(confere)</span>');
    };
    const gerarParcelas = () => {
      const qtd = Math.max(1, Number(q('#qtd-parcelas').value || 1));
      const base = q('#primeiro-vencimento').value || UI.hoje();
      const total = Number(q('[name=valor_total]').value || 0);
      const mensal = q('[name=periodicidade]').value === 'MENSAL';
      const intervalo = Number(q('[name=intervalo_dias]').value || 30);
      const valor = Math.round((total / qtd) * 100) / 100;
      q('#parcelas').innerHTML = '';
      let acumulado = 0;
      for (let i = 0; i < qtd; i += 1) {
        const d = new Date(`${base}T12:00:00`);
        if (mensal) d.setMonth(d.getMonth() + i);
        else d.setDate(d.getDate() + intervalo * i);
        const v = i < qtd - 1 ? valor : Math.round((total - acumulado) * 100) / 100;
        acumulado += v;
        addParcela(i + 1, d.toISOString().slice(0, 10), v.toFixed(2));
      }
    };

    q('#btn-add-item').onclick = () => addItem();
    q('#btn-add-parcela').onclick = () => addParcela(corpo.querySelectorAll('.linha-parcelas:not(.cabecalho)').length, UI.hoje(), '0.00');
    q('#btn-gerar-parcelas').onclick = gerarParcelas;
    q('[name=valor_total]').oninput = () => { somarItens(); somarParcelas(); };
    q('[name=data_emissao]').onchange = (e) => {
      q('[name=data_competencia]').value = e.target.value;
      q('[name=vencimento_simples]').value = e.target.value;
      q('#primeiro-vencimento').value = e.target.value;
    };
    q('[name=operacao_id]').onchange = (e) => {
      const op = (Estado.cache.operacoes || []).find((o) => String(o.id) === e.target.value);
      if (op && op.conta_contabil_id) q('[name=conta_simples]').value = op.conta_contabil_id;
      if (op && op.centro_custo_id) q('[name=centro_simples]').value = op.centro_custo_id;
    };

    corpo.querySelectorAll('.aba').forEach((aba) => {
      aba.onclick = () => {
        corpo.querySelectorAll('.aba').forEach((a) => a.classList.remove('ativa'));
        aba.classList.add('ativa');
        modo = aba.dataset.modo;
        q('#area-simples').classList.toggle('oculto', modo !== 'SIMPLES');
        q('#area-multiplo').classList.toggle('oculto', modo === 'SIMPLES');
        q('#ajuda-modo').textContent = modo === 'SIMPLES'
          ? 'Uma classificação e uma parcela — ideal para o dia a dia.'
          : 'Divida o valor entre várias contas/centros de custo e gere quantas parcelas precisar.';
        if (modo === 'MULTIPLO' && !corpo.querySelectorAll('.linha-itens:not(.cabecalho)').length) {
          addItem();
          gerarParcelas();
        }
      };
    });

    UI.abrirModal({
      titulo: eh_receber ? 'Novo título a receber' : 'Novo título a pagar',
      corpo,
      largo: true,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        {
          rotulo: 'Salvar lançamento',
          classe: 'btn-primario',
          acao: async () => {
            try {
              const d = UI.lerFormulario(corpo);
              if (!d.descricao) return UI.erro('Informe a descrição.');
              if (!d.valor_total || d.valor_total <= 0) return UI.erro('Informe o valor total.');

              const payload = {
                empresa_id: Estado.empresaId,
                tipo,
                modo,
                descricao: d.descricao,
                numero_documento: d.numero_documento,
                parceiro_id: d.parceiro_id ? Number(d.parceiro_id) : null,
                operacao_id: d.operacao_id ? Number(d.operacao_id) : null,
                data_emissao: d.data_emissao,
                data_competencia: d.data_competencia || d.data_emissao,
                valor_total: Number(d.valor_total),
                observacao: d.observacao,
                itens: [],
                parcelas: [],
              };

              if (modo === 'SIMPLES') {
                if (!d.conta_simples) return UI.erro('Escolha a conta contábil.');
                payload.itens = [{
                  conta_contabil_id: Number(d.conta_simples),
                  centro_custo_id: d.centro_simples ? Number(d.centro_simples) : null,
                  operacao_id: payload.operacao_id,
                  descricao: d.descricao,
                  valor: payload.valor_total,
                }];
                payload.parcelas = [{
                  numero: 1,
                  data_vencimento: d.vencimento_simples || d.data_emissao,
                  valor: payload.valor_total,
                }];
                payload.baixar_agora = Boolean(d.baixar_agora);
                payload.banco_id = d.banco_id ? Number(d.banco_id) : null;
                if (payload.baixar_agora && !payload.banco_id) {
                  return UI.erro('Escolha a conta bancária para a baixa imediata.');
                }
              } else {
                corpo.querySelectorAll('#itens .linha-itens').forEach((linha) => {
                  const conta = linha.querySelector('[name=item_conta]').value;
                  const valor = Number(linha.querySelector('.item-valor').value || 0);
                  if (!conta || !valor) return;
                  payload.itens.push({
                    conta_contabil_id: Number(conta),
                    centro_custo_id: linha.querySelector('[name=item_centro]').value || null,
                    operacao_id: linha.querySelector('[name=item_operacao]').value || null,
                    valor,
                  });
                });
                corpo.querySelectorAll('#parcelas .linha-parcelas').forEach((linha, i) => {
                  const valor = Number(linha.querySelector('.parcela-valor').value || 0);
                  if (!valor) return;
                  payload.parcelas.push({
                    numero: i + 1,
                    data_vencimento: linha.querySelector('.parcela-venc').value,
                    valor,
                  });
                });
                if (!payload.itens.length) return UI.erro('Adicione ao menos uma linha de rateio.');
                if (!payload.parcelas.length) return UI.erro('Gere as parcelas do lançamento.');
              }

              await Api.post('/api/lancamentos', payload);
              UI.fecharModal();
              UI.sucesso('Lançamento salvo com sucesso.');
              App.recarregar();
            } catch (e) {
              UI.erro(e.message);
            }
          },
        },
      ],
    });
  },

  /* ==================================================================== BAIXA */
  /** Bloco com as contas/chaves cadastradas do parceiro, para pagar certo. */
  async blocoFormasParceiro(corpo, parcela, eh_receber) {
    if (!parcela.parceiro_id) return;
    let dados;
    try {
      dados = await Api.get(`/api/parceiros/${parcela.parceiro_id}/formas-pagamento`);
    } catch {
      return;
    }
    const ativas = (dados.formas || []).filter((f) => f.ativo);
    const area = corpo.querySelector('#formas-parceiro');
    if (!area) return;

    if (!ativas.length) {
      area.innerHTML = `
        <div class="mini">
          ${UI.escapar(parcela.parceiro_nome || 'Este cadastro')} ainda não tem
          ${eh_receber ? 'dados bancários' : 'forma de pagamento'} cadastrada.
          Cadastre em Clientes/Fornecedores → Pagamento.
        </div>`;
      return;
    }

    const principal = ativas.find((f) => f.principal) || ativas[0];
    area.innerHTML = `
      <div class="titulo-bloco" style="margin-top:0">
        ${eh_receber ? 'Dados bancários do cliente' : 'Onde pagar este fornecedor'}
      </div>
      <div class="forma-escolha">
        ${ativas.map((f) => `
          <label class="forma-opcao ${f.id === principal.id ? 'ativo' : ''}">
            <input type="radio" name="forma_parceiro_id" value="${f.id}" ${f.id === principal.id ? 'checked' : ''}>
            <span>
              <span class="forte">${UI.escapar(f.resumo)}</span>
              <span class="mini"> ${UI.escapar(f.tipo_nome)}${f.principal ? ' · principal' : ''}</span>
            </span>
            <button type="button" class="btn btn-mini" data-copiar-forma="${f.id}">Copiar</button>
          </label>`).join('')}
      </div>`;

    area.querySelectorAll('input[name=forma_parceiro_id]').forEach((radio) => {
      radio.onchange = () => {
        area.querySelectorAll('.forma-opcao').forEach((o) => o.classList.remove('ativo'));
        radio.closest('.forma-opcao').classList.add('ativo');
        const escolhida = ativas.find((f) => String(f.id) === radio.value);
        const forma = corpo.querySelector('[name=forma_pagamento]');
        if (escolhida && forma && escolhida.tipo === 'PIX') forma.value = 'PIX';
        if (escolhida && forma && ['DEPOSITO', 'TED'].includes(escolhida.tipo)) {
          forma.value = 'TRANSFERENCIA';
        }
      };
    });
    area.querySelectorAll('[data-copiar-forma]').forEach((b) => {
      b.onclick = async (e) => {
        e.preventDefault();
        const f = ativas.find((x) => String(x.id) === b.dataset.copiarForma);
        try {
          await navigator.clipboard.writeText(f.texto_copia);
          UI.sucesso('Dados copiados.');
        } catch {
          UI.aviso(f.texto_copia);
        }
      };
    });
    if (principal.tipo === 'PIX') corpo.querySelector('[name=forma_pagamento]').value = 'PIX';
  },

  baixar(parcela, tipo) {
    const eh_receber = tipo === 'RECEBER';
    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <div class="cartao" style="box-shadow:none;margin-bottom:14px">
        <div class="cartao-corpo">
          <div class="grade g3">
            <div><div class="mini">${eh_receber ? 'Cliente' : 'Fornecedor'}</div><div class="forte">${UI.escapar(parcela.parceiro_nome || '-')}</div></div>
            <div><div class="mini">Descrição</div><div class="forte">${UI.escapar(parcela.descricao)}</div></div>
            <div><div class="mini">Vencimento</div><div class="forte">${UI.data(parcela.data_vencimento)}</div></div>
            <div><div class="mini">Valor da parcela</div><div class="forte">${UI.moeda(parcela.valor)}</div></div>
            <div><div class="mini">Já baixado</div><div class="forte">${UI.moeda(parcela.valor_baixado)}</div></div>
            <div><div class="mini">Saldo</div><div class="forte">${UI.moeda(parcela.saldo)}</div></div>
          </div>
        </div>
      </div>
      <div id="formas-parceiro"></div>
      <div class="linha-campos" style="margin-top:12px">
        ${UI.campo('Conta bancária *', UI.select('banco_id', UI.opcoesBancos(), '', { obrigatorio: true }),
          eh_receber ? 'onde o dinheiro entra' : 'de onde o dinheiro sai')}
        ${UI.campo('Data da baixa', `<input type="date" name="data" value="${UI.hoje()}">`)}
        ${UI.campo('Valor do título a baixar', `<input type="number" step="0.01" name="valor" value="${parcela.saldo.toFixed(2)}">`)}
        ${UI.campo('Juros', '<input type="number" step="0.01" name="juros" value="0">')}
        ${UI.campo('Multa', '<input type="number" step="0.01" name="multa" value="0">')}
        ${UI.campo('Desconto', '<input type="number" step="0.01" name="desconto" value="0">')}
        ${UI.campo('Forma', UI.select('forma_pagamento', ['DINHEIRO', 'PIX', 'TRANSFERENCIA', 'BOLETO', 'CARTAO', 'CHEQUE', 'DEBITO AUTOMATICO']
          .map((v) => ({ valor: v, rotulo: v })), 'PIX', { vazio: false }))}
        ${UI.campo('Histórico', `<input name="historico" value="${UI.escapar(parcela.descricao)}">`)}
      </div>
      <div class="ok-caixa" id="resumo-baixa" style="margin-top:14px"></div>`;

    const atualizar = () => {
      const d = UI.lerFormulario(corpo);
      const liquido = Number(d.valor || 0) - Number(d.desconto || 0) + Number(d.juros || 0) + Number(d.multa || 0);
      corpo.querySelector('#resumo-baixa').innerHTML =
        `Valor que ${eh_receber ? 'entra' : 'sai'} na conta bancária: <span class="forte">${UI.moeda(liquido)}</span>`;
    };
    corpo.querySelectorAll('input[type=number]').forEach((i) => { i.oninput = atualizar; });
    atualizar();
    Lancamentos.blocoFormasParceiro(corpo, parcela, eh_receber);

    UI.abrirModal({
      titulo: eh_receber ? 'Receber título' : 'Pagar título',
      corpo,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        {
          rotulo: eh_receber ? 'Confirmar recebimento' : 'Confirmar pagamento',
          classe: 'btn-verde',
          acao: async () => {
            const d = UI.lerFormulario(corpo);
            if (!d.banco_id) return UI.erro('Escolha a conta bancária.');
            try {
              await Api.post(`/api/parcelas/${parcela.id}/baixar`, {
                banco_id: Number(d.banco_id),
                data: d.data,
                valor: Number(d.valor),
                juros: Number(d.juros || 0),
                multa: Number(d.multa || 0),
                desconto: Number(d.desconto || 0),
                forma_pagamento: d.forma_pagamento,
                forma_parceiro_id: d.forma_parceiro_id ? Number(d.forma_parceiro_id) : null,
                historico: d.historico,
              });
              UI.fecharModal();
              UI.sucesso('Baixa registrada.');
              App.recarregar();
            } catch (e) {
              UI.erro(e.message);
            }
          },
        },
      ],
    });
  },

  baixarLote(tipo) {
    const selecionadas = [...document.querySelectorAll('.sel-parcela:checked')]
      .map((c) => Lancamentos._parcelas[Number(c.dataset.indice)]);
    if (!selecionadas.length) return UI.erro('Selecione ao menos uma parcela na lista.');
    const total = selecionadas.reduce((s, p) => s + p.saldo, 0);

    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <div class="ok-caixa">${selecionadas.length} parcela(s) selecionada(s) — total ${UI.moeda(total)}</div>
      <div class="linha-campos">
        ${UI.campo('Conta bancária *', UI.select('banco_id', UI.opcoesBancos(), '', { obrigatorio: true }))}
        ${UI.campo('Data', `<input type="date" name="data" value="${UI.hoje()}">`)}
        ${UI.campo('Forma', UI.select('forma_pagamento', ['DINHEIRO', 'PIX', 'TRANSFERENCIA', 'BOLETO', 'CARTAO', 'CHEQUE']
          .map((v) => ({ valor: v, rotulo: v })), 'PIX', { vazio: false }))}
      </div>
      <div class="mini" style="margin-top:10px">As parcelas serão baixadas pelo saldo total, sem juros ou desconto.</div>`;

    UI.abrirModal({
      titulo: 'Baixa em lote',
      corpo,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        {
          rotulo: 'Confirmar baixas',
          classe: 'btn-verde',
          acao: async () => {
            const d = UI.lerFormulario(corpo);
            if (!d.banco_id) return UI.erro('Escolha a conta bancária.');
            try {
              const r = await Api.post('/api/parcelas/baixar-lote', {
                parcela_ids: selecionadas.map((p) => p.id),
                banco_id: Number(d.banco_id),
                data: d.data,
                forma_pagamento: d.forma_pagamento,
              });
              UI.fecharModal();
              UI.sucesso(`${r.quantidade} baixa(s) registrada(s).`);
              App.recarregar();
            } catch (e) {
              UI.erro(e.message);
            }
          },
        },
      ],
    });
  },

  /* ============================================================== VER TÍTULO */
  async verTitulo(id) {
    const l = await Api.get(`/api/lancamentos/${id}`);
    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <div class="grade g3" style="margin-bottom:16px">
        <div><div class="mini">Tipo</div><div class="forte">${l.tipo === 'RECEBER' ? 'Conta a receber' : 'Conta a pagar'}</div></div>
        <div><div class="mini">Documento</div><div class="forte">${UI.escapar(l.numero_documento || '-')}</div></div>
        <div><div class="mini">Cliente/Fornecedor</div><div class="forte">${UI.escapar(l.parceiro_nome || '-')}</div></div>
        <div><div class="mini">Emissão</div><div class="forte">${UI.data(l.data_emissao)}</div></div>
        <div><div class="mini">Competência</div><div class="forte">${UI.data(l.data_competencia)}</div></div>
        <div><div class="mini">Operação</div><div class="forte">${UI.escapar(l.operacao_nome || '-')}</div></div>
        <div><div class="mini">Valor total</div><div class="forte">${UI.moeda(l.valor_total)}</div></div>
        <div><div class="mini">Baixado</div><div class="forte">${UI.moeda(l.total_baixado)}</div></div>
        <div><div class="mini">Situação</div><div>${UI.tagStatus(l.status)}</div></div>
      </div>

      <h4 style="margin:14px 0 6px">Classificação (rateio)</h4>
      ${UI.tabela({
        colunas: [
          { titulo: 'Conta contábil', valor: (i) => `${UI.escapar(i.conta_contabil_codigo)} — ${UI.escapar(i.conta_contabil_nome)}` },
          { titulo: 'Centro de custo', valor: (i) => UI.escapar(i.centro_custo_nome || '-') },
          { titulo: 'Operação', valor: (i) => UI.escapar(i.operacao_nome || '-') },
          { titulo: 'Valor', classe: 'num', valor: (i) => UI.moeda(i.valor) },
        ],
        linhas: l.itens,
      })}

      <h4 style="margin:16px 0 6px">Parcelas e baixas</h4>
      ${UI.tabela({
        colunas: [
          { titulo: 'Nº', classe: 'centro', valor: (p) => p.numero },
          { titulo: 'Vencimento', valor: (p) => UI.data(p.data_vencimento) },
          { titulo: 'Valor', classe: 'num', valor: (p) => UI.moeda(p.valor) },
          { titulo: 'Baixado', classe: 'num', valor: (p) => UI.moeda(p.valor_baixado) },
          { titulo: 'Juros/multa', classe: 'num', valor: (p) => UI.moeda(p.juros_multa) },
          { titulo: 'Desconto', classe: 'num', valor: (p) => UI.moeda(p.desconto) },
          { titulo: 'Saldo', classe: 'num', valor: (p) => UI.moeda(p.saldo) },
          { titulo: 'Situação', classe: 'centro', valor: (p) => UI.tagStatus(p.status, p.vencida) },
          {
            titulo: 'Baixas',
            valor: (p) => (p.baixas.length
              ? p.baixas.map((b) => `<div class="mini">${UI.data(b.data)} — ${UI.moeda(b.valor_liquido)} (${UI.escapar(b.banco_nome || '')})${b.forma_parceiro ? `<br>via ${UI.escapar(b.forma_parceiro)}` : ''} <button class="btn btn-mini btn-perigo" data-estornar="${b.id}">Estornar</button></div>`).join('')
              : '<span class="mini">—</span>'),
          },
        ],
        linhas: l.parcelas,
      })}`;

    corpo.querySelectorAll('[data-estornar]').forEach((b) => {
      b.onclick = async () => {
        if (!(await UI.confirmar('Estornar esta baixa? O movimento no caixa e a contabilização serão desfeitos.', 'Estornar'))) return;
        try {
          await Api.del(`/api/baixas/${b.dataset.estornar}`);
          UI.fecharModal();
          UI.sucesso('Baixa estornada.');
          App.recarregar();
        } catch (e) {
          UI.erro(e.message);
        }
      };
    });

    UI.abrirModal({
      titulo: `Título #${l.id} — ${l.descricao}`,
      corpo,
      largo: true,
      botoes: [
        {
          rotulo: 'Excluir título',
          classe: 'btn-perigo',
          acao: async () => {
            if (!(await UI.confirmar('Excluir definitivamente este título?', 'Excluir'))) return;
            try {
              await Api.del(`/api/lancamentos/${l.id}`);
              UI.fecharModal();
              UI.sucesso('Título excluído.');
              App.recarregar();
            } catch (e) {
              UI.erro(e.message);
            }
          },
        },
        { rotulo: 'Fechar', classe: 'btn-primario', acao: UI.fecharModal },
      ],
    });
  },
};
