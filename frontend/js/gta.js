/* GTA — Guia de Trânsito Animal.

   Aqui o sistema **não emite** a guia: a GTA não tem webservice. Quem emite é o
   produtor ou o médico-veterinário, dentro do sistema fechado do estado (em
   Minas o SIAPEC, do IMA). Então esta tela faz as duas coisas que faltavam:

     1. guarda e vigia todas as guias — quem mandou, para onde, quantos animais,
        até quando vale (e avisa quando está vencendo);
     2. imprime a **ficha de preparo**: a folha com tudo já conferido, na ordem
        das telas do portal, para quem for digitar não errar nem procurar dado.

   A conferência é a parte que economiza tempo de verdade: ela aponta o que o
   portal vai cobrar **antes** de a pessoa abrir o portal. */
const GTA = {
  _tabelas: null,
  _guias: [],
  _resumo: {},
  _categorias: [],
  _filtros: { de: '', ate: '', produtor_id: '', especie: '', situacao: '', busca: '' },

  CORES: {
    PREPARO: 'tag-aberto',
    EMITIDA: 'tag-pago',
    UTILIZADA: 'tag-quitado',
    CANCELADA: 'tag-cancelado',
    VENCIDA: 'tag-vencido',
  },

  ROTULOS: {
    PREPARO: 'Em preparo',
    EMITIDA: 'Emitida',
    UTILIZADA: 'Utilizada',
    CANCELADA: 'Cancelada',
    VENCIDA: 'Vencida',
  },

  /* ------------------------------------------------------------------ tela */
  async tela() {
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';
    try {
      if (!GTA._tabelas) GTA._tabelas = await Api.get('/api/gta/tabelas');
      await GTA.carregar();
    } catch (e) {
      alvo.innerHTML = `<div class="cartao"><div class="vazio">${UI.escapar(e.message)}</div></div>`;
    }
  },

  async carregar() {
    const retorno = await Api.get('/api/gta', {
      empresa_id: Estado.empresaId, ...GTA._filtros,
    });
    GTA._guias = retorno.guias || [];
    GTA._resumo = retorno.resumo || {};
    GTA.desenhar();
  },

  desenhar() {
    const r = GTA._resumo;
    const especies = Object.keys(GTA._tabelas.especies || {});
    document.getElementById('pagina').innerHTML = `
      <div class="cartao" style="margin-bottom:12px;border-left:4px solid var(--azul)">
        <div class="cartao-corpo">
          <b>A GTA é emitida no portal do estado, não aqui.</b>
          <div class="mini">Não existe webservice de GTA: quem emite é o produtor ou o
            médico-veterinário, com o login dele, no sistema do órgão de defesa
            (em Minas, o SIAPEC/IMA). O que o sistema faz é guardar as guias, avisar
            de validade e imprimir a <b>ficha de preparo</b> — a folha já conferida,
            na ordem das telas do portal.</div>
        </div>
      </div>

      <div class="grade g4" style="margin-bottom:12px">
        ${GTA.cartao('Guias', r.total, `${r.animais || 0} animais`, 'azul')}
        ${GTA.cartao('Válidas', r.validas, 'emitidas e dentro do prazo', 'verde')}
        ${GTA.cartao('Vencendo', r.vencendo, `faltam até ${GTA._tabelas.dias_de_aviso} dias`,
          r.vencendo ? 'ambar' : '')}
        ${GTA.cartao('Vencidas', r.vencidas, 'passaram da validade', r.vencidas ? 'vermelho' : '')}
        ${GTA.cartao('Em preparo', r.preparo, 'ainda não foram ao portal')}
        ${GTA.cartao('Com pendência', r.com_pendencia, 'falta dado para digitar',
          r.com_pendencia ? 'ambar' : '')}
      </div>

      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Guias de Trânsito Animal</h3>
            <div class="mini">as guias dos produtores atendidos</div></div>
          <div class="espaco">
            <button class="btn" id="btn-exportar-gta">Exportar</button>
            <button class="btn btn-primario" id="btn-nova-gta">Nova guia</button>
          </div>
        </div>
        <div class="cartao-corpo">
          <div class="linha-campos" data-nao-suja>
            ${UI.campo('De', `<input type="date" name="de" value="${GTA._filtros.de}">`)}
            ${UI.campo('Até', `<input type="date" name="ate" value="${GTA._filtros.ate}">`)}
            ${UI.campo('Produtor', UI.select('produtor_id', UI.opcoesParceiros(),
              GTA._filtros.produtor_id, { vazio: 'Todos' }))}
            ${UI.campo('Espécie', UI.select('especie',
              especies.map((e) => ({ valor: e, rotulo: GTA.titulo(e) })),
              GTA._filtros.especie, { vazio: 'Todas' }))}
            ${UI.campo('Situação', UI.select('situacao',
              (GTA._tabelas.situacoes || []).map((s) => ({ valor: s, rotulo: GTA.ROTULOS[s] || s })),
              GTA._filtros.situacao, { vazio: 'Todas' }))}
            ${UI.campo('Procurar', `<input name="busca" value="${UI.escapar(GTA._filtros.busca)}"
              placeholder="número, produtor ou fazenda">`)}
          </div>
          <div id="lista-gta" style="margin-top:12px">${GTA.tabela()}</div>
        </div>
      </div>`;
    GTA.ligar();
  },

  cartao(titulo, valor, dica, cor = '') {
    return `<div class="kpi ${cor ? `destaque-${cor}` : ''}">
      <div class="kpi-rotulo">${UI.escapar(titulo)}</div>
      <div class="kpi-valor" ${cor ? `style="color:var(--${cor})"` : ''}>${Number(valor || 0)}</div>
      <div class="kpi-nota">${UI.escapar(dica)}</div></div>`;
  },

  titulo(texto) {
    const t = String(texto || '').toLowerCase();
    return t ? t[0].toUpperCase() + t.slice(1) : '';
  },

  tabela() {
    return UI.tabela({
      vazio: 'Nenhuma guia neste filtro. Comece criando uma guia em preparo.',
      colunas: [
        { titulo: 'Guia', valor: (g) => `<b>${UI.escapar(g.numero || '—')}</b>
            <div class="mini">${UI.escapar(GTA.titulo(g.especie || ''))} ·
            ${Number(g.quantidade || 0)} animais</div>` },
        { titulo: 'Emissão', valor: (g) => UI.data(g.data_emissao) || '—' },
        { titulo: 'Validade', valor: (g) => GTA.celulaValidade(g) },
        { titulo: 'Origem', valor: (g) => `${UI.escapar(g.origem_nome || '—')}
            <div class="mini">${UI.escapar(g.origem_propriedade || '')}
            ${g.origem_municipio ? `— ${UI.escapar(g.origem_municipio)}/${UI.escapar(g.origem_uf || '')}` : ''}</div>` },
        { titulo: 'Destino', valor: (g) => `${UI.escapar(g.destino_nome || '—')}
            <div class="mini">${UI.escapar(g.destino_propriedade || '')}
            ${g.destino_municipio ? `— ${UI.escapar(g.destino_municipio)}/${UI.escapar(g.destino_uf || '')}` : ''}</div>` },
        { titulo: 'Situação', valor: (g) => GTA.selo(g) },
        { titulo: '', classe: 'direita', valor: (g, i) => `
            <button class="btn btn-mini" data-preparo="${i}">Ficha de preparo</button>
            <button class="btn btn-mini" data-abrir="${i}">Abrir</button>` },
      ],
      linhas: GTA._guias,
    });
  },

  celulaValidade(g) {
    if (!g.data_validade) return '<span class="mini">sem validade</span>';
    const faltam = g.dias_para_vencer;
    const cor = faltam === null ? ''
      : faltam < 0 ? 'var(--vermelho)'
      : faltam <= (GTA._tabelas.dias_de_aviso || 3) ? 'var(--ambar)' : '';
    return `<span style="${cor ? `color:${cor};font-weight:600` : ''}">${UI.data(g.data_validade)}</span>
      ${g.aviso ? `<div class="mini" style="color:${cor}">${UI.escapar(g.aviso)}</div>` : ''}`;
  },

  selo(g) {
    const situacao = g.situacao_mostrada || g.situacao;
    const pendencia = g.pronta ? '' :
      `<div class="mini" style="color:var(--ambar)">${g.faltas.length}
       ponto${g.faltas.length > 1 ? 's' : ''} a resolver</div>`;
    return `<span class="tag ${GTA.CORES[situacao] || ''}">${GTA.ROTULOS[situacao] || situacao}</span>${pendencia}`;
  },

  ligar() {
    const pagina = document.getElementById('pagina');
    pagina.querySelectorAll('[name]').forEach((campo) => {
      campo.onchange = () => {
        GTA._filtros[campo.name] = campo.value;
        GTA.carregar();
      };
    });
    const busca = pagina.querySelector('[name="busca"]');
    if (busca) {
      let tempo = null;
      busca.oninput = () => {
        clearTimeout(tempo);
        tempo = setTimeout(() => {
          GTA._filtros.busca = busca.value;
          GTA.carregar();
        }, 400);
      };
    }
    pagina.querySelector('#btn-nova-gta').onclick = () => GTA.formulario(null);
    pagina.querySelector('#btn-exportar-gta').onclick = () =>
      UI.exportarTabela('guias-transito-animal', '#lista-gta table');
    pagina.querySelectorAll('[data-abrir]').forEach((b) => {
      b.onclick = () => GTA.formulario(GTA._guias[Number(b.dataset.abrir)]);
    });
    pagina.querySelectorAll('[data-preparo]').forEach((b) => {
      b.onclick = () => GTA.preparo(GTA._guias[Number(b.dataset.preparo)].id);
    });
  },

  /* ------------------------------------------------------------ formulário */
  formulario(guia) {
    const g = guia || {};
    GTA._categorias = (g.categorias || []).map((c) => ({ ...c }));
    const especies = Object.keys(GTA._tabelas.especies || {});
    const ufs = ['', 'AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS',
      'MT', 'PA', 'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO'];
    const opcoesUf = ufs.filter(Boolean).map((u) => ({ valor: u, rotulo: u }));

    const corpo = UI.abrirModal({
      titulo: g.id ? `Guia ${g.numero || '(em preparo)'}` : 'Nova guia de trânsito animal',
      largo: true,
      corpo: `
        <div id="faltas-gta"></div>

        <h4 class="titulo-bloco">Os animais</h4>
        <div class="linha-campos">
          ${UI.campo('Espécie', UI.select('especie',
            especies.map((e) => ({ valor: e, rotulo: GTA.titulo(e) })), g.especie || 'BOVINO',
            { vazio: false }))}
          ${UI.campo('Finalidade', UI.select('finalidade',
            (GTA._tabelas.finalidades || []).map((f) => ({ valor: f, rotulo: GTA.titulo(f) })),
            g.finalidade || '', { vazio: 'Escolha' }), 'o portal pergunta logo na primeira tela')}
          ${UI.campo('Situação', UI.select('situacao',
            (GTA._tabelas.situacoes || []).map((s) => ({ valor: s, rotulo: GTA.ROTULOS[s] || s })),
            g.situacao || 'PREPARO', { vazio: false }))}
        </div>
        <div id="categorias-gta"></div>

        <h4 class="titulo-bloco">Origem — de onde os animais saem</h4>
        ${GTA.blocoLado('origem', g, opcoesUf)}

        <h4 class="titulo-bloco">Destino — para onde vão</h4>
        ${GTA.blocoLado('destino', g, opcoesUf)}

        <h4 class="titulo-bloco">Transporte e responsável</h4>
        <div class="linha-campos">
          ${UI.campo('Meio', UI.select('meio_transporte',
            (GTA._tabelas.meios_transporte || []).map((m) => ({ valor: m, rotulo: GTA.titulo(m) })),
            g.meio_transporte || 'RODOVIARIO', { vazio: false }))}
          ${UI.campo('Transportador', `<input name="transportador" value="${UI.escapar(g.transportador || '')}">`)}
          ${UI.campo('Placa', `<input name="placa" value="${UI.escapar(g.placa || '')}" maxlength="10">`)}
          ${UI.campo('Médico-veterinário', `<input name="veterinario" value="${UI.escapar(g.veterinario || '')}">`)}
          ${UI.campo('CRMV', `<input name="crmv" value="${UI.escapar(g.crmv || '')}">`)}
        </div>

        <h4 class="titulo-bloco">Depois de emitir no portal</h4>
        <div class="linha-campos">
          ${UI.campo('Número da GTA', `<input name="numero" value="${UI.escapar(g.numero || '')}">`)}
          ${UI.campo('Série', `<input name="serie" value="${UI.escapar(g.serie || '')}">`)}
          ${UI.campo('UF emissora', UI.select('uf_emissora', opcoesUf, g.uf_emissora || '',
            { vazio: 'Escolha' }), 'de qual portal a guia saiu')}
          ${UI.campo('Emissão', `<input type="date" name="data_emissao" value="${g.data_emissao || ''}">`)}
          ${UI.campo('Validade', `<input type="date" name="data_validade" value="${g.data_validade || ''}">`,
            'é esta data que o sistema vigia')}
        </div>
        <div class="linha-campos">
          ${UI.campo('PDF da guia', '<input type="file" name="arquivo_pdf" accept="application/pdf">',
            g.tem_anexo ? 'já existe um arquivo guardado — anexar outro substitui'
                        : 'opcional: guarde aqui a guia que saiu do portal')}
          ${UI.campo('Observação', `<input name="observacao" value="${UI.escapar(g.observacao || '')}">`)}
        </div>`,
      botoes: GTA.botoes(g),
      aoSalvar: () => GTA.salvar(g),
    });

    GTA.desenharCategorias();
    GTA.mostrarFaltas(g.faltas || []);
    corpo.querySelector('[name="especie"]').onchange = () => {
      GTA._categorias = [];
      GTA.desenharCategorias();
    };
    const anexo = corpo.querySelector('[name="arquivo_pdf"]');
    if (anexo && g.tem_anexo) {
      anexo.insertAdjacentHTML('afterend',
        `<button class="btn btn-mini" id="btn-baixar-gta" style="margin-top:6px">Baixar o PDF guardado</button>`);
      corpo.querySelector('#btn-baixar-gta').onclick = (e) => {
        e.preventDefault();
        GTA.baixarAnexo(g.id);
      };
    }
  },

  blocoLado(lado, g, opcoesUf) {
    const rotulo = lado === 'origem' ? 'produtor de origem' : 'produtor de destino';
    return `<div class="linha-campos">
      ${UI.campo('No cadastro', UI.select(lado === 'origem' ? 'produtor_id' : 'destino_id',
        UI.opcoesParceiros(), g[lado === 'origem' ? 'produtor_id' : 'destino_id'] || '',
        { vazio: 'Não está no cadastro' }),
        `escolha o ${rotulo} e os dados vêm sozinhos`)}
      ${UI.campo('Nome', `<input name="${lado}_nome" value="${UI.escapar(g[`${lado}_nome`] || '')}">`)}
      ${UI.campo('CPF/CNPJ', `<input name="${lado}_documento" value="${UI.escapar(g[`${lado}_documento`] || '')}">`)}
      ${UI.campo('Propriedade', `<input name="${lado}_propriedade" value="${UI.escapar(g[`${lado}_propriedade`] || '')}">`,
        'o portal procura a fazenda, não a pessoa')}
      ${UI.campo('Inscrição estadual', `<input name="${lado}_inscricao" value="${UI.escapar(g[`${lado}_inscricao`] || '')}">`)}
      ${UI.campo('Município', `<input name="${lado}_municipio" value="${UI.escapar(g[`${lado}_municipio`] || '')}">`)}
      ${UI.campo('UF', UI.select(`${lado}_uf`, opcoesUf, g[`${lado}_uf`] || '', { vazio: '—' }))}
    </div>`;
  },

  /* As categorias: o portal não aceita um número só de animais — quer separado
     por sexo e faixa de idade, e a soma tem de bater. */
  desenharCategorias() {
    const corpo = document.getElementById('modal-corpo');
    const area = corpo.querySelector('#categorias-gta');
    const especie = corpo.querySelector('[name="especie"]').value;
    const faixas = (GTA._tabelas.especies || {})[especie] || [];
    const total = GTA._categorias.reduce((s, c) => s + Number(c.quantidade || 0), 0);

    area.innerHTML = `
      <div class="mini" style="margin:6px 0">Quantos animais, por sexo e idade —
        é assim que o portal pede. <b>Total: ${total}</b></div>
      <div class="tabela-wrap"><table><thead><tr>
        <th>Sexo</th><th>Faixa de idade</th><th class="direita">Quantidade</th>
        <th>Observação</th><th></th></tr></thead><tbody>
        ${GTA._categorias.map((c, i) => `<tr>
          <td>${UI.select(`cat_sexo_${i}`, [{ valor: 'M', rotulo: 'Macho' },
            { valor: 'F', rotulo: 'Fêmea' }], c.sexo || 'M', { vazio: false })}</td>
          <td>${UI.select(`cat_faixa_${i}`, faixas.map((f) => ({ valor: f, rotulo: f })),
            c.faixa || faixas[0] || '', { vazio: false })}</td>
          <td class="direita"><input type="number" min="0" step="1" style="max-width:110px"
            name="cat_qtd_${i}" value="${Number(c.quantidade || 0)}"></td>
          <td><input name="cat_obs_${i}" value="${UI.escapar(c.observacao || '')}"></td>
          <td class="direita"><button class="btn btn-mini btn-perigo"
            data-tirar-cat="${i}">Tirar</button></td>
        </tr>`).join('')}
      </tbody></table></div>
      <button class="btn btn-mini" id="btn-add-cat" style="margin-top:6px">Acrescentar categoria</button>`;

    area.querySelector('#btn-add-cat').onclick = (e) => {
      e.preventDefault();
      GTA.lerCategorias();
      GTA._categorias.push({ sexo: 'M', faixa: faixas[0] || '', quantidade: 0 });
      GTA.desenharCategorias();
    };
    area.querySelectorAll('[data-tirar-cat]').forEach((b) => {
      b.onclick = (e) => {
        e.preventDefault();
        GTA.lerCategorias();
        GTA._categorias.splice(Number(b.dataset.tirarCat), 1);
        GTA.desenharCategorias();
      };
    });
    area.querySelectorAll('input,select').forEach((campo) => {
      campo.onchange = () => {
        GTA.lerCategorias();
        GTA.desenharCategorias();
      };
    });
  },

  lerCategorias() {
    const corpo = document.getElementById('modal-corpo');
    GTA._categorias = GTA._categorias.map((c, i) => ({
      sexo: corpo.querySelector(`[name="cat_sexo_${i}"]`)?.value || c.sexo,
      faixa: corpo.querySelector(`[name="cat_faixa_${i}"]`)?.value || c.faixa,
      quantidade: Number(corpo.querySelector(`[name="cat_qtd_${i}"]`)?.value || 0),
      observacao: corpo.querySelector(`[name="cat_obs_${i}"]`)?.value || '',
    }));
  },

  mostrarFaltas(faltas) {
    const area = document.getElementById('faltas-gta');
    if (!area) return;
    if (!faltas.length) {
      area.innerHTML = `<div class="gta-conferencia ok">
        <b>Está tudo conferido.</b> Dá para imprimir a ficha e digitar no portal.</div>`;
      return;
    }
    area.innerHTML = `<div class="gta-conferencia">
      <b>O portal vai cobrar isto:</b>
      <ul>${faltas.map((f) => `<li>${UI.escapar(f)}</li>`).join('')}</ul></div>`;
  },

  botoes(g) {
    const botoes = [{ rotulo: 'Fechar', acao: () => UI.fecharModal() }];
    if (g.id) {
      botoes.push({ rotulo: 'Ficha de preparo', acao: () => GTA.preparo(g.id) });
      botoes.push({ rotulo: 'Apagar', classe: 'btn-perigo', acao: () => GTA.apagar(g) });
    }
    botoes.push({ rotulo: 'Salvar', classe: 'btn-primario', acao: () => GTA.salvar(g) });
    return botoes;
  },

  async lerArquivo(campo) {
    const arquivo = campo?.files?.[0];
    if (!arquivo) return null;
    if (arquivo.size > 4 * 1024 * 1024) {
      throw new Error('O PDF da guia passa de 4 MB. Gere um arquivo menor no portal.');
    }
    const base64 = await new Promise((ok, falhou) => {
      const leitor = new FileReader();
      leitor.onload = () => ok(String(leitor.result).split(',')[1] || '');
      leitor.onerror = () => falhou(new Error('Não consegui ler o arquivo escolhido.'));
      leitor.readAsDataURL(arquivo);
    });
    return { arquivo: base64, arquivo_nome: arquivo.name };
  },

  async salvar(g) {
    const corpo = document.getElementById('modal-corpo');
    GTA.lerCategorias();
    const dados = UI.lerFormulario(corpo);
    // os campos das categorias já foram lidos acima — não vão no corpo da guia
    Object.keys(dados).forEach((k) => { if (k.startsWith('cat_')) delete dados[k]; });
    delete dados.arquivo_pdf;

    const guia = {
      ...dados,
      empresa_id: Estado.empresaId,
      categorias: GTA._categorias.filter((c) => Number(c.quantidade || 0) > 0),
    };
    try {
      const anexo = await GTA.lerArquivo(corpo.querySelector('[name="arquivo_pdf"]'));
      if (anexo) Object.assign(guia, anexo);
      const retorno = g.id
        ? await Api.put(`/api/gta/${g.id}`, guia)
        : await Api.post('/api/gta', guia);
      UI.modalSalvo();
      UI.sucesso('Guia salva.');
      await GTA.carregar();
      GTA.mostrarFaltas(retorno.guia.faltas || []);
      if (!g.id) UI.fecharModal();
    } catch (e) {
      UI.erro(e.message);
    }
  },

  async apagar(g) {
    if (!await UI.confirmar(
      `Apagar a guia ${g.numero || 'em preparo'}? Isso não cancela nada no portal.`,
      'Apagar')) return;
    try {
      await Api.del(`/api/gta/${g.id}`);
      UI.modalSalvo();
      UI.fecharModal();
      UI.sucesso('Guia apagada.');
      await GTA.carregar();
    } catch (e) {
      UI.erro(e.message);
    }
  },

  async baixarAnexo(id) {
    const resposta = await fetch(`/api/gta/${id}/anexo`, {
      headers: { Authorization: `Bearer ${Estado.token}` },
    });
    if (!resposta.ok) return UI.erro('Não consegui baixar o arquivo desta guia.');
    const blob = await resposta.blob();
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `GTA-${id}.pdf`;
    link.click();
    URL.revokeObjectURL(link.href);
  },

  /* -------------------------------------------------------- ficha de preparo */
  async preparo(id) {
    try {
      const retorno = await Api.get(`/api/gta/${id}/preparo`);
      GTA.imprimirPreparo(retorno.preparo, retorno.guia);
    } catch (e) {
      UI.erro(e.message);
    }
  },

  /** A folha para levar ao portal. Página própria, sem depender do CSS do app. */
  imprimirPreparo(preparo, guia) {
    const esc = UI.escapar;
    const portal = preparo.portal || {};
    const blocos = (preparo.blocos || []).map((b) => `
      <section>
        <h2>${esc(b.titulo)}</h2>
        <table class="dados">
          ${b.linhas.map(([rotulo, valor]) => `<tr>
            <th>${esc(rotulo)}</th>
            <td>${valor ? esc(valor) : '<span class="falta">— em branco —</span>'}</td></tr>`).join('')}
        </table>
        ${b.categorias ? `<table class="animais">
          <thead><tr><th>Sexo</th><th>Faixa de idade</th><th class="dir">Quantidade</th>
            <th>Observação</th></tr></thead>
          <tbody>${b.categorias.map((c) => `<tr><td>${esc(c.sexo)}</td><td>${esc(c.faixa)}</td>
            <td class="dir">${c.quantidade}</td><td>${esc(c.observacao)}</td></tr>`).join('')}
          </tbody></table>` : ''}
      </section>`).join('');

    const faltas = (preparo.faltas || []).length ? `
      <div class="alerta">
        <b>Confira antes de digitar — o portal vai cobrar isto:</b>
        <ul>${preparo.faltas.map((f) => `<li>${esc(f)}</li>`).join('')}</ul>
      </div>` : `
      <div class="ok"><b>Tudo conferido.</b> Os dados abaixo estão completos.</div>`;

    const pagina = `<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
      <title>Ficha de preparo da GTA</title>
      <style>
        @page { size: A4; margin: 14mm; }
        body { font: 12px/1.45 Arial, Helvetica, sans-serif; color:#111; margin:0; }
        h1 { font-size:17px; margin:0 0 2px; }
        h2 { font-size:12px; text-transform:uppercase; letter-spacing:.5px;
             background:#eee; padding:5px 7px; margin:14px 0 6px; border-left:3px solid #555; }
        .cabecalho { border-bottom:2px solid #333; padding-bottom:8px; margin-bottom:10px; }
        .mini { font-size:11px; color:#555; }
        table { width:100%; border-collapse:collapse; }
        table.dados th { width:26%; text-align:left; font-weight:600; padding:3px 7px;
                         vertical-align:top; }
        table.dados td { padding:3px 7px; border-bottom:1px dotted #bbb; }
        table.animais { margin-top:8px; }
        table.animais th, table.animais td { border:1px solid #999; padding:4px 7px; }
        table.animais th { background:#f2f2f2; font-size:11px; }
        .dir { text-align:right; }
        .falta { color:#b00; }
        .alerta { border:1px solid #c47; background:#fff4f6; padding:8px 10px; margin-bottom:10px; }
        .ok { border:1px solid #2a7; background:#f2fbf6; padding:8px 10px; margin-bottom:10px; }
        .alerta ul { margin:6px 0 0 18px; padding:0; }
        .rodape { margin-top:18px; border-top:1px solid #999; padding-top:8px; font-size:11px;
                  color:#444; }
        @media print { .nao-imprime { display:none; } }
      </style></head><body>
      <div class="cabecalho">
        <h1>Ficha de preparo — Guia de Trânsito Animal</h1>
        <div class="mini">Para digitar em <b>${esc(portal.sistema || '')}</b> —
          ${esc(portal.orgao || '')}${portal.site ? ` · ${esc(portal.site)}` : ''}</div>
        <div class="mini">Esta folha <b>não é a GTA</b>: é a conferência do que vai ser
          digitado no portal. A guia válida é a que sair de lá.</div>
      </div>
      ${faltas}
      ${blocos}
      ${preparo.observacao ? `<section><h2>Observação</h2><div>${esc(preparo.observacao)}</div></section>` : ''}
      <div class="rodape">
        Conferido por ____________________________ em ____/____/________ ·
        AgroDock — Contratos e Gestão
      </div>
      <div class="nao-imprime" style="margin-top:14px">
        <button onclick="window.print()">Imprimir</button>
      </div>
      </body></html>`;

    const janela = window.open('', '_blank');
    if (!janela) return UI.erro('O navegador bloqueou a janela. Libere os pop-ups deste site.');
    janela.document.write(pagina);
    janela.document.close();
    setTimeout(() => janela.print(), 350);
  },
};
