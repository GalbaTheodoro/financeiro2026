/* Amostras de café — cadastro, classificação e laudo.

   O caminho de todo dia: a amostra chega (produtor, lote, sacas), o
   classificador conta os defeitos, passa nas peneiras, prova a xícara, e o
   laudo sai impresso com o gráfico de aranha da prova.

   A conta não é feita aqui: a cada mudança a tela pergunta ao servidor
   (/api/amostras/calcular), e o servidor calcula de novo ao salvar. Assim a
   regra da classificação mora num lugar só (backend/classificacao.py). */
const Amostras = {
  _tabelas: null,
  _dados: null,
  _filtros: { de: '', ate: '', situacao: '', busca: '' },
  _contratos: [],
  _resultado: null,
  _tempo: null,

  SITUACOES: [
    { valor: 'RECEBIDA', rotulo: 'Recebida (a classificar)' },
    { valor: 'CLASSIFICADA', rotulo: 'Classificada' },
  ],
  UFS: ['AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA',
    'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO'],

  /* ================================================================ LISTA */
  async tela() {
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';
    if (!Amostras._tabelas) Amostras._tabelas = await Api.get('/api/amostras/tabelas');
    await Amostras.carregar();
  },

  async carregar() {
    Amostras._dados = await Api.get('/api/amostras', {
      empresa_id: Estado.empresaId, ...Amostras._filtros,
    });
    Amostras.desenhar();
  },

  desenhar() {
    const d = Amostras._dados;
    const r = d.resumo;
    const f = Amostras._filtros;
    document.getElementById('pagina').innerHTML = `
      <div class="grade g4" style="margin-bottom:18px">
        ${Amostras.kpi('Amostras', r.total, `${r.sacas.toLocaleString('pt-BR')} sacas no total`, 'destaque-azul')}
        ${Amostras.kpi('A classificar', r.recebidas, 'recebidas, ainda sem laudo',
          r.recebidas ? 'destaque-vermelho' : 'destaque-verde')}
        ${Amostras.kpi('Classificadas', r.classificadas, 'com laudo')}
        ${Amostras.kpi('Cafés especiais', r.especiais,
          r.media_pontos ? `média ${UI.numero(r.media_pontos)} pontos na prova` : '80 pontos ou mais na prova')}
      </div>
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Amostras de café</h3>
            <div class="mini">tipo pelos defeitos (COB — IN MAPA 8/2003), peneiras, bebida e
              prova de xícara (SCA). O laudo sai impresso com o gráfico de aranha.</div></div>
          <button class="btn btn-verde" id="btn-nova-amostra">+ Nova amostra</button>
        </div>
        <div class="filtros">
          ${UI.campo('Recebida de', `<input type="date" name="de" value="${f.de}">`)}
          ${UI.campo('até', `<input type="date" name="ate" value="${f.ate}">`)}
          ${UI.campo('Situação', UI.select('situacao', Amostras.SITUACOES, f.situacao, { vazio: 'Todas' }))}
          ${UI.campo('Buscar', `<input name="busca" value="${UI.escapar(f.busca)}" placeholder="nº, produtor, fazenda, lote, padrão">`)}
          <div class="acoes"><button class="btn btn-primario" id="btn-filtrar-amostras">Filtrar</button></div>
        </div>
        <div class="cartao-corpo sem-padding">${Amostras.tabela(d.amostras)}</div>
      </div>`;
    Amostras.ligarLista();
  },

  kpi(rotulo, valor, nota, classe = '') {
    return `<div class="kpi ${classe}"><div class="kpi-rotulo">${UI.escapar(rotulo)}</div>
      <div class="kpi-valor">${valor}</div><div class="kpi-nota">${UI.escapar(nota)}</div></div>`;
  },

  tabela(linhas) {
    return UI.tabela({
      linhas,
      vazio: 'Nenhuma amostra ainda. Clique em "+ Nova amostra" para cadastrar a primeira.',
      colunas: [
        { titulo: 'Nº', valor: (a) => `<span class="forte">${Amostras.numero(a.numero)}</span>
            <div class="mini">${UI.data(a.data_recebimento)}</div>` },
        { titulo: 'Produtor', valor: (a) => `${UI.escapar(a.produtor_nome || a.parceiro_nome || '-')}
            <div class="mini">${UI.escapar([a.fazenda, a.municipio && `${a.municipio}/${a.uf || ''}`]
              .filter(Boolean).join(' · '))}</div>` },
        { titulo: 'Lote', valor: (a) => `${UI.escapar(a.lote || '-')}
            <div class="mini">${a.sacas ? `${UI.numero(a.sacas, 0)} sacas` : ''}</div>` },
        { titulo: 'Tipo', classe: 'centro', valor: (a) => (a.tipo
          ? `<span class="forte">${UI.escapar(a.tipo)}</span><div class="mini">${UI.numero(a.total_defeitos, 0)} defeitos</div>`
          : '<span class="mini">—</span>') },
        { titulo: 'Bebida', valor: (a) => UI.escapar(a.bebida || '—') },
        { titulo: 'Pontos', classe: 'num', valor: (a) => (a.pontuacao
          ? `<span class="forte ${a.pontuacao >= 80 ? 'positivo' : ''}">${UI.numero(a.pontuacao)}</span>` : '—') },
        { titulo: 'Padrão', valor: (a) => `<span class="mini">${UI.escapar(a.padrao || '')}</span>` },
        { titulo: 'Situação', classe: 'centro', valor: (a) => `<span class="tag ${
          a.situacao === 'CLASSIFICADA' ? 'tag-pago' : 'tag-aberto'}">${
          a.situacao === 'CLASSIFICADA' ? 'Classificada' : 'A classificar'}</span>` },
        { titulo: 'Ações', classe: 'centro', valor: (a) => `
            <button class="btn btn-mini" data-abrir="${a.id}">Abrir</button>
            <button class="btn btn-mini" data-laudo="${a.id}">Laudo</button>` },
      ],
    });
  },

  numero(n) { return String(n || 0).padStart(5, '0'); },

  ligarLista() {
    const pagina = document.getElementById('pagina');
    pagina.querySelector('#btn-nova-amostra').onclick = () => Amostras.abrir(null);
    pagina.querySelector('#btn-filtrar-amostras').onclick = () => {
      Object.assign(Amostras._filtros, UI.lerFormulario(pagina.querySelector('.filtros')));
      Object.keys(Amostras._filtros).forEach((k) => { Amostras._filtros[k] = Amostras._filtros[k] || ''; });
      Amostras.carregar().catch((e) => UI.erro(e.message));
    };
    pagina.querySelectorAll('[data-abrir]').forEach((b) => {
      b.onclick = () => Amostras.abrir(Number(b.dataset.abrir));
    });
    pagina.querySelectorAll('[data-laudo]').forEach((b) => {
      b.onclick = () => Amostras.laudo(Number(b.dataset.laudo));
    });
  },

  /* ================================================================ FORMULÁRIO */
  async abrir(id) {
    try {
      const amostra = id ? await Api.get(`/api/amostras/${id}`) : null;
      if (!Amostras._contratos.length) {
        try {
          const c = await Api.get('/api/contratos', { empresa_id: Estado.empresaId });
          Amostras._contratos = Array.isArray(c) ? c : (c.contratos || c.linhas || []);
        } catch (e) { Amostras._contratos = []; }
      }
      Amostras.formulario(amostra);
    } catch (e) {
      UI.erro(e.message);
    }
  },

  formulario(amostra) {
    const a = amostra || { situacao: 'RECEBIDA', especie: 'ARABICA', peso_amostra: 300,
      peso_peneiras: 100, data_recebimento: UI.hoje(), defeitos: {}, peneiras: {}, sensorial: {} };
    const t = Amostras._tabelas;
    const esc = UI.escapar;
    const v = (campo) => esc(a[campo] ?? '');
    const lista = (itens) => itens.map((x) => ({ valor: x, rotulo: x }));
    const dic = (obj) => Object.entries(obj).map(([valor, rotulo]) => ({ valor, rotulo }));
    const num = (nome, valor, extra = '') => `<input type="number" name="${nome}" value="${
      valor ?? ''}" min="0" step="any" ${extra}>`;

    const defeitosPorGrupo = (grupo) => t.defeitos.filter((x) => x.grupo === grupo).map((x) => UI.campo(
      x.rotulo, num(`def_${x.chave}`, a.defeitos[x.chave], 'step="1"'),
      x.vale > 1 ? `1 = ${x.vale} defeitos` : (x.unidades > 1 ? `${x.unidades} = 1 defeito` : '1 = 1 defeito'),
    )).join('');

    const peneirasDe = (formato) => t.peneiras.filter((x) => x.formato === formato).map((x) => UI.campo(
      formato === 'Fundo' ? 'Fundo' : `${formato} ${x.rotulo}`,
      num(`pen_${x.chave}`, a.peneiras[x.chave]),
    )).join('');

    const atributos = t.atributos.map((x) => UI.campo(x.rotulo,
      num(`sen_${x.chave}`, a.sensorial[x.chave], 'max="10" step="0.25"'))).join('');

    UI.abrirModal({
      titulo: a.id ? `Amostra ${Amostras.numero(a.numero)}` : 'Nova amostra de café',
      largo: true,
      corpo: `
        <div class="abas" id="abas-amostra">
          <button type="button" class="aba ativa" data-parte="identificacao">Amostra</button>
          <button type="button" class="aba" data-parte="fisica">Classificação física</button>
          <button type="button" class="aba" data-parte="peneiras">Peneiras</button>
          <button type="button" class="aba" data-parte="sensorial">Sensorial</button>
        </div>

        <div class="parte-amostra" data-parte="identificacao">
          <div class="linha-campos">
            ${UI.campo('Situação', UI.select('situacao', Amostras.SITUACOES, a.situacao, { vazio: false }))}
            ${UI.campo('Recebida em', `<input type="date" name="data_recebimento" value="${a.data_recebimento || ''}">`)}
            ${UI.campo('Classificada em', `<input type="date" name="data_classificacao" value="${a.data_classificacao || ''}">`)}
            ${UI.campo('Espécie', UI.select('especie', dic(t.especies), a.especie || 'ARABICA', { vazio: false }))}
          </div>
          <h4 class="titulo-bloco">Produtor e lote</h4>
          <div class="linha-campos">
            ${UI.campo('Produtor no cadastro', UI.select('parceiro_id', UI.opcoesParceiros(), a.parceiro_id || '',
              { vazio: 'Não está no cadastro' }), 'nome, cidade e UF vêm do cadastro')}
            ${UI.campo('Nome do produtor', `<input name="produtor_nome" value="${v('produtor_nome')}">`)}
            ${UI.campo('Fazenda / sítio', `<input name="fazenda" value="${v('fazenda')}">`)}
          </div>
          <div class="linha-campos">
            ${UI.campo('Município', `<input name="municipio" value="${v('municipio')}">`)}
            ${UI.campo('UF', UI.select('uf', lista(Amostras.UFS), a.uf || '', { vazio: '—' }))}
            ${UI.campo('Lote', `<input name="lote" value="${v('lote')}">`)}
            ${UI.campo('Sacas do lote', num('sacas', a.sacas || ''))}
            ${UI.campo('Armazém', `<input name="armazem" value="${v('armazem')}">`)}
          </div>
          <div class="linha-campos">
            ${UI.campo('Safra', `<input name="safra" value="${v('safra')}" placeholder="2025/2026" maxlength="9">`)}
            ${UI.campo('Variedade', `<input name="variedade" value="${v('variedade')}" placeholder="Catuaí, Mundo Novo...">`)}
            ${UI.campo('Preparo', UI.select('preparo', dic(t.preparos), a.preparo || '', { vazio: '—' }))}
            ${UI.campo('Altitude (m)', num('altitude', a.altitude || ''))}
            ${UI.campo('Contrato', UI.select('contrato_id', Amostras._contratos.map((c) => ({
              valor: c.id, rotulo: `${c.numero}${c.comprador_nome || c.vendedor_nome ? ` — ${c.comprador_nome || c.vendedor_nome}` : ''}`,
            })), a.contrato_id || '', { vazio: 'Sem contrato' }))}
          </div>
        </div>

        <div class="parte-amostra oculto" data-parte="fisica">
          <div class="linha-campos">
            ${UI.campo('Peso da amostra (g)', num('peso_amostra', a.peso_amostra ?? 300), 'a COB conta em 300 g')}
            ${UI.campo('Umidade (%)', num('umidade', a.umidade ?? '', 'max="100"'))}
            ${UI.campo('Catação (%)', num('catacao', a.catacao ?? '', 'max="100"'))}
            ${UI.campo('Impurezas (%)', num('impurezas', a.impurezas ?? '', 'max="100"'), 'acima de 1% desclassifica')}
          </div>
          <div class="linha-campos">
            ${UI.campo('Cor', UI.select('cor', lista(t.cores), a.cor || '', { vazio: '—' }))}
            ${UI.campo('Aspecto', UI.select('aspecto', lista(t.aspectos), a.aspecto || '', { vazio: '—' }))}
            ${UI.campo('Torração', UI.select('torracao', lista(t.torracoes), a.torracao || '', { vazio: '—' }))}
          </div>
          <h4 class="titulo-bloco">Defeitos — grãos (quantos achou na amostra)</h4>
          <div class="linha-campos">${defeitosPorGrupo('Grãos')}</div>
          <h4 class="titulo-bloco">Defeitos — impurezas</h4>
          <div class="linha-campos">${defeitosPorGrupo('Impurezas')}</div>
        </div>

        <div class="parte-amostra oculto" data-parte="peneiras">
          <div class="linha-campos">
            ${UI.campo('Peso passado nas peneiras (g)', num('peso_peneiras', a.peso_peneiras ?? 100),
              'normalmente 100 g; digite em cada peneira quanto ficou retido')}
          </div>
          <h4 class="titulo-bloco">Chato</h4>
          <div class="linha-campos">${peneirasDe('Chato')}</div>
          <h4 class="titulo-bloco">Moca</h4>
          <div class="linha-campos">${peneirasDe('Moca')}${peneirasDe('Fundo')}</div>
        </div>

        <div class="parte-amostra oculto" data-parte="sensorial">
          <div class="linha-campos">
            ${UI.campo('Bebida', UI.select('bebida',
              lista(a.especie === 'CONILON' ? t.bebidas_conilon : t.bebidas), a.bebida || '', { vazio: '—' }))}
            ${UI.campo('Gostos estranhos', `<input name="gostos_estranhos" value="${v('gostos_estranhos')}"
              list="lista-gostos" placeholder="fermentado, mofo...">`)}
            ${UI.campo('Descritores', `<input name="descritores" value="${v('descritores')}"
              placeholder="chocolate, caramelo, frutas amarelas...">`)}
          </div>
          <datalist id="lista-gostos">${t.gostos.map((g) => `<option value="${esc(g)}">`).join('')}</datalist>
          <h4 class="titulo-bloco">Prova de xícara (SCA) — notas de 0 a 10</h4>
          <div class="linha-campos">${atributos}</div>
          <div class="linha-campos">
            ${UI.campo('Defeitos de xícara (pontos a descontar)', num('sensorial_defeitos', a.sensorial_defeitos || ''),
              'taça com defeito leve: 2 pontos; grave: 4 pontos, por xícara')}
          </div>
        </div>

        <h4 class="titulo-bloco">Resultado</h4>
        <div id="resultado-amostra"></div>
        <div class="linha-campos">
          ${UI.campo('Tipo corrigido à mão', `<input name="tipo" value="${a.tipo_manual ? v('tipo') : ''}" placeholder="vazio = o calculado">`,
            'use se a tabela do seu armazém der outro intermediário')}
          <label class="campo">Usar o tipo corrigido
            <span class="espaco" style="margin-top:6px"><input type="checkbox" name="tipo_manual" ${a.tipo_manual ? 'checked' : ''}>
            <span class="mini">o laudo sai com ele</span></span></label>
          ${UI.campo('Padrão', `<input name="padrao" value="${v('padrao')}" placeholder="vazio = o sugerido">`)}
        </div>
        <div class="linha-campos">
          ${UI.campo('Classificador', `<input name="classificador" value="${v('classificador')}">`)}
          ${UI.campo('Registro (CREA/MAPA)', `<input name="registro_classificador" value="${v('registro_classificador')}">`)}
          ${UI.campo('Observação', `<input name="observacao" value="${v('observacao')}">`)}
        </div>`,
      botoes: Amostras.botoes(a),
      aoSalvar: () => Amostras.salvar(a),
    });

    const corpo = document.getElementById('modal-corpo');
    corpo.querySelectorAll('#abas-amostra .aba').forEach((b) => {
      b.onclick = () => {
        corpo.querySelectorAll('#abas-amostra .aba').forEach((x) => x.classList.toggle('ativa', x === b));
        corpo.querySelectorAll('.parte-amostra').forEach((p) => {
          p.classList.toggle('oculto', p.dataset.parte !== b.dataset.parte);
        });
      };
    });
    // a bebida muda de lista quando a espécie muda (conilon tem a escala dele)
    corpo.querySelector('[name="especie"]').onchange = () => {
      const especie = corpo.querySelector('[name="especie"]').value;
      const bebida = corpo.querySelector('[name="bebida"]');
      const opcoes = especie === 'CONILON' ? t.bebidas_conilon : t.bebidas;
      bebida.innerHTML = `<option value="">—</option>${opcoes.map((o) => `<option>${esc(o)}</option>`).join('')}`;
      Amostras.recalcular();
    };
    corpo.addEventListener('input', () => Amostras.recalcularDepois());
    corpo.addEventListener('change', () => Amostras.recalcularDepois());
    Amostras._resultado = a.resultado || null;
    if (a.resultado) Amostras.mostrarResultado(a.resultado);
    Amostras.recalcular();
  },

  botoes(a) {
    const botoes = [{ rotulo: 'Fechar', acao: () => UI.tentarFecharModal() }];
    if (a.id) {
      botoes.push({ rotulo: 'Apagar', classe: 'btn-perigo', acao: () => Amostras.apagar(a) });
      botoes.push({ rotulo: 'Imprimir laudo', acao: () => Amostras.salvar(a, { laudo: true }) });
    }
    botoes.push({ rotulo: 'Salvar', classe: 'btn-primario', acao: () => Amostras.salvar(a) });
    return botoes;
  },

  /** Lê a tela e monta o corpo que o servidor espera. */
  ler() {
    const corpo = document.getElementById('modal-corpo');
    const d = UI.lerFormulario(corpo);
    const grupo = (prefixo) => {
      const saida = {};
      Object.keys(d).forEach((k) => {
        if (!k.startsWith(prefixo)) return;
        if (d[k] !== null && d[k] !== '') saida[k.slice(prefixo.length)] = d[k];
        delete d[k];
      });
      return saida;
    };
    const dados = {
      ...d,
      defeitos: grupo('def_'),
      peneiras: grupo('pen_'),
      sensorial: grupo('sen_'),
    };
    // grupo() apagou as chaves de d, mas o espalhamento acima foi feito antes
    Object.keys(dados).forEach((k) => {
      if (k.startsWith('def_') || k.startsWith('pen_') || k.startsWith('sen_')) delete dados[k];
    });
    ['sacas', 'sensorial_defeitos'].forEach((k) => { if (dados[k] === null) dados[k] = 0; });
    ['parceiro_id', 'contrato_id', 'altitude'].forEach((k) => {
      dados[k] = dados[k] ? Number(dados[k]) : null;
    });
    dados.empresa_id = Estado.empresaId;
    return dados;
  },

  recalcularDepois() {
    clearTimeout(Amostras._tempo);
    Amostras._tempo = setTimeout(() => Amostras.recalcular(), 300);
  },

  async recalcular() {
    if (!document.getElementById('resultado-amostra')) return;
    try {
      const r = await Api.post('/api/amostras/calcular', Amostras.ler());
      Amostras._resultado = r;
      Amostras.mostrarResultado(r);
    } catch (e) { /* digitação pela metade: o próximo toque calcula de novo */ }
  },

  mostrarResultado(r) {
    const alvo = document.getElementById('resultado-amostra');
    if (!alvo) return;
    const p = r.peneiras.grupos;
    const s = r.sensorial;
    alvo.innerHTML = `
      <div class="grade g4" style="margin-bottom:10px">
        ${Amostras.kpi('Tipo', r.tipo ? UI.escapar(r.tipo) : '—',
          r.tipo_manual ? `corrigido (calculado: ${r.tipo_calculado})`
            : `${UI.numero(r.defeitos.total_300g)} defeitos em 300 g`,
          r.fora_de_tipo ? 'destaque-vermelho' : 'destaque-azul')}
        ${Amostras.kpi('Peneira', r.peneiras.leitura || '—',
          r.peneiras.soma ? `17 acima ${UI.numero(p.acima_17)}% · moca ${UI.numero(p.moca_total)}%` : 'sem peneiras digitadas')}
        ${Amostras.kpi('Prova (SCA)', s.pontuacao != null ? UI.numero(s.pontuacao) : '—',
          s.categoria || (s.parcial != null ? `parcial: ${UI.numero(s.parcial)}` : 'sem notas'),
          s.pontuacao >= 80 ? 'destaque-verde' : '')}
        ${Amostras.kpi('Padrão', `<span style="font-size:14px">${UI.escapar(r.padrao || '—')}</span>`,
          r.padrao_sugerido && r.padrao !== r.padrao_sugerido ? `sugerido: ${r.padrao_sugerido}` : 'sugerido pelo sistema')}
      </div>
      <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start">
        <div style="flex:1;min-width:260px">${Amostras.tabelaDefeitos(r)}</div>
        ${Object.keys(s.notas).length ? `<div style="width:340px;max-width:100%">${Amostras.radar(s.atributos, { tamanho: 240 })}</div>` : ''}
      </div>
      ${(r.avisos || []).length ? `<div class="aviso-caixa"><ul class="lista-simples">${
        r.avisos.map((x) => `<li>${UI.escapar(x)}</li>`).join('')}</ul></div>` : ''}`;
  },

  tabelaDefeitos(r) {
    const linhas = r.defeitos.linhas.filter((x) => x.quantidade);
    if (!linhas.length) return '<div class="mini">Nenhum defeito digitado ainda.</div>';
    return `<table class="tabela-simples" style="width:100%">
      <thead><tr><th>Defeito</th><th class="num">Achados</th><th class="num">Defeitos</th></tr></thead>
      <tbody>${linhas.map((x) => `<tr><td>${UI.escapar(x.rotulo)}</td>
        <td class="num">${UI.numero(x.quantidade, 0)}</td><td class="num">${UI.numero(x.defeitos)}</td></tr>`).join('')}</tbody>
      <tfoot><tr><td><b>Total na amostra</b></td><td></td><td class="num"><b>${UI.numero(r.defeitos.soma)}</b></td></tr>
      ${r.defeitos.fator !== 1 ? `<tr><td><b>Em 300 g</b></td><td></td><td class="num"><b>${UI.numero(r.defeitos.total_300g)}</b></td></tr>` : ''}
      </tfoot></table>`;
  },

  async salvar(a, { laudo = false } = {}) {
    const dados = Amostras.ler();
    try {
      const retorno = a.id
        ? await Api.put(`/api/amostras/${a.id}`, dados)
        : await Api.post('/api/amostras', dados);
      UI.modalSalvo();
      UI.sucesso(`Amostra ${Amostras.numero(retorno.numero)} salva.`);
      Amostras.carregar().catch(() => {});
      if (laudo) return Amostras.laudo(retorno.id);
      if (!a.id) {
        // a amostra nova ganhou número: reabre já com os botões de laudo
        return Amostras.formulario(retorno);
      }
      UI.trocarBotoes(Amostras.botoes(retorno), document.getElementById('modal-corpo'));
      Object.assign(a, retorno);
    } catch (e) {
      UI.erro(e.message);
    }
    return null;
  },

  async apagar(a) {
    if (!await UI.confirmar(`Apagar a amostra ${Amostras.numero(a.numero)}? O laudo dela some junto.`, 'Apagar')) {
      return Amostras.formulario(a);
    }
    try {
      await Api.del(`/api/amostras/${a.id}`);
      UI.sucesso('Amostra apagada.');
      await Amostras.carregar();
    } catch (e) {
      UI.erro(e.message);
    }
    return null;
  },

  /* ================================================================ GRÁFICO DE ARANHA */
  /** SVG do gráfico de aranha da prova. Escala de 5 (centro) a 10 (borda):
      é onde as notas de um café de verdade caem, e as diferenças aparecem. */
  radar(atributos, { tamanho = 300, cor = '#15774a', imprimir = false } = {}) {
    const n = atributos.length;
    const cx = tamanho / 2;
    const cy = tamanho / 2;
    const raio = tamanho / 2 - 30;
    const minimo = 5;
    const maximo = 10;
    const ponto = (i, valor) => {
      const angulo = -Math.PI / 2 + (2 * Math.PI * i) / n;
      const fr = Math.max(0, Math.min(1, (valor - minimo) / (maximo - minimo)));
      return [cx + Math.cos(angulo) * raio * fr, cy + Math.sin(angulo) * raio * fr];
    };
    const linhaCor = imprimir ? '#999' : 'var(--borda,#d6dbe1)';
    const textoCor = imprimir ? '#222' : 'var(--cinza-700,#334155)';
    const aneis = [6, 7, 8, 9, 10].map((v) => {
      const pts = atributos.map((_, i) => ponto(i, v).map((x) => x.toFixed(1)).join(',')).join(' ');
      return `<polygon points="${pts}" fill="none" stroke="${linhaCor}" stroke-width="${v === 10 ? 1.2 : 0.7}"/>
        <text x="${cx + 3}" y="${(ponto(0, v)[1] + 3).toFixed(1)}" font-size="8" fill="${textoCor}" opacity=".7">${v}</text>`;
    }).join('');
    const eixos = atributos.map((x, i) => {
      const [ex, ey] = ponto(i, maximo);
      const angulo = -Math.PI / 2 + (2 * Math.PI * i) / n;
      const lx = cx + Math.cos(angulo) * (raio + 14);
      const ly = cy + Math.sin(angulo) * (raio + 14);
      const ancora = Math.abs(Math.cos(angulo)) < 0.2 ? 'middle' : (Math.cos(angulo) > 0 ? 'start' : 'end');
      return `<line x1="${cx}" y1="${cy}" x2="${ex.toFixed(1)}" y2="${ey.toFixed(1)}" stroke="${linhaCor}" stroke-width=".7"/>
        <text x="${lx.toFixed(1)}" y="${(ly + 3).toFixed(1)}" font-size="9.5" text-anchor="${ancora}" fill="${textoCor}">${
          UI.escapar(x.rotulo)}${x.nota != null ? ` ${String(x.nota).replace('.', ',')}` : ''}</text>`;
    }).join('');
    const pts = atributos.map((x, i) => ponto(i, x.nota != null ? x.nota : minimo));
    const area = pts.map((p) => p.map((v) => v.toFixed(1)).join(',')).join(' ');
    const bolas = pts.map(([x, y]) => `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.6" fill="${cor}"/>`).join('');
    // margem dos lados para os nomes dos atributos não serem cortados
    const folga = 62;
    return `<svg viewBox="${-folga} 0 ${tamanho + 2 * folga} ${tamanho}" width="100%"
        style="max-width:${tamanho + 2 * folga}px;display:block;margin:auto;overflow:visible"
        role="img" aria-label="Gráfico de aranha da prova de xícara">
      ${aneis}${eixos}
      <polygon points="${area}" fill="${cor}" fill-opacity=".22" stroke="${cor}" stroke-width="2"/>
      ${bolas}</svg>`;
  },

  /* ================================================================ LAUDO */
  async laudo(id) {
    let dados;
    try {
      dados = await Api.get(`/api/amostras/${id}/laudo`);
    } catch (e) {
      return UI.erro(e.message);
    }
    const janela = window.open('', '_blank');
    if (!janela) return UI.erro('O navegador bloqueou a janela. Libere os pop-ups deste site.');
    janela.document.write(Amostras.paginaLaudo(dados));
    janela.document.close();
    // espera o logotipo carregar antes de imprimir
    setTimeout(() => janela.print(), 500);
    return null;
  },

  paginaLaudo({ amostra: a, empresa: e, preparos, especies }) {
    const esc = UI.escapar;
    const r = a.resultado;
    const s = r.sensorial;
    const n = (v, c = 2) => (v == null || v === '' ? '—' : UI.numero(v, c));
    const linha = (rotulo, valor) => `<tr><th>${esc(rotulo)}</th><td>${valor || '—'}</td></tr>`;
    const defeitos = r.defeitos.linhas.filter((x) => x.quantidade);
    const peneiras = r.peneiras.linhas.filter((x) => x.gramas);
    const g = r.peneiras.grupos;
    const temProva = Object.keys(s.notas).length > 0;

    return `<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
      <title>Laudo ${Amostras.numero(a.numero)} — ${esc(a.produtor_nome || '')}</title>
      <style>
        @page { size: A4; margin: 10mm 12mm; }
        * { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        body { font: 10px/1.3 Arial, Helvetica, sans-serif; color:#111; margin:0; }
        .topo { display:flex; gap:14px; align-items:center; border-bottom:2px solid #15774a; padding-bottom:8px; }
        .topo img { max-width:110px; max-height:60px; object-fit:contain; }
        .topo h1 { font-size:15px; margin:0; }
        .topo .mini { font-size:10px; color:#444; }
        .titulo { display:flex; justify-content:space-between; align-items:flex-end; margin:8px 0 2px; }
        .titulo h2 { font-size:16px; margin:0; letter-spacing:.3px; }
        .titulo .numero { font-size:13px; font-weight:700; }
        h3 { font-size:10px; text-transform:uppercase; letter-spacing:.6px; color:#0f5c39;
             border-bottom:1px solid #c9d8cf; padding-bottom:2px; margin:8px 0 4px; }
        .duas { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
        table { width:100%; border-collapse:collapse; }
        table.dados th { text-align:left; font-weight:600; width:42%; padding:1px 5px; vertical-align:top; color:#333; }
        table.dados td { padding:1px 5px; border-bottom:1px dotted #ccc; }
        table.grade th, table.grade td { border:1px solid #bbb; padding:1px 5px; font-size:9.5px; }
        table.grade th { background:#eef4f0; font-size:10px; text-align:left; }
        .num { text-align:right; }
        .resultado { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin:4px 0 2px; }
        .caixa { border:1px solid #15774a; border-radius:6px; padding:5px 8px; min-width:0; }
        .caixa .rot { font-size:9px; text-transform:uppercase; color:#0f5c39; letter-spacing:.5px; }
        .caixa .val { font-size:16px; font-weight:700; }
        .caixa .sub { font-size:9.5px; color:#444; }
        .padrao { border:2px solid #15774a; background:#f2fbf6; border-radius:6px; padding:5px 10px;
                  font-size:12.5px; font-weight:700; margin-top:6px; }
        .barra { height:8px; background:#15774a; border-radius:2px; }
        .assinatura { margin-top:18px; display:flex; justify-content:space-between; gap:30px; }
        .assinatura div { flex:1; border-top:1px solid #333; padding-top:3px; text-align:center; font-size:10px; }
        .rodape { margin-top:14px; font-size:8.5px; color:#666; border-top:1px solid #ddd; padding-top:5px; }
        .radar { text-align:center; }
        @media print { .nao-imprime { display:none; } }
      </style></head><body>
      <div class="topo">
        ${e.logo ? `<img src="${esc(e.logo)}" alt="">` : ''}
        <div><h1>${esc(e.nome_fantasia || e.razao_social)}</h1>
          <div class="mini">${esc(e.razao_social)}${e.cnpj ? ` · CNPJ ${esc(e.cnpj)}` : ''}</div>
          <div class="mini">${esc([e.endereco, e.cidade && `${e.cidade}/${e.uf || ''}`].filter(Boolean).join(' · '))}
            ${e.telefone ? ` · ${esc(e.telefone)}` : ''}${e.email ? ` · ${esc(e.email)}` : ''}</div></div>
      </div>

      <div class="titulo">
        <h2>LAUDO DE CLASSIFICAÇÃO DE CAFÉ</h2>
        <div class="numero">Amostra nº ${Amostras.numero(a.numero)}</div>
      </div>

      <div class="duas">
        <div><h3>Identificação</h3><table class="dados">
          ${linha('Produtor', esc(a.produtor_nome || a.parceiro_nome || ''))}
          ${linha('Fazenda', esc(a.fazenda || ''))}
          ${linha('Município/UF', esc([a.municipio, a.uf].filter(Boolean).join('/')))}
          ${linha('Lote', esc(a.lote || ''))}
          ${linha('Sacas', a.sacas ? UI.numero(a.sacas, 0) : '')}
          ${linha('Armazém', esc(a.armazem || ''))}
          ${a.contrato_numero ? linha('Contrato', esc(a.contrato_numero)) : ''}
        </table></div>
        <div><h3>O café</h3><table class="dados">
          ${linha('Espécie', esc(especies[a.especie] || a.especie || ''))}
          ${linha('Variedade', esc(a.variedade || ''))}
          ${linha('Preparo', esc(preparos[a.preparo] || ''))}
          ${linha('Safra', esc(a.safra || ''))}
          ${linha('Altitude', a.altitude ? `${a.altitude} m` : '')}
          ${linha('Recebida em', UI.data(a.data_recebimento))}
          ${linha('Classificada em', a.data_classificacao ? UI.data(a.data_classificacao) : '')}
        </table></div>
      </div>

      <h3>Resultado</h3>
      <div class="resultado">
        <div class="caixa"><div class="rot">Tipo (COB)</div><div class="val">${esc(r.tipo || '—')}</div>
          <div class="sub">${n(r.defeitos.total_300g)} defeitos em 300 g</div></div>
        <div class="caixa"><div class="rot">Peneira</div><div class="val">${esc(r.peneiras.leitura || '—')}</div>
          <div class="sub">${r.peneiras.soma ? `17 acima ${n(g.acima_17)}% · moca ${n(g.moca_total)}%` : ''}</div></div>
        <div class="caixa"><div class="rot">Bebida</div><div class="val" style="font-size:13px">${esc(a.bebida || '—')}</div>
          <div class="sub">${esc(a.gostos_estranhos || '')}</div></div>
        <div class="caixa"><div class="rot">Prova (SCA)</div><div class="val">${s.pontuacao != null ? n(s.pontuacao) : '—'}</div>
          <div class="sub">${esc(s.categoria || '')}</div></div>
      </div>
      <div class="padrao">Padrão: ${esc(r.padrao || '—')}</div>

      <div class="duas">
        <div>
          <h3>Classificação física</h3>
          <table class="dados">
            ${linha('Umidade', a.umidade != null ? `${n(a.umidade, 1)}%` : '')}
            ${linha('Catação', a.catacao != null ? `${n(a.catacao, 1)}%` : '')}
            ${linha('Impurezas', a.impurezas != null ? `${n(a.impurezas, 1)}%` : '')}
            ${linha('Cor', esc(a.cor || ''))}
            ${linha('Aspecto', esc(a.aspecto || ''))}
            ${linha('Torração', esc(a.torracao || ''))}
            ${linha('Peso da amostra', `${n(a.peso_amostra, 0)} g`)}
          </table>
          ${defeitos.length ? `<table class="grade" style="margin-top:6px">
            <thead><tr><th>Defeito</th><th class="num">Achados</th><th class="num">Defeitos</th></tr></thead>
            <tbody>${defeitos.map((x) => `<tr><td>${esc(x.rotulo)}</td><td class="num">${n(x.quantidade, 0)}</td>
              <td class="num">${n(x.defeitos)}</td></tr>`).join('')}
            <tr><td><b>Total${r.defeitos.fator !== 1 ? ' (em 300 g)' : ''}</b></td><td></td>
              <td class="num"><b>${n(r.defeitos.total_300g)}</b></td></tr></tbody></table>` : ''}
        </div>
        <div>
          <h3>Peneiras (${n(r.peneiras.soma || a.peso_peneiras, 0)} g)</h3>
          ${peneiras.length ? `<table class="grade">
            <thead><tr><th>Peneira</th><th class="num">g</th><th class="num">%</th><th style="width:38%"></th></tr></thead>
            <tbody>${peneiras.map((x) => `<tr><td>${esc(x.formato === 'Fundo' ? 'Fundo' : `${x.formato} ${x.rotulo}`)}</td>
              <td class="num">${n(x.gramas, 1)}</td><td class="num">${n(x.percentual, 1)}</td>
              <td><div class="barra" style="width:${Math.min(100, x.percentual).toFixed(1)}%"></div></td></tr>`).join('')}
            </tbody></table>
            <table class="dados" style="margin-top:4px">
              ${linha('Chato graúdo (17 e acima)', `${n(g.chato_graudo, 1)}%`)}
              ${linha('Chato médio (15 e 16)', `${n(g.chato_medio, 1)}%`)}
              ${linha('Chato miúdo (14 e abaixo)', `${n(g.chato_miudo, 1)}%`)}
              ${linha('Moca', `${n(g.moca_total, 1)}%`)}
              ${linha('Fundo', `${n(g.fundo, 1)}%`)}
            </table>` : '<div>Peneiras não informadas.</div>'}
        </div>
      </div>

      ${temProva ? `
        <h3>Análise sensorial — prova de xícara (protocolo SCA)</h3>
        <div class="duas">
          <div><table class="grade">
            <thead><tr><th>Atributo</th><th class="num">Nota</th><th>Atributo</th><th class="num">Nota</th></tr></thead>
            <tbody>${[0, 1, 2, 3, 4].map((i) => {
              const x = s.atributos[i];
              const y = s.atributos[i + 5];
              return `<tr><td>${esc(x.rotulo)}</td><td class="num">${n(x.nota)}</td>
                <td>${esc(y.rotulo)}</td><td class="num">${n(y.nota)}</td></tr>`;
            }).join('')}
              ${Number(a.sensorial_defeitos) ? `<tr><td colspan="3">Defeitos de xícara</td><td class="num">− ${n(a.sensorial_defeitos)}</td></tr>` : ''}
              <tr><td colspan="3"><b>Pontuação final</b>${s.categoria ? ` — ${esc(s.categoria)}` : ''}</td>
                <td class="num"><b>${s.pontuacao != null ? n(s.pontuacao) : 'incompleta'}</b></td></tr>
            </tbody></table>
            ${a.descritores ? `<p><b>Descritores:</b> ${esc(a.descritores)}</p>` : ''}
          </div>
          <div class="radar">${Amostras.radar(s.atributos, { tamanho: 215, imprimir: true })}</div>
        </div>` : (a.descritores ? `<p><b>Descritores:</b> ${esc(a.descritores)}</p>` : '')}

      ${a.observacao ? `<p style="margin:6px 0 0"><b>Observação:</b> ${esc(a.observacao)}</p>` : ''}

      <div class="assinatura">
        <div>${esc(a.classificador || 'Classificador')}${a.registro_classificador ? ` — ${esc(a.registro_classificador)}` : ''}</div>
        <div>${esc(e.cidade || '')}${e.cidade ? ', ' : ''}${UI.data(a.data_classificacao || UI.hoje())}</div>
      </div>
      <div class="rodape">Classificação física pela Classificação Oficial Brasileira (Instrução Normativa
        MAPA nº 8/2003); o tipo intermediário é obtido por interpolação entre os limites da tabela de tipos.
        Prova de xícara no protocolo da SCA. O resultado vale para a amostra recebida. — AgroDock</div>
      <div class="nao-imprime" style="margin-top:12px"><button onclick="window.print()">Imprimir</button></div>
      </body></html>`;
  },
};
