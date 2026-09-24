/* Notas Fiscais — a tela onde a nota vira dinheiro no financeiro.

   O DF-e é a caixa de entrada (o que a SEFAZ entregou). Aqui é a gestão:
   ver a nota, os itens e o cliente/fornecedor, e então

     Faturar    -> gera a conta a pagar (nota de entrada) ou a receber (nota que
                   a empresa emitiu), com as parcelas das duplicatas da nota;
     Desfaturar -> apaga esse título e libera a nota de novo. Só no AgroDock:
                   a nota na SEFAZ não é tocada. */
const Notas = {
  filtros: { inicio: '', fim: '', situacao: '', faturamento: '', sentido: '', origem: '', busca: '' },
  selecionadas: new Set(),

  SITUACOES: [
    { valor: 'AUTORIZADA', rotulo: 'Autorizada' },
    { valor: 'CANCELADA', rotulo: 'Cancelada' },
    { valor: 'DENEGADA', rotulo: 'Denegada' },
  ],
  FATURAMENTO: [
    { valor: 'a-faturar', rotulo: 'Ainda a faturar' },
    { valor: 'faturadas', rotulo: 'Já faturadas' },
  ],
  SENTIDOS: [
    { valor: 'entrada', rotulo: 'Entrada (recebi a nota)' },
    { valor: 'saida', rotulo: 'Saída (minha empresa emitiu)' },
  ],
  ORIGENS: [
    { valor: 'DFE', rotulo: 'Recebidas (vieram da SEFAZ)' },
    { valor: 'EMITIDA', rotulo: 'Emitidas por mim' },
  ],
  TAG_EMISSAO: {
    RASCUNHO: 'tag-aberto', ENVIADA: 'tag-parcial', AUTORIZADA: 'tag-pago',
    REJEITADA: 'tag-vencido', CANCELADA: 'tag-cancelado',
  },
  TAG_SITUACAO: { AUTORIZADA: 'tag-pago', CANCELADA: 'tag-cancelado', DENEGADA: 'tag-vencido' },

  /* ================================================================ LISTAGEM */
  async tela() {
    const alvo = document.getElementById('pagina');
    const f = Notas.filtros;
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';

    const [resumo, dados] = await Promise.all([
      Api.get('/api/notas/resumo', { empresa_id: Estado.empresaId }),
      Api.get('/api/notas', { empresa_id: Estado.empresaId, ...f }),
    ]);
    Notas._linhas = dados.linhas;
    Notas.selecionadas = new Set(
      [...Notas.selecionadas].filter((id) => dados.linhas.some((n) => n.id === id && !n.faturada)),
    );
    const t = dados.totais;

    alvo.innerHTML = `
      <div class="grade g4" style="margin-bottom:18px">
        <div class="kpi destaque-azul"><div class="kpi-rotulo">Notas fiscais</div>
          <div class="kpi-valor">${resumo.documentos}</div>
          <div class="kpi-nota">${resumo.canceladas} cancelada(s) · ${resumo.so_resumo} só com resumo</div></div>
        <div class="kpi ${resumo.a_faturar ? 'destaque-vermelho' : 'destaque-verde'}">
          <div class="kpi-rotulo">A faturar</div>
          <div class="kpi-valor ${resumo.a_faturar ? 'negativo' : 'positivo'}">${resumo.a_faturar}</div>
          <div class="kpi-nota">${UI.moeda(resumo.valor_a_faturar)} sem título gerado</div></div>
        <div class="kpi destaque-verde"><div class="kpi-rotulo">Já faturadas</div>
          <div class="kpi-valor positivo">${resumo.faturadas}</div>
          <div class="kpi-nota">viraram conta a pagar ou a receber</div></div>
        <div class="kpi destaque-ambar"><div class="kpi-rotulo">Na lista abaixo</div>
          <div class="kpi-valor">${UI.moeda(t.valor)}</div>
          <div class="kpi-nota">${t.quantidade} nota(s)${
            t.emitidas ? ` · ${t.emitidas} emitida(s) por mim` : ''}${
            t.rascunhos ? ` · ${t.rascunhos} rascunho(s)` : ''}</div></div>
      </div>

      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Notas fiscais</h3>
            <div class="mini" id="resumo-notas"></div></div>
          <div class="espaco">
            <button class="btn" id="btn-exportar-notas">Exportar CSV</button>
            <button class="btn" id="btn-ir-dfe">Buscar na SEFAZ</button>
            <button class="btn" id="btn-series">Numeração</button>
            <button class="btn btn-verde" id="btn-emitir">+ Emitir NF-e</button>
            <button class="btn btn-primario oculto" id="btn-faturar-lote">Faturar selecionadas</button>
          </div>
        </div>
        <div class="filtros">
          ${UI.campo('Emissão de', `<input type="date" name="inicio" value="${f.inicio}">`)}
          ${UI.campo('Emissão até', `<input type="date" name="fim" value="${f.fim}">`)}
          ${UI.campo('Faturamento', UI.select('faturamento', Notas.FATURAMENTO, f.faturamento, { vazio: 'Todas' }))}
          ${UI.campo('Entrada ou saída', UI.select('sentido', Notas.SENTIDOS, f.sentido, { vazio: 'Todas' }))}
          ${UI.campo('Origem', UI.select('origem', Notas.ORIGENS, f.origem, { vazio: 'Todas' }))}
          ${UI.campo('Situação', UI.select('situacao', Notas.SITUACOES, f.situacao, { vazio: 'Todas' }))}
          ${UI.campo('Buscar', `<input name="busca" value="${UI.escapar(f.busca)}" placeholder="emitente, número, chave...">`)}
          <div class="acoes"><button class="btn btn-primario" id="btn-filtrar-notas">Filtrar</button></div>
        </div>
        <div class="cartao-corpo sem-padding" id="lista-notas"></div>
      </div>`;

    alvo.querySelector('#btn-filtrar-notas').onclick = () => {
      Object.assign(Notas.filtros, UI.lerFormulario(alvo.querySelector('.filtros')));
      Object.keys(Notas.filtros).forEach((k) => { Notas.filtros[k] = Notas.filtros[k] || ''; });
      Notas.tela();
    };
    alvo.querySelector('#btn-ir-dfe').onclick = () => App.irPara('/dfe');
    alvo.querySelector('#btn-emitir').onclick = () => Emissao.abrir(null, null);
    alvo.querySelector('#btn-series').onclick = () => Emissao.series();
    alvo.querySelector('#btn-exportar-notas').onclick = () =>
      UI.exportarTabela('notas-fiscais', '#lista-notas table');
    alvo.querySelector('#btn-faturar-lote').onclick = () => Notas.faturarLote();

    Notas.desenharLista();
  },

  desenharLista() {
    const linhas = Notas._linhas || [];
    const podeFaturar = (n) => !n.faturada && n.situacao !== 'CANCELADA'
      && n.status_emissao !== 'RASCUNHO' && n.status_emissao !== 'REJEITADA';
    document.getElementById('lista-notas').innerHTML = UI.tabela({
      vazio: 'Nenhuma nota por aqui. Vá em DF-e para buscar as notas na SEFAZ ou enviar um XML.',
      colunas: [
        { titulo: '', classe: 'centro',
          valor: (n, i) => (podeFaturar(n)
            ? `<input type="checkbox" data-sel="${i}" ${Notas.selecionadas.has(n.id) ? 'checked' : ''}>`
            : '') },
        { titulo: 'Emissão', valor: (n) => `${UI.data(n.data_emissao)}
            <div class="mini">${n.sentido}</div>` },
        { titulo: 'Nota', valor: (n) => `<span class="forte">${UI.escapar(n.numero || '-')}</span>
            <div class="mini">série ${UI.escapar(n.serie || '-')}</div>` },
        { titulo: 'Emitente', valor: (n) => `${UI.escapar(n.emitente_nome || '-')}
            <div class="mini">${UI.escapar(n.emitente_documento || '')}</div>` },
        { titulo: 'Cliente/Fornecedor', valor: (n) => (n.parceiro_nome
          ? UI.escapar(n.parceiro_nome)
          : '<span class="mini">não ligado ao cadastro</span>') },
        { titulo: 'Valor', classe: 'num', valor: (n) => UI.moeda(n.valor_total) },
        { titulo: 'Situação', classe: 'centro',
          valor: (n) => (n.origem === 'EMITIDA'
            ? `<span class="tag ${Notas.TAG_EMISSAO[n.status_emissao] || ''}">${
                UI.escapar(((n.status_emissao || '').charAt(0)
                  + (n.status_emissao || '').slice(1).toLowerCase()))}</span>
               <div class="mini">emitida por mim</div>`
            : `<span class="tag ${Notas.TAG_SITUACAO[n.situacao] || ''}">${
                UI.escapar((n.situacao || '').charAt(0) + (n.situacao || '').slice(1).toLowerCase())}</span>`) },
        { titulo: 'Faturamento', classe: 'centro', valor: (n) => Notas.selo(n) },
        { titulo: 'Ações', classe: 'centro',
          valor: (n, i) => `<button class="btn btn-mini" data-ficha="${i}">Abrir</button>
            ${n.tem_xml
              ? `<button class="btn btn-mini" data-xml="${i}"
                   title="Baixar o arquivo XML desta nota">XML</button>` : ''}
            ${n.tem_xml && n.origem === 'EMITIDA'
              ? `<button class="btn btn-mini" data-email="${i}" title="${n.email_enviado_em
                  ? `Já enviado em ${UI.data(n.email_enviado_em)} para ${
                      UI.escapar(n.email_destinatarios || '')} — clique para enviar de novo`
                  : 'Enviar o XML e a DANFE para o e-mail do cliente'}">${
                  n.email_enviado_em ? 'Reenviar' : 'E-mail'}</button>` : ''}
            ${n.faturada
              ? `<button class="btn btn-mini btn-perigo" data-desfaturar="${i}">Desfaturar</button>`
              : (podeFaturar(n)
                ? `<button class="btn btn-mini btn-verde" data-faturar="${i}">Faturar</button>` : '')}` },
      ],
      linhas,
    });

    const alvo = document.getElementById('lista-notas');
    alvo.querySelectorAll('[data-ficha]').forEach((b) => {
      b.onclick = () => {
        const nota = linhas[Number(b.dataset.ficha)];
        // nota emitida pela empresa abre no formulário de emissão; recebida, na ficha
        if (nota.origem === 'EMITIDA') return Emissao.abrir(nota.id);
        return Notas.ficha(nota.id);
      };
    });
    // baixa o XML direto da lista, sem precisar abrir a nota
    alvo.querySelectorAll('[data-xml]').forEach((b) => {
      b.onclick = () => DFe.baixarArquivo(linhas[Number(b.dataset.xml)]);
    });
    // manda (ou remanda) o XML e a DANFE para o cliente
    alvo.querySelectorAll('[data-email]').forEach((b) => {
      b.onclick = async () => {
        const nota = linhas[Number(b.dataset.email)];
        const rotulo = b.textContent;
        b.disabled = true;
        b.textContent = 'Enviando...';
        try {
          const r = await Api.postQuery(
            `/api/nfe/${nota.id}/enviar-email`, { empresa_id: Estado.empresaId });
          // saiu, mas sem o PDF: isso é aviso, não sucesso
          if (r.aviso) UI.erro(r.mensagem); else UI.sucesso(r.mensagem);
          Notas.tela();
        } catch (e) {
          UI.erro(e.message);
          b.disabled = false;
          b.textContent = rotulo;
        }
      };
    });
    alvo.querySelectorAll('[data-faturar]').forEach((b) => {
      b.onclick = () => Notas.faturar(linhas[Number(b.dataset.faturar)]);
    });
    alvo.querySelectorAll('[data-desfaturar]').forEach((b) => {
      b.onclick = () => Notas.desfaturar(linhas[Number(b.dataset.desfaturar)]);
    });
    alvo.querySelectorAll('[data-sel]').forEach((caixa) => {
      caixa.onchange = () => {
        const nota = linhas[Number(caixa.dataset.sel)];
        if (caixa.checked) Notas.selecionadas.add(nota.id);
        else Notas.selecionadas.delete(nota.id);
        Notas.atualizarRodape();
      };
    });
    Notas.atualizarRodape();
  },

  selo(n) {
    if (!n.faturada) {
      if (n.status_emissao === 'RASCUNHO') return '<span class="mini">rascunho</span>';
      return n.situacao === 'CANCELADA'
        ? '<span class="mini">nota cancelada</span>'
        : '<span class="tag tag-aberto">A faturar</span>';
    }
    const t = n.titulo || {};
    const rotulo = t.tipo === 'PAGAR' ? 'A pagar' : 'A receber';
    return `<span class="tag tag-pago">Faturada</span>
      <div class="mini">${rotulo} nº ${t.id} · ${t.num_parcelas} parc.${
        t.valor_baixado ? `<br>${UI.moeda(t.valor_baixado)} baixado` : ''}</div>`;
  },

  atualizarRodape() {
    const escolhidas = (Notas._linhas || []).filter((n) => Notas.selecionadas.has(n.id));
    const soma = escolhidas.reduce((s, n) => s + Number(n.valor_total || 0), 0);
    const botao = document.getElementById('btn-faturar-lote');
    if (botao) {
      botao.classList.toggle('oculto', !escolhidas.length);
      botao.textContent = `Faturar ${escolhidas.length} nota(s)`;
    }
    const resumo = document.getElementById('resumo-notas');
    if (resumo) {
      const t = (Notas._linhas || []).length;
      resumo.textContent = escolhidas.length
        ? `${escolhidas.length} nota(s) marcada(s) — ${UI.moeda(soma)}`
        : `${t} nota(s) na lista — marque as que quer faturar de uma vez`;
    }
  },

  /* ================================================================== FICHA */
  async ficha(notaId) {
    const dados = await Api.get(`/api/notas/${notaId}`);
    const n = dados.nota;
    const t = n.titulo;
    const p = dados.parceiro;
    const ti = dados.totais_itens;

    const itens = UI.tabela({
      vazio: 'Sem itens. Os itens aparecem depois que o XML completo é lido.',
      colunas: [
        { titulo: '#', classe: 'centro', valor: (i) => i.numero },
        { titulo: 'Produto', valor: (i) => `${UI.escapar(i.descricao)}
            <div class="mini">cód. ${UI.escapar(i.codigo || '-')}${
              i.produto_nome ? ` · cadastro: ${UI.escapar(i.produto_codigo || '')} ${UI.escapar(i.produto_nome)}`
                : ' · <span class="negativo">sem produto no cadastro</span>'}</div>` },
        { titulo: 'NCM/CFOP', classe: 'centro',
          valor: (i) => `${UI.escapar(i.ncm || '-')}<div class="mini">${UI.escapar(i.cfop || '')}</div>` },
        { titulo: 'Qtde', classe: 'num', valor: (i) => `${UI.numero(i.quantidade, 3)} ${UI.escapar(i.unidade || '')}` },
        { titulo: 'Unitário', classe: 'num', valor: (i) => UI.numero(i.valor_unitario, 4) },
        { titulo: 'Total', classe: 'num', valor: (i) => UI.moeda(i.valor_total) },
        { titulo: 'ICMS', classe: 'num',
          valor: (i) => `${UI.moeda(i.icms_valor)}<div class="mini">${UI.numero(i.icms_aliquota, 2)}%</div>` },
      ],
      linhas: dados.itens || [],
    });

    const pagamentos = (dados.pagamentos || []).length ? UI.tabela({
      colunas: [
        { titulo: 'Tipo', valor: (x) => (x.origem === 'DUPLICATA' ? 'Duplicata' : 'Pagamento') },
        { titulo: 'Descrição', valor: (x) => `${UI.escapar(x.descricao || '-')}${
          x.numero ? ` <span class="mini">nº ${UI.escapar(x.numero)}</span>` : ''}` },
        { titulo: 'Vencimento', classe: 'centro', valor: (x) => UI.data(x.vencimento) || '-' },
        { titulo: 'Valor', classe: 'num', valor: (x) => UI.moeda(x.valor) },
      ],
      linhas: dados.pagamentos,
    }) : '<div class="vazio">A nota não informou formas de pagamento nem duplicatas.</div>';

    const financeiro = t ? `
      <div class="grade g3" style="margin-bottom:12px">
        <div class="kpi destaque-verde"><div class="kpi-rotulo">Título gerado</div>
          <div class="kpi-valor" style="font-size:17px">${t.tipo === 'PAGAR' ? 'A pagar' : 'A receber'} nº ${t.id}</div>
          <div class="kpi-nota">${UI.escapar(t.status)}${
            n.faturada_em ? ` · faturada em ${UI.data(n.faturada_em)}` : ''}</div></div>
        <div class="kpi"><div class="kpi-rotulo">Valor</div>
          <div class="kpi-valor" style="font-size:19px">${UI.moeda(t.valor_total)}</div>
          <div class="kpi-nota">${t.num_parcelas} parcela(s)</div></div>
        <div class="kpi ${t.valor_baixado ? 'destaque-azul' : ''}"><div class="kpi-rotulo">Já baixado</div>
          <div class="kpi-valor" style="font-size:19px">${UI.moeda(t.valor_baixado)}</div>
          <div class="kpi-nota">saldo ${UI.moeda(t.saldo)}</div></div>
      </div>
      ${UI.tabela({
        colunas: [
          { titulo: 'Parcela', classe: 'centro', valor: (x) => x.numero },
          { titulo: 'Vencimento', classe: 'centro', valor: (x) => UI.data(x.data_vencimento) },
          { titulo: 'Valor', classe: 'num', valor: (x) => UI.moeda(x.valor) },
          { titulo: 'Baixado', classe: 'num', valor: (x) => UI.moeda(x.valor_baixado) },
          { titulo: 'Situação', classe: 'centro', valor: (x) => UI.tagStatus(x.status) },
        ],
        linhas: t.parcelas || [],
      })}
      ${t.tem_baixa ? `<div class="mini" style="margin-top:8px">
        Este título já tem baixa. Para desfaturar, estorne a baixa antes em
        Contas a ${t.tipo === 'PAGAR' ? 'Pagar' : 'Receber'}.</div>` : ''}`
      : `<div class="vazio">Esta nota ainda não foi faturada.<br>
          <span class="mini">Faturar gera a conta a ${
            n.tipo_titulo_sugerido === 'PAGAR' ? 'pagar' : 'receber'} com as parcelas da nota.</span></div>`;

    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <div class="grade g4" style="margin-bottom:14px">
        <div class="kpi"><div class="kpi-rotulo">Nota</div>
          <div class="kpi-valor">${UI.escapar(n.numero || '-')}</div>
          <div class="kpi-nota">série ${UI.escapar(n.serie || '-')} · ${UI.data(n.data_emissao)}</div></div>
        <div class="kpi"><div class="kpi-rotulo">Valor total</div>
          <div class="kpi-valor">${UI.moeda(n.valor_total)}</div>
          <div class="kpi-nota">produtos ${UI.moeda(ti.produtos)} · ICMS ${UI.moeda(ti.icms)}</div></div>
        <div class="kpi"><div class="kpi-rotulo">Situação</div>
          <div class="kpi-valor" style="font-size:17px">${UI.escapar(n.situacao)}</div>
          <div class="kpi-nota">${n.sentido}${n.manifestacao ? ` · ${UI.escapar(n.manifestacao_nome)}` : ''}</div></div>
        <div class="kpi ${n.faturada ? 'destaque-verde' : 'destaque-ambar'}">
          <div class="kpi-rotulo">Faturamento</div>
          <div class="kpi-valor" style="font-size:17px">${n.faturada ? 'Faturada' : 'A faturar'}</div>
          <div class="kpi-nota">${n.faturada ? `título nº ${t.id}` : 'ainda não virou título'}</div></div>
      </div>

      <div class="abas" id="abas-nota">
        <button class="aba ativa" data-painel="itens">Itens (${ti.quantidade})</button>
        <button class="aba" data-painel="parceiro">Cliente/Fornecedor</button>
        <button class="aba" data-painel="pagamentos">Pagamentos</button>
        <button class="aba" data-painel="financeiro">Financeiro</button>
      </div>

      <div data-conteudo="itens">
        ${ti.sem_produto ? `<div class="mini" style="margin-bottom:8px">
          ${ti.sem_produto} item(ns) ainda sem produto no cadastro.</div>` : ''}
        ${itens}
      </div>
      <div data-conteudo="parceiro" class="oculto">
        ${p ? `<div class="cartao"><div class="cartao-corpo">
            <b>${UI.escapar(p.nome)}</b>
            <div class="mini">${UI.escapar(p.documento || '')} · IE ${UI.escapar(p.rg_ie || '-')}
              · ${UI.escapar({ CLIENTE: 'Cliente', FORNECEDOR: 'Fornecedor', AMBOS: 'Cliente e fornecedor' }[p.tipo] || p.tipo)}</div>
            <div class="mini" style="margin-top:6px">${UI.escapar(p.endereco || 'sem endereço')}</div>
            <div class="mini">${UI.escapar(p.telefone || '')} ${UI.escapar(p.email || '')}</div>
            <div class="mini" style="margin-top:8px">
              Código do município: ${UI.escapar(p.codigo_municipio || '—')} ·
              Indicador de IE: ${UI.escapar(p.indicador_ie || '—')} ·
              Regime: ${UI.escapar(p.regime_tributario || '—')}</div>
            ${p.completo_para_nota
              ? '<div class="mini positivo" style="margin-top:6px">Cadastro completo para emissão de nota.</div>'
              : '<div class="mini negativo" style="margin-top:6px">Faltam dados fiscais (UF, código do município ou indicador de IE) — complete em Cadastros.</div>'}
            <div class="espaco" style="margin-top:12px">
              <button class="btn btn-mini" id="btn-abrir-parceiro">Abrir no cadastro</button>
              ${n.faturada ? '' : '<button class="btn btn-mini" id="btn-trocar-parceiro">Trocar</button>'}
            </div>
          </div></div>`
          : `<div class="vazio">A nota ainda não está ligada a um cliente/fornecedor.
              ${n.faturada ? '' : '<br><button class="btn btn-mini" id="btn-trocar-parceiro" style="margin-top:8px">Escolher agora</button>'}</div>`}
      </div>
      <div data-conteudo="pagamentos" class="oculto">${pagamentos}</div>
      <div data-conteudo="financeiro" class="oculto">${financeiro}</div>`;

    UI.abrirModal({
      titulo: `NF-e ${n.numero || ''} — ${n.emitente_nome || ''}`,
      corpo,
      largo: true,
      botoes: [
        { rotulo: 'Fechar', acao: UI.fecharModal },
        ...(n.tem_xml ? [{ rotulo: 'DANFE', acao: () => DFe.abrirDanfe(n.id) }] : []),
        { rotulo: 'XML', acao: () => DFe.baixarArquivo(n) },
        ...(n.faturada
          ? [{ rotulo: 'Ver o título', acao: () => { UI.fecharModal(); App.irPara(t.tipo === 'PAGAR' ? '/pagar' : '/receber'); } },
             { rotulo: 'Desfaturar', classe: 'btn-perigo', acao: () => Notas.desfaturar(n) }]
          : [{ rotulo: 'Faturar', classe: 'btn-primario', acao: () => Notas.faturar(n) }]),
      ],
    });

    corpo.querySelectorAll('[data-painel]').forEach((botao) => {
      botao.onclick = () => {
        corpo.querySelectorAll('[data-painel]').forEach((b) => b.classList.remove('ativa'));
        botao.classList.add('ativa');
        corpo.querySelectorAll('[data-conteudo]').forEach((caixa) => {
          caixa.classList.toggle('oculto', caixa.dataset.conteudo !== botao.dataset.painel);
        });
      };
    });
    const trocar = corpo.querySelector('#btn-trocar-parceiro');
    if (trocar) trocar.onclick = () => Notas.trocarParceiro(n);
    const abrirParceiro = corpo.querySelector('#btn-abrir-parceiro');
    if (abrirParceiro) {
      abrirParceiro.onclick = () => { UI.fecharModal(); App.irPara('/cadastros/parceiros'); };
    }
  },

  /* ============================================================== FATURAR */
  async faturar(nota) {
    const dados = await Api.get(`/api/notas/${nota.id}`);
    const n = dados.nota;
    const duplicatas = (dados.pagamentos || []).filter((p) => p.origem === 'DUPLICATA' && p.vencimento);
    const pagar = n.tipo_titulo_sugerido === 'PAGAR';

    const area = UI.abrirModal({
      titulo: `Faturar a NF-e ${n.numero || ''}`,
      largo: true,
      corpo: `
        <p class="mini" style="margin-top:0">Faturar gera a conta a <b>${pagar ? 'pagar' : 'receber'}</b>
        desta nota, já classificada e contabilizada. ${duplicatas.length
          ? `A nota tem <b>${duplicatas.length} duplicata(s)</b> — vira uma parcela para cada uma.`
          : 'A nota não trouxe duplicatas — sai uma parcela só.'}</p>

        <div class="cartao" style="margin-bottom:12px"><div class="cartao-corpo">
          <b>${UI.escapar(n.emitente_nome || '')}</b>
          <div class="mini">${UI.escapar(n.emitente_documento || '')} · nota ${UI.escapar(n.numero || '')}
            de ${UI.data(n.data_emissao)} · ${UI.moeda(n.valor_total)}</div>
          ${dados.parceiro
            ? `<div class="mini" style="margin-top:4px">Título no nome de <b>${UI.escapar(dados.parceiro.nome)}</b></div>`
            : '<div class="mini negativo" style="margin-top:4px">A nota ainda não está ligada a um cliente/fornecedor — escolha abaixo.</div>'}
        </div></div>

        <div class="linha-campos">
          ${UI.campo('Tipo do título', UI.select('tipo_titulo', [
            { valor: 'PAGAR', rotulo: 'Conta a pagar' },
            { valor: 'RECEBER', rotulo: 'Conta a receber' },
          ], n.tipo_titulo_sugerido, { vazio: false }),
            pagar ? 'a nota é de entrada' : 'a nota foi emitida pela sua empresa')}
          ${UI.campo('Cliente/Fornecedor', UI.select('parceiro_id',
            UI.opcoesParceiros(), (dados.parceiro || {}).id || '', { vazio: 'Usar o do emitente' }))}
          ${UI.campo('Conta contábil', UI.select('conta_contabil_id',
            UI.opcoesContas(['CUSTO', 'DESPESA', 'RECEITA', 'ATIVO']), '', { vazio: 'Usar a conta padrão' }))}
          ${UI.campo('Centro de custo', UI.select('centro_custo_id', UI.opcoesCentros(), '', { vazio: 'Nenhum' }))}
          ${UI.campo('Operação', UI.select('operacao_id', UI.opcoesOperacoes(), '', { vazio: 'Nenhuma' }))}
          ${UI.campo('Vencimento', '<input type="date" name="vencimento" value="">',
            duplicatas.length ? 'preenchido, ignora as duplicatas e gera uma parcela só' : 'padrão: a data de emissão')}
          ${UI.campo('Observação', '<input name="observacao" placeholder="opcional">', '', 2)}
        </div>

        ${duplicatas.length ? `<h4 style="margin:14px 0 6px">Parcelas que serão criadas</h4>
          ${UI.tabela({
            colunas: [
              { titulo: 'Parcela', classe: 'centro', valor: (d, i) => i + 1 },
              { titulo: 'Duplicata', valor: (d) => UI.escapar(d.numero || '-') },
              { titulo: 'Vencimento', classe: 'centro', valor: (d) => UI.data(d.vencimento) },
              { titulo: 'Valor', classe: 'num', valor: (d) => UI.moeda(d.valor) },
            ],
            linhas: duplicatas,
          })}` : ''}`,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        {
          rotulo: 'Faturar',
          classe: 'btn-primario',
          acao: async (corpo) => {
            const form = UI.lerFormulario(corpo);
            try {
              const r = await Api.post(`/api/notas/${n.id}/faturar`, {
                empresa_id: Estado.empresaId,
                tipo_titulo: form.tipo_titulo,
                parceiro_id: form.parceiro_id || null,
                conta_contabil_id: form.conta_contabil_id || null,
                centro_custo_id: form.centro_custo_id || null,
                operacao_id: form.operacao_id || null,
                vencimento: form.vencimento || null,
                observacao: form.observacao || null,
              });
              UI.fecharModal();
              UI.sucesso(r.mensagem);
              await Api.carregarCache(true);
              Notas.tela();
            } catch (e) {
              UI.erro(e.message);
            }
          },
        },
      ],
    });
    return area;
  },

  async desfaturar(nota) {
    const t = nota.titulo || {};
    const ok = await UI.confirmar(
      `Desfaturar a nota ${nota.numero || ''}? A conta a ${t.tipo === 'PAGAR' ? 'pagar' : 'receber'}`
      + ` nº ${t.id || ''} será apagada e a nota volta para "a faturar". `
      + 'Isso não mexe na SEFAZ — a nota continua lá como está.',
      'Desfaturar',
    );
    if (!ok) return;
    try {
      const r = await Api.post(`/api/notas/${nota.id}/desfaturar`, {});
      UI.sucesso(r.mensagem);
      Notas.tela();
    } catch (e) {
      UI.erro(e.message);
    }
  },

  /* Faturamento em lote das notas marcadas na lista. */
  faturarLote() {
    const escolhidas = (Notas._linhas || []).filter((n) => Notas.selecionadas.has(n.id));
    if (!escolhidas.length) return UI.erro('Marque as notas que quer faturar.');
    const soma = escolhidas.reduce((s, n) => s + Number(n.valor_total || 0), 0);

    UI.abrirModal({
      titulo: `Faturar ${escolhidas.length} nota(s)`,
      largo: true,
      corpo: `
        <p class="mini" style="margin-top:0">Cada nota vira um título próprio, com as parcelas
        das duplicatas dela. O tipo (a pagar ou a receber) sai do sentido de cada nota.</p>
        <div class="linha-campos">
          ${UI.campo('Conta contábil', UI.select('conta_contabil_id',
            UI.opcoesContas(['CUSTO', 'DESPESA', 'RECEITA', 'ATIVO']), '', { vazio: 'Usar a conta padrão de cada tipo' }))}
          ${UI.campo('Centro de custo', UI.select('centro_custo_id', UI.opcoesCentros(), '', { vazio: 'Nenhum' }))}
          ${UI.campo('Operação', UI.select('operacao_id', UI.opcoesOperacoes(), '', { vazio: 'Nenhuma' }))}
        </div>
        ${UI.tabela({
          colunas: [
            { titulo: 'Emissão', valor: (n) => UI.data(n.data_emissao) },
            { titulo: 'Nota', valor: (n) => UI.escapar(n.numero || '-') },
            { titulo: 'Emitente', valor: (n) => UI.escapar(n.emitente_nome || '-') },
            { titulo: 'Tipo', classe: 'centro',
              valor: (n) => (n.tipo_titulo_sugerido === 'PAGAR' ? 'A pagar' : 'A receber') },
            { titulo: 'Valor', classe: 'num', valor: (n) => UI.moeda(n.valor_total) },
          ],
          linhas: escolhidas,
          rodape: null,
        })}
        <div class="mini" style="margin-top:8px">Total: <b>${UI.moeda(soma)}</b></div>`,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        {
          rotulo: 'Faturar todas',
          classe: 'btn-primario',
          acao: async (corpo) => {
            const form = UI.lerFormulario(corpo);
            UI.trocarBotoes([{ rotulo: 'Faturando...', acao: () => {} }], corpo);
            try {
              const r = await Api.post('/api/notas/faturar-lote', {
                empresa_id: Estado.empresaId,
                notas: escolhidas.map((n) => n.id),
                conta_contabil_id: form.conta_contabil_id || null,
                centro_custo_id: form.centro_custo_id || null,
                operacao_id: form.operacao_id || null,
              });
              UI.fecharModal();
              if (r.recusadas.length) {
                UI.erro(`${r.mensagem} ${r.recusadas.map((x) => `Nota ${x.numero || x.nota_id}: ${x.motivo}`).join(' ')}`);
              } else {
                UI.sucesso(r.mensagem);
              }
              Notas.selecionadas.clear();
              await Api.carregarCache(true);
              Notas.tela();
            } catch (e) {
              UI.erro(e.message);
              UI.fecharModal();
            }
          },
        },
      ],
    });
  },

  /* Troca o cliente/fornecedor da nota (só enquanto ela não está faturada). */
  trocarParceiro(nota) {
    UI.abrirModal({
      titulo: `Cliente/Fornecedor da NF-e ${nota.numero || ''}`,
      corpo: `<div class="linha-campos">
          ${UI.campo('Cliente/Fornecedor', UI.select('parceiro_id', UI.opcoesParceiros(),
            nota.parceiro_id || '', { vazio: 'Nenhum' }),
            'é em nome dele que o título será gerado')}
        </div>`,
      botoes: [
        { rotulo: 'Voltar', acao: () => Notas.ficha(nota.id) },
        {
          rotulo: 'Salvar',
          classe: 'btn-primario',
          acao: async (corpo) => {
            const form = UI.lerFormulario(corpo);
            try {
              await Api.put(`/api/notas/${nota.id}`, {
                empresa_id: Estado.empresaId, parceiro_id: form.parceiro_id || null,
              });
              UI.sucesso('Cliente/fornecedor da nota atualizado.');
              Notas.ficha(nota.id);
            } catch (e) {
              UI.erro(e.message);
            }
          },
        },
      ],
    });
  },
};
