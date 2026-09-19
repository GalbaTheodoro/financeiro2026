/* Emissão de NF-e — a nota que a sua empresa emite e manda para a SEFAZ.

   Fluxo: rascunho -> conferir na prévia -> transmitir -> autorizada.
   Rascunho não gasta número da série; o número só é usado na transmissão.
   Nota autorizada não se apaga: se precisar, cancela na SEFAZ (com justificativa). */
const Emissao = {
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
  formulario(dados, preparo) {
    const n = dados.nota;
    const editavel = n.pode_editar;
    Emissao._itens = (dados.itens || []).map((i) => ({ ...i }));
    Emissao._parcelas = (dados.parcelas || []).map((p) => ({ ...p }));
    if (!Emissao._itens.length) Emissao._itens.push(Emissao.itemVazio());

    const corpo = document.createElement('div');
    corpo.innerHTML = `
      ${Emissao.faixaPendencias(preparo)}
      ${Emissao.faixaSituacao(n)}
      <div class="linha-campos">
        ${UI.campo('Cliente', UI.select('parceiro_id', UI.opcoesParceiros(),
          n.parceiro_id || '', { obrigatorio: true }))}
        ${UI.campo('Natureza da operação',
          `<input name="natureza_operacao" value="${UI.escapar(n.natureza_operacao || 'VENDA DE MERCADORIA')}">`)}
        ${UI.campo('Série', `<input name="serie" value="${UI.escapar(n.serie || '1')}" style="max-width:90px">`,
          'a numeração é automática')}
        ${UI.campo('Data de emissão',
          `<input type="date" name="data_emissao" value="${(n.data_emissao || UI.hoje()).slice(0, 10)}">`)}
        ${UI.campo('Finalidade', UI.select('finalidade',
          (preparo.finalidades || []).map((f) => ({ valor: f.codigo, rotulo: f.nome })),
          n.finalidade || '1', { vazio: false }))}
        ${UI.campo('Ambiente', UI.select('ambiente', [
          { valor: '2', rotulo: 'Homologação (teste)' },
          { valor: '1', rotulo: 'Produção (vale de verdade)' },
        ], n.ambiente || '2', { vazio: false }), 'comece sempre em homologação')}
      </div>

      <h4 style="margin:16px 0 6px">Itens</h4>
      <div id="itens-nfe"></div>
      ${editavel ? '<button class="btn btn-mini" id="btn-add-item" style="margin-top:8px">+ Adicionar item</button>' : ''}

      <h4 style="margin:16px 0 6px">Parcelas (duplicatas)</h4>
      <div id="parcelas-nfe"></div>
      ${editavel ? `<div class="espaco" style="margin-top:8px">
        <button class="btn btn-mini" id="btn-add-parcela">+ Adicionar parcela</button>
        <button class="btn btn-mini" id="btn-parcela-unica">Uma parcela com o total</button>
      </div>` : ''}

      <h4 style="margin:16px 0 6px">Transporte</h4>
      <div class="linha-campos">
        ${UI.campo('Frete por conta', UI.select('frete_modalidade',
          (preparo.modalidades_frete || []).map((f) => ({ valor: f.codigo, rotulo: f.nome })),
          n.frete_modalidade || '9', { vazio: false }))}
        ${UI.campo('Transportadora', UI.select('transportadora_id', UI.opcoesParceiros(),
          n.transportadora_id || '', { vazio: 'Nenhuma' }))}
        ${UI.campo('Placa', `<input name="placa_veiculo" value="${UI.escapar(n.placa_veiculo || '')}" maxlength="8">`)}
        ${UI.campo('UF do veículo', `<input name="uf_veiculo" value="${UI.escapar(n.uf_veiculo || '')}" maxlength="2">`)}
        ${UI.campo('Volumes', `<input type="number" name="volumes" value="${n.volumes ?? ''}">`)}
        ${UI.campo('Espécie', `<input name="especie_volume" value="${UI.escapar(n.especie_volume || '')}" placeholder="sacas, caixas...">`)}
        ${UI.campo('Peso líquido (kg)', `<input type="number" step="0.001" name="peso_liquido" value="${n.peso_liquido || 0}">`)}
        ${UI.campo('Peso bruto (kg)', `<input type="number" step="0.001" name="peso_bruto" value="${n.peso_bruto || 0}">`)}
      </div>

      <h4 style="margin:16px 0 6px">Informações complementares</h4>
      <div class="linha-campos">
        ${UI.campo('Texto que sai na nota',
          `<textarea name="informacoes_complementares" rows="2">${UI.escapar(n.informacoes_complementares || '')}</textarea>`,
          'contrato, pedido, observações fiscais')}
      </div>
      <div class="mini" style="margin-top:10px" id="total-nfe"></div>`;

    UI.abrirModal({
      titulo: n.numero
        ? `NF-e ${n.numero} — série ${n.serie}`
        : 'Nova NF-e (rascunho)',
      corpo,
      largo: true,
      botoes: Emissao.botoes(n, editavel),
    });

    Emissao._nota = n;
    Emissao._preparo = preparo;
    Emissao.desenharItens(editavel);
    Emissao.desenharParcelas(editavel);
    if (editavel) {
      corpo.querySelector('#btn-add-item').onclick = () => {
        Emissao._itens.push(Emissao.itemVazio());
        Emissao.desenharItens(true);
      };
      corpo.querySelector('#btn-add-parcela').onclick = () => {
        Emissao._parcelas.push({ vencimento: UI.hoje(), valor: 0 });
        Emissao.desenharParcelas(true);
      };
      corpo.querySelector('#btn-parcela-unica').onclick = () => {
        Emissao._parcelas = [{ vencimento: UI.hoje(), valor: Emissao.total() }];
        Emissao.desenharParcelas(true);
      };
    } else {
      corpo.querySelectorAll('input,select,textarea').forEach((c) => { c.disabled = true; });
    }
  },

  /* Aviso no alto do formulário quando ainda falta cadastro para transmitir. */
  faixaPendencias(preparo) {
    if (preparo.pronto) return '';
    return `<div class="cartao" style="margin-bottom:12px;border-left:4px solid var(--ambar)">
      <div class="cartao-corpo"><b>Dá para montar a nota, mas ainda não dá para transmitir.</b>
        <div class="mini">Falta: ${preparo.pendencias.map((p) => UI.escapar(p)).join(' · ')}</div>
      </div></div>`;
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
    return `<div class="cartao" style="margin-bottom:14px;border-left:4px solid ${cores[situacao]}">
      <div class="cartao-corpo">
        <b>${UI.escapar(textos[situacao] || situacao)}</b>
        ${n.ambiente === '2' ? '<div class="mini">Ambiente de <b>homologação</b>: a nota não tem valor fiscal.</div>' : ''}
        ${n.mensagem_sefaz ? `<div class="mini">SEFAZ: ${UI.escapar(n.codigo_sefaz || '')} — ${UI.escapar(n.mensagem_sefaz)}</div>` : ''}
        ${n.protocolo ? `<div class="mini">Protocolo ${UI.escapar(n.protocolo)} · chave ${UI.escapar(n.chave_formatada || '')}</div>` : ''}
      </div></div>`;
  },

  botoes(n, editavel) {
    const lista = [{ rotulo: 'Fechar', acao: UI.fecharModal }];
    if (n.status_emissao === 'RASCUNHO') {
      lista.push({ rotulo: 'Excluir', classe: 'btn-perigo', acao: () => Emissao.excluir(n) });
    }
    lista.push({ rotulo: 'Prévia (DANFE)', acao: () => Emissao.previa(n.id) });
    if (editavel) {
      lista.push({ rotulo: 'Salvar', acao: () => Emissao.salvar(n.id, false) });
      lista.push({ rotulo: 'Transmitir à SEFAZ', classe: 'btn-primario',
        acao: () => Emissao.salvar(n.id, true) });
    }
    if (n.pode_cancelar) {
      lista.push({ rotulo: 'Cancelar na SEFAZ', classe: 'btn-perigo',
        acao: () => Emissao.cancelar(n) });
    }
    return lista;
  },

  itemVazio() {
    return { produto_id: '', descricao: '', unidade: '', quantidade: 0, valor_unitario: 0,
             cfop: '', ncm: '', icms_cst: '', desconto: 0 };
  },

  total() {
    return Emissao._itens.reduce(
      (s, i) => s + (Number(i.quantidade || 0) * Number(i.valor_unitario || 0)
        - Number(i.desconto || 0)), 0);
  },

  desenharItens(editavel) {
    const alvo = document.getElementById('itens-nfe');
    const produtos = Api.produtosAtivos();
    alvo.innerHTML = Emissao._itens.map((item, i) => `
      <div class="linha-campos" data-item="${i}" style="align-items:end;margin-bottom:8px">
        ${UI.campo('Produto', UI.select(`produto_${i}`,
          produtos.map((p) => ({ valor: p.id, rotulo: `${p.codigo} — ${p.nome}` })),
          item.produto_id || '', { vazio: 'Digitar à mão' }))}
        ${UI.campo('Descrição', `<input data-campo="descricao" data-linha="${i}" value="${UI.escapar(item.descricao || '')}">`)}
        ${UI.campo('CFOP', `<input data-campo="cfop" data-linha="${i}" value="${UI.escapar(item.cfop || '')}" style="max-width:90px">`)}
        ${UI.campo('Un.', `<input data-campo="unidade" data-linha="${i}" value="${UI.escapar(item.unidade || '')}" style="max-width:80px">`)}
        ${UI.campo('Quantidade', `<input type="number" step="0.001" data-campo="quantidade" data-linha="${i}" value="${item.quantidade || 0}">`)}
        ${UI.campo('Valor unitário', `<input type="number" step="0.0001" data-campo="valor_unitario" data-linha="${i}" value="${item.valor_unitario || 0}">`)}
        ${UI.campo('Total', `<input value="${UI.moeda(Number(item.quantidade || 0) * Number(item.valor_unitario || 0) - Number(item.desconto || 0))}" disabled>`)}
        ${editavel ? `<div class="acoes"><button class="btn btn-mini btn-perigo" data-remover="${i}">Remover</button></div>` : ''}
      </div>`).join('');

    alvo.querySelectorAll('[data-campo]').forEach((campo) => {
      campo.oninput = () => {
        const item = Emissao._itens[Number(campo.dataset.linha)];
        item[campo.dataset.campo] = campo.type === 'number' ? Number(campo.value) : campo.value;
        Emissao.mostrarTotal();
        if (['quantidade', 'valor_unitario'].includes(campo.dataset.campo)) {
          Emissao.desenharItens(editavel);
        }
      };
    });
    alvo.querySelectorAll('select[name^=produto_]').forEach((select) => {
      select.onchange = () => {
        const i = Number(select.name.split('_')[1]);
        const produto = produtos.find((p) => String(p.id) === select.value);
        Emissao._itens[i].produto_id = select.value || '';
        if (produto) {
          Object.assign(Emissao._itens[i], {
            descricao: produto.nome, unidade: produto.unidade_comercial || '',
            cfop: produto.cfop_padrao || '', ncm: produto.ncm || '',
            icms_cst: produto.cst_icms || '',
          });
        }
        Emissao.desenharItens(editavel);
      };
    });
    alvo.querySelectorAll('[data-remover]').forEach((botao) => {
      botao.onclick = () => {
        Emissao._itens.splice(Number(botao.dataset.remover), 1);
        if (!Emissao._itens.length) Emissao._itens.push(Emissao.itemVazio());
        Emissao.desenharItens(editavel);
      };
    });
    Emissao.mostrarTotal();
  },

  desenharParcelas(editavel) {
    const alvo = document.getElementById('parcelas-nfe');
    if (!Emissao._parcelas.length) {
      alvo.innerHTML = '<div class="mini">Sem parcelas — a nota sai como pagamento à vista.</div>';
      return;
    }
    alvo.innerHTML = Emissao._parcelas.map((p, i) => `
      <div class="linha-campos" data-parcela="${i}" style="align-items:end;margin-bottom:6px">
        ${UI.campo(`Parcela ${i + 1}`, `<input type="date" data-parc="vencimento" data-linha="${i}" value="${(p.vencimento || '').slice(0, 10)}">`)}
        ${UI.campo('Valor', `<input type="number" step="0.01" data-parc="valor" data-linha="${i}" value="${p.valor || 0}">`)}
        ${editavel ? `<div class="acoes"><button class="btn btn-mini btn-perigo" data-rem-parc="${i}">Remover</button></div>` : ''}
      </div>`).join('');
    alvo.querySelectorAll('[data-parc]').forEach((campo) => {
      campo.oninput = () => {
        const p = Emissao._parcelas[Number(campo.dataset.linha)];
        p[campo.dataset.parc] = campo.type === 'number' ? Number(campo.value) : campo.value;
        Emissao.mostrarTotal();
      };
    });
    alvo.querySelectorAll('[data-rem-parc]').forEach((botao) => {
      botao.onclick = () => {
        Emissao._parcelas.splice(Number(botao.dataset.remParc), 1);
        Emissao.desenharParcelas(editavel);
      };
    });
  },

  mostrarTotal() {
    const alvo = document.getElementById('total-nfe');
    if (!alvo) return;
    const total = Emissao.total();
    const parcelas = Emissao._parcelas.reduce((s, p) => s + Number(p.valor || 0), 0);
    const diferenca = Math.round((total - parcelas) * 100) / 100;
    alvo.innerHTML = `Total da nota: <b>${UI.moeda(total)}</b>`
      + (Emissao._parcelas.length
        ? ` · parcelas: ${UI.moeda(parcelas)}${diferenca
          ? ` <span class="negativo">(diferença de ${UI.moeda(diferenca)})</span>` : ''}`
        : '');
  },

  /* ================================================================= AÇÕES */
  corpoFormulario() {
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
      volumes: dados.volumes || null,
      especie_volume: dados.especie_volume || null,
      peso_liquido: dados.peso_liquido || 0,
      peso_bruto: dados.peso_bruto || 0,
      informacoes_complementares: dados.informacoes_complementares || null,
      itens: Emissao._itens
        .filter((i) => Number(i.quantidade || 0) > 0)
        .map((i) => ({
          produto_id: i.produto_id || null,
          descricao: i.descricao || null,
          cfop: i.cfop || null,
          ncm: i.ncm || null,
          unidade: i.unidade || null,
          quantidade: Number(i.quantidade || 0),
          valor_unitario: Number(i.valor_unitario || 0),
          desconto: Number(i.desconto || 0),
          icms_cst: i.icms_cst || null,
        })),
      parcelas: Emissao._parcelas
        .filter((p) => p.vencimento && Number(p.valor || 0) > 0)
        .map((p, i) => ({ numero: String(i + 1).padStart(3, '0'),
                          vencimento: p.vencimento, valor: Number(p.valor) })),
    };
  },

  async salvar(notaId, transmitir) {
    const payload = Emissao.corpoFormulario();
    if (!payload.parceiro_id) return UI.erro('Escolha o cliente da nota.');
    if (!payload.itens.length) return UI.erro('A nota precisa de pelo menos um item com quantidade.');
    try {
      const salvo = await Api.put(`/api/nfe/${notaId}`, payload);
      if (!transmitir) {
        UI.sucesso('Rascunho salvo.');
        return Emissao.formulario(salvo, Emissao._preparo);
      }
      Emissao.confirmarTransmissao(salvo.nota);
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
              UI.fecharModal();
              if (r.ok) UI.sucesso(r.mensagem);
              else UI.erro(r.mensagem);
              if (typeof Notas !== 'undefined' && Notas._linhas) Notas.tela();
              Emissao.abrir(n.id);
            } catch (e) {
              UI.erro(e.message);
              Emissao.abrir(n.id);
            }
          },
        },
      ],
    });
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
              UI.fecharModal();
              UI.sucesso(r.mensagem);
              if (typeof Notas !== 'undefined') Notas.tela();
            } catch (e) {
              UI.erro(e.message);
              Emissao.abrir(n.id);
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
      <h4 style="margin:16px 0 6px">Ajustar</h4>
      <div class="linha-campos">
        ${UI.campo('Série', '<input name="serie" value="1" style="max-width:90px">')}
        ${UI.campo('Ambiente', UI.select('ambiente', [
          { valor: '2', rotulo: 'Homologação' }, { valor: '1', rotulo: 'Produção' },
        ], '2', { vazio: false }))}
        ${UI.campo('Próximo número', '<input type="number" name="proximo_numero" value="1" min="1">')}
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
              await Api.post('/api/nfe/series', { empresa_id: Estado.empresaId, ...dados });
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
