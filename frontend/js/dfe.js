/* DF-e — documentos fiscais eletrônicos emitidos contra o CNPJ da empresa.

   Duas abas:
     Documentos ..... lista o que a SEFAZ entregou, com XML, DANFE, manifestação
                      do destinatário e importação para o sistema;
     Certificado .... envia o certificado digital A1 (.pfx) e mostra a validade.

   O certificado sai daqui direto para o servidor e nunca volta: a tela mostra
   só o titular, o CNPJ e o prazo de validade. */
const DFe = {
  aba: 'documentos',
  filtros: { inicio: '', fim: '', situacao: '', manifestacao: '', formato: '', busca: '' },

  SITUACOES: [
    { valor: 'AUTORIZADA', rotulo: 'Autorizada' },
    { valor: 'CANCELADA', rotulo: 'Cancelada' },
    { valor: 'DENEGADA', rotulo: 'Denegada' },
  ],
  MANIFESTACOES: [
    { valor: 'SEM', rotulo: 'Ainda sem manifestação' },
    { valor: 'CIENCIA', rotulo: 'Ciência da operação' },
    { valor: 'CONFIRMADA', rotulo: 'Confirmada' },
    { valor: 'DESCONHECIDA', rotulo: 'Desconhecida' },
    { valor: 'NAO_REALIZADA', rotulo: 'Operação não realizada' },
  ],
  FORMATOS: [
    { valor: 'resumo', rotulo: 'Só o resumo (sem XML completo)' },
    { valor: 'completo', rotulo: 'Com XML completo' },
    { valor: 'pendente', rotulo: 'Ainda não importadas' },
    { valor: 'importada', rotulo: 'Já importadas' },
  ],
  UFS: ['AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA', 'PB',
    'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO'],

  TAG_SITUACAO: { AUTORIZADA: 'tag-pago', CANCELADA: 'tag-cancelado', DENEGADA: 'tag-vencido' },
  TAG_MANIFESTACAO: {
    CIENCIA: 'tag-parcial', CONFIRMADA: 'tag-pago',
    DESCONHECIDA: 'tag-vencido', NAO_REALIZADA: 'tag-cancelado',
  },

  /* ==================================================================== tela */
  async tela(aba) {
    DFe.aba = ['documentos', 'certificado'].includes(aba) ? aba : DFe.aba;
    const pagina = document.getElementById('pagina');
    pagina.innerHTML = `
      <div class="abas">
        <button class="aba ${DFe.aba === 'documentos' ? 'ativa' : ''}" data-aba="documentos">Documentos</button>
        <button class="aba ${DFe.aba === 'certificado' ? 'ativa' : ''}" data-aba="certificado">Certificado digital</button>
      </div>
      <div id="area-dfe"><div class="cartao"><div class="vazio">Carregando...</div></div></div>`;
    pagina.querySelectorAll('[data-aba]').forEach((b) => {
      b.onclick = () => { DFe.aba = b.dataset.aba; DFe.tela(); };
    });
    if (DFe.aba === 'certificado') return DFe.telaCertificado();
    return DFe.telaDocumentos();
  },

  alvo() {
    return document.getElementById('area-dfe') || document.getElementById('pagina');
  },

  /* ============================================================== documentos */
  async telaDocumentos() {
    const alvo = DFe.alvo();
    const f = DFe.filtros;
    const [resumo, notas] = await Promise.all([
      Api.get('/api/dfe/resumo', { empresa_id: Estado.empresaId }),
      Api.get('/api/dfe/notas', { empresa_id: Estado.empresaId, ...f }),
    ]);
    DFe._notas = notas;
    const cert = resumo.certificado || {};

    alvo.innerHTML = `
      ${DFe.avisoCertificado(cert)}
      <div class="grade g4" style="margin-bottom:18px">
        <div class="kpi destaque-azul"><div class="kpi-rotulo">Documentos recebidos</div>
          <div class="kpi-valor">${resumo.documentos}</div>
          <div class="kpi-nota">${UI.moeda(resumo.valor_total)} em notas válidas</div></div>
        <div class="kpi ${resumo.sem_manifestacao ? 'destaque-ambar' : ''}">
          <div class="kpi-rotulo">Sem manifestação</div>
          <div class="kpi-valor">${resumo.sem_manifestacao}</div>
          <div class="kpi-nota">a ciência libera o XML completo</div></div>
        <div class="kpi ${resumo.somente_resumo ? 'destaque-ambar' : ''}">
          <div class="kpi-rotulo">Só com resumo</div>
          <div class="kpi-valor">${resumo.somente_resumo}</div>
          <div class="kpi-nota">ainda sem o XML para DANFE</div></div>
        <div class="kpi ${resumo.nao_importadas ? 'destaque-vermelho' : 'destaque-verde'}">
          <div class="kpi-rotulo">A importar</div>
          <div class="kpi-valor">${resumo.nao_importadas}</div>
          <div class="kpi-nota">${resumo.canceladas} cancelada(s) na lista</div></div>
      </div>

      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Documentos fiscais</h3>
            <div class="mini" id="resumo-dfe">${notas.length} documento(s) na lista${
              cert.ultima_consulta ? ` — última busca em ${UI.data(cert.ultima_consulta)}` : ''}</div>
          </div>
          <div class="espaco">
            <button class="btn" id="btn-exportar-dfe">Exportar CSV</button>
            <button class="btn" id="btn-enviar-xml">Enviar XML</button>
            <button class="btn btn-primario" id="btn-buscar-sefaz">Buscar na SEFAZ</button>
          </div>
        </div>
        <div class="filtros">
          ${UI.campo('Emissão de', `<input type="date" name="inicio" value="${f.inicio}">`)}
          ${UI.campo('Emissão até', `<input type="date" name="fim" value="${f.fim}">`)}
          ${UI.campo('Situação', UI.select('situacao', DFe.SITUACOES
            .map((s) => ({ valor: s.valor, rotulo: s.rotulo })), f.situacao, { vazio: 'Todas' }))}
          ${UI.campo('Manifestação', UI.select('manifestacao', DFe.MANIFESTACOES
            .map((m) => ({ valor: m.valor, rotulo: m.rotulo })), f.manifestacao, { vazio: 'Todas' }))}
          ${UI.campo('Situação no sistema', UI.select('formato', DFe.FORMATOS
            .map((x) => ({ valor: x.valor, rotulo: x.rotulo })), f.formato, { vazio: 'Todos' }))}
          ${UI.campo('Buscar', `<input name="busca" value="${UI.escapar(f.busca)}" placeholder="emitente, número, chave...">`)}
          <div class="acoes"><button class="btn btn-primario" id="btn-filtrar-dfe">Filtrar</button></div>
        </div>
        <div class="cartao-corpo sem-padding" id="lista-dfe"></div>
      </div>`;

    alvo.querySelector('#btn-filtrar-dfe').onclick = () => {
      Object.assign(DFe.filtros, UI.lerFormulario(alvo.querySelector('.filtros')));
      Object.keys(DFe.filtros).forEach((k) => { DFe.filtros[k] = DFe.filtros[k] || ''; });
      DFe.telaDocumentos();
    };
    alvo.querySelector('#btn-buscar-sefaz').onclick = () => DFe.buscar();
    alvo.querySelector('#btn-enviar-xml').onclick = () => DFe.enviarXml();
    alvo.querySelector('#btn-exportar-dfe').onclick = () =>
      UI.exportarTabela('documentos-fiscais', '#lista-dfe table');

    alvo.querySelector('#lista-dfe').innerHTML = UI.tabela({
      vazio: cert.configurado
        ? 'Nenhum documento por aqui. Clique em "Buscar na SEFAZ" para trazer as notas emitidas contra o seu CNPJ.'
        : 'Cadastre o certificado digital A1 na aba "Certificado digital" para buscar as notas na SEFAZ.',
      colunas: [
        { titulo: 'Emissão', valor: (n) => `${UI.data(n.data_emissao)}
            <div class="mini">${n.sentido}${n.nsu ? ` · NSU ${Number(n.nsu)}` : ''}</div>` },
        { titulo: 'Nota', valor: (n) => `<span class="forte">${UI.escapar(n.numero || '-')}</span>
            <div class="mini">série ${UI.escapar(n.serie || '-')} · mod. ${UI.escapar(n.modelo || '55')}</div>` },
        { titulo: 'Emitente', valor: (n) => `${UI.escapar(n.emitente_nome || '-')}
            <div class="mini">${UI.escapar(n.emitente_documento || '')} ${UI.escapar(n.emitente_uf || '')}</div>` },
        { titulo: 'Valor', classe: 'num', valor: (n) => UI.moeda(n.valor_total) },
        { titulo: 'Situação', classe: 'centro',
          valor: (n) => `<span class="tag ${DFe.TAG_SITUACAO[n.situacao] || ''}">${
            UI.escapar((n.situacao || '').charAt(0) + (n.situacao || '').slice(1).toLowerCase())}</span>
            ${n.resumo ? '<div class="mini">só resumo</div>' : ''}` },
        { titulo: 'Manifestação', classe: 'centro',
          valor: (n) => (n.manifestacao
            ? `<span class="tag ${DFe.TAG_MANIFESTACAO[n.manifestacao] || ''}">${UI.escapar(n.manifestacao_nome)}</span>`
            : '<span class="mini">—</span>') },
        { titulo: 'No sistema', classe: 'centro',
          valor: (n) => (n.importada
            ? '<span class="tag tag-pago">Importada</span>'
            : '<span class="mini">a importar</span>') },
        { titulo: 'Ações', classe: 'centro',
          valor: (n, i) => `<button class="btn btn-mini" data-ficha="${i}">Abrir</button>
            ${n.tem_xml ? `<button class="btn btn-mini" data-danfe="${n.id}">DANFE</button>` : ''}
            <button class="btn btn-mini" data-xml="${i}">XML</button>` },
      ],
      linhas: notas,
    });

    alvo.querySelectorAll('[data-ficha]').forEach((b) => {
      b.onclick = () => DFe.ficha(notas[Number(b.dataset.ficha)].id);
    });
    alvo.querySelectorAll('[data-xml]').forEach((b) => {
      b.onclick = () => DFe.baixarArquivo(notas[Number(b.dataset.xml)]);
    });
    alvo.querySelectorAll('[data-danfe]').forEach((b) => {
      b.onclick = () => DFe.abrirDanfe(Number(b.dataset.danfe));
    });
  },

  avisoCertificado(cert) {
    if (!cert.configurado) {
      return `<div class="cartao" style="margin-bottom:16px;border-left:4px solid var(--ambar)">
        <div class="cartao-corpo">
          <b>Certificado digital não cadastrado.</b>
          <div class="mini">Para buscar os documentos direto na SEFAZ o sistema precisa do
          certificado A1 da empresa (arquivo .pfx e senha). Vá na aba
          <b>Certificado digital</b>.</div>
        </div></div>`;
    }
    if (cert.vencido) {
      return `<div class="cartao" style="margin-bottom:16px;border-left:4px solid var(--vermelho)">
        <div class="cartao-corpo"><b>O certificado venceu em ${UI.data(cert.valido_ate)}.</b>
          <div class="mini">Envie o certificado novo na aba Certificado digital.</div></div></div>`;
    }
    if (cert.dias_para_vencer !== null && cert.dias_para_vencer <= 30) {
      return `<div class="cartao" style="margin-bottom:16px;border-left:4px solid var(--ambar)">
        <div class="cartao-corpo"><b>O certificado vence em ${cert.dias_para_vencer} dia(s)</b>
          (${UI.data(cert.valido_ate)}).</div></div>`;
    }
    if (cert.ambiente === '2') {
      return `<div class="cartao" style="margin-bottom:16px;border-left:4px solid var(--ambar)">
        <div class="cartao-corpo"><b>Ambiente de homologação (teste).</b>
          <div class="mini">Em homologação a SEFAZ não entrega as notas reais. Para trabalhar
          com as notas da empresa, troque para Produção na aba Certificado digital.</div></div></div>`;
    }
    return '';
  },

  /* ---------------------------------------------------------- buscar / enviar */
  async buscar() {
    UI.abrirModal({
      titulo: 'Buscar documentos na SEFAZ',
      corpo: `
        <p class="mini" style="margin-top:0">A SEFAZ entrega os documentos em blocos de até 50,
        seguindo o NSU (a numeração que ela usa para controlar o que você já recebeu).
        O sistema guarda o ponto em que parou e continua da próxima vez.</p>
        <div class="linha-campos">
          ${UI.campo('Quantos blocos buscar agora', `<input type="number" name="paginas" value="5" min="1" max="20">`,
            'cada bloco traz até 50 documentos')}
          <label class="campo"><span>Recomeçar do zero</span>
            <span><input type="checkbox" name="desde_o_inicio"> Buscar tudo o que a SEFAZ ainda guarda</span></label>
        </div>
        <p class="mini">A SEFAZ mantém os documentos por cerca de 90 dias. "Recomeçar do zero"
        traz tudo de novo — os que já estão aqui só são atualizados, nada é duplicado.</p>`,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        {
          rotulo: 'Buscar agora',
          classe: 'btn-primario',
          acao: async (corpo, botao) => {
            const dados = UI.lerFormulario(corpo);
            UI.trocarBotoes([{ rotulo: 'Consultando a SEFAZ...', acao: () => {} }], corpo);
            try {
              const r = await Api.post('/api/dfe/buscar', {
                empresa_id: Estado.empresaId,
                paginas: dados.paginas || 5,
                desde_o_inicio: Boolean(dados.desde_o_inicio),
              });
              UI.fecharModal();
              UI.sucesso(r.mensagem);
              if (r.certificado && r.certificado.faltam_documentos) {
                UI.aviso('Ainda há documentos na SEFAZ. Clique em "Buscar na SEFAZ" de novo para continuar.');
              }
              DFe.telaDocumentos();
            } catch (e) {
              UI.erro(e.message);
              UI.fecharModal();
            }
          },
        },
      ],
    });
  },

  enviarXml() {
    const area = UI.abrirModal({
      titulo: 'Enviar XML recebido por e-mail',
      corpo: `
        <p class="mini" style="margin-top:0">Use isto quando o fornecedor mandar o XML da nota
        por e-mail. O arquivo entra na lista igual aos que vêm da SEFAZ.</p>
        <div class="linha-campos">
          ${UI.campo('Arquivo XML', '<input type="file" id="arquivo-xml" accept=".xml,text/xml,application/xml">')}
        </div>`,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        {
          rotulo: 'Enviar',
          classe: 'btn-primario',
          acao: async () => {
            const campo = area.querySelector('#arquivo-xml');
            if (!campo.files.length) return UI.erro('Escolha o arquivo XML.');
            const formulario = new FormData();
            formulario.append('empresa_id', Estado.empresaId);
            formulario.append('arquivo', campo.files[0]);
            try {
              const r = await DFe.enviarFormulario('/api/dfe/enviar-xml', formulario);
              UI.fecharModal();
              UI.sucesso(r.mensagem);
              DFe.telaDocumentos();
            } catch (e) {
              UI.erro(e.message);
            }
          },
        },
      ],
    });
  },

  /** POST multipart com o token da sessão (o Api.post só manda JSON). */
  async enviarFormulario(caminho, formulario) {
    const resposta = await fetch(caminho, {
      method: 'POST',
      headers: Estado.token ? { Authorization: `Bearer ${Estado.token}` } : {},
      body: formulario,
    });
    const texto = await resposta.text();
    let corpo = {};
    try { corpo = texto ? JSON.parse(texto) : {}; } catch { corpo = { detail: texto.slice(0, 300) }; }
    if (!resposta.ok) {
      const d = corpo.detail;
      throw new Error(Array.isArray(d) ? d.map((x) => x.msg || '').join('; ') : d || 'Erro inesperado');
    }
    return corpo;
  },

  /** Baixa um arquivo da API levando o token (não dá para usar link direto). */
  async baixarArquivo(nota) {
    try {
      const resposta = await fetch(`/api/dfe/notas/${nota.id}/xml`, {
        headers: Estado.token ? { Authorization: `Bearer ${Estado.token}` } : {},
      });
      if (!resposta.ok) throw new Error('Este documento não tem XML guardado.');
      const blob = await resposta.blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `${nota.chave || nota.id}.xml`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (e) {
      UI.erro(e.message);
    }
  },

  /** Abre a DANFE numa aba nova (a página vem do servidor, já pronta para imprimir). */
  async abrirDanfe(notaId) {
    const aba = window.open('', '_blank');
    try {
      const resposta = await fetch(`/api/dfe/notas/${notaId}/danfe`, {
        headers: Estado.token ? { Authorization: `Bearer ${Estado.token}` } : {},
      });
      const texto = await resposta.text();
      if (!resposta.ok) {
        if (aba) aba.close();
        let corpo = {};
        try { corpo = JSON.parse(texto); } catch { corpo = {}; }
        throw new Error(corpo.detail || 'Não foi possível gerar a DANFE.');
      }
      if (!aba) return UI.erro('O navegador bloqueou a aba nova. Libere as janelas deste site.');
      aba.document.open();
      aba.document.write(texto);
      aba.document.close();
    } catch (e) {
      UI.erro(e.message);
    }
  },

  /* -------------------------------------------------------------- ficha */
  async ficha(notaId) {
    const dados = await Api.get(`/api/dfe/notas/${notaId}`);
    const n = dados.nota;
    const itens = dados.itens || [];
    const pagamentos = dados.pagamentos || [];

    const linhaItens = UI.tabela({
      vazio: 'Sem itens.',
      colunas: [
        { titulo: '#', classe: 'centro', valor: (i) => i.numero },
        { titulo: 'Produto', valor: (i) => `${UI.escapar(i.descricao)}
            <div class="mini">cód. ${UI.escapar(i.codigo || '-')}${
              i.produto_nome ? ` · cadastro: ${UI.escapar(i.produto_nome)}` : ''}</div>` },
        { titulo: 'NCM/CFOP', classe: 'centro',
          valor: (i) => `${UI.escapar(i.ncm || '-')}<div class="mini">${UI.escapar(i.cfop || '')}</div>` },
        { titulo: 'Qtde', classe: 'num', valor: (i) => `${UI.numero(i.quantidade, 3)} ${UI.escapar(i.unidade || '')}` },
        { titulo: 'Unitário', classe: 'num', valor: (i) => UI.numero(i.valor_unitario, 4) },
        { titulo: 'Total', classe: 'num', valor: (i) => UI.moeda(i.valor_total) },
        { titulo: 'ICMS', classe: 'num',
          valor: (i) => `${UI.moeda(i.icms_valor)}<div class="mini">${UI.numero(i.icms_aliquota, 2)}%</div>` },
      ],
      linhas: itens,
    });

    const linhaPagamentos = pagamentos.length ? UI.tabela({
      colunas: [
        { titulo: 'Tipo', valor: (p) => UI.escapar(p.origem === 'DUPLICATA' ? 'Duplicata' : 'Pagamento') },
        { titulo: 'Descrição', valor: (p) => `${UI.escapar(p.descricao || '-')}${
          p.numero ? ` <span class="mini">nº ${UI.escapar(p.numero)}</span>` : ''}` },
        { titulo: 'Vencimento', classe: 'centro', valor: (p) => UI.data(p.vencimento) || '-' },
        { titulo: 'Valor', classe: 'num', valor: (p) => UI.moeda(p.valor) },
      ],
      linhas: pagamentos,
    }) : '<div class="vazio">A nota não informou formas de pagamento nem duplicatas.</div>';

    const eventos = (dados.eventos || []).map((e) => `<li class="mini">${UI.data(e.data_emissao)} —
      ${UI.escapar(e.natureza_operacao || e.esquema || 'evento')}</li>`).join('');

    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <div class="grade g3" style="margin-bottom:14px">
        <div class="kpi"><div class="kpi-rotulo">Nota</div>
          <div class="kpi-valor">${UI.escapar(n.numero || '-')}</div>
          <div class="kpi-nota">série ${UI.escapar(n.serie || '-')} · ${UI.data(n.data_emissao)}</div></div>
        <div class="kpi"><div class="kpi-rotulo">Valor total</div>
          <div class="kpi-valor">${UI.moeda(n.valor_total)}</div>
          <div class="kpi-nota">produtos ${UI.moeda(n.valor_produtos)} · ICMS ${UI.moeda(n.valor_icms)}</div></div>
        <div class="kpi"><div class="kpi-rotulo">Situação</div>
          <div class="kpi-valor" style="font-size:17px">${UI.escapar(n.situacao)}</div>
          <div class="kpi-nota">${n.manifestacao ? UI.escapar(n.manifestacao_nome) : 'sem manifestação'}${
            n.manifestacao_em ? ` em ${UI.data(n.manifestacao_em)}` : ''}</div></div>
      </div>

      <div class="cartao" style="margin-bottom:12px"><div class="cartao-corpo">
        <b>${UI.escapar(n.emitente_nome || '-')}</b>
        <div class="mini">${UI.escapar(n.emitente_documento || '')} · IE ${UI.escapar(n.emitente_ie || '-')}
          · ${UI.escapar(n.emitente_uf || '')}</div>
        <div class="mini" style="margin-top:6px">${UI.escapar(n.natureza_operacao || '')}</div>
        <div class="mini" style="margin-top:6px;font-family:monospace">Chave ${UI.escapar(n.chave_formatada || '')}</div>
        ${n.protocolo ? `<div class="mini">Protocolo ${UI.escapar(n.protocolo)}</div>` : ''}
        ${n.resumo ? `<div class="mini" style="margin-top:8px;color:var(--ambar)">
          Esta nota está aqui só como resumo. Dê ciência da operação e busque de novo na
          SEFAZ para receber o XML completo (aí saem a DANFE e a importação).</div>` : ''}
        ${eventos ? `<ul style="margin:8px 0 0;padding-left:18px">${eventos}</ul>` : ''}
      </div></div>

      <h4 style="margin:14px 0 6px">Itens da nota</h4>
      ${linhaItens}
      <h4 style="margin:16px 0 6px">Pagamentos e duplicatas</h4>
      ${linhaPagamentos}`;

    UI.abrirModal({
      titulo: `NF-e ${n.numero || ''} — ${n.emitente_nome || ''}`,
      corpo,
      largo: true,
      botoes: [
        { rotulo: 'Fechar', acao: UI.fecharModal },
        { rotulo: 'Excluir', classe: 'btn-perigo', acao: () => DFe.excluir(n) },
        { rotulo: 'XML', acao: () => DFe.baixarArquivo(n) },
        ...(n.tem_xml ? [{ rotulo: 'DANFE', acao: () => DFe.abrirDanfe(n.id) }] : []),
        { rotulo: 'Manifestar', acao: () => DFe.manifestar(n, dados.manifestacoes) },
        ...(n.tem_xml ? [{ rotulo: n.importada ? 'Importar de novo' : 'Importar',
          classe: 'btn-primario', acao: () => DFe.importar(n) }] : []),
      ],
    });
  },

  async excluir(nota) {
    const ok = await UI.confirmar(
      `Tirar a nota ${nota.numero || ''} de ${nota.emitente_nome || ''} da lista do AgroDock? `
      + 'Isso não apaga nada na SEFAZ — e ela volta se você buscar tudo de novo.',
      'Excluir',
    );
    if (!ok) return;
    try {
      await Api.del(`/api/dfe/notas/${nota.id}`);
      UI.sucesso('Documento removido da lista.');
      DFe.telaDocumentos();
    } catch (e) {
      UI.erro(e.message);
    }
  },

  /* ------------------------------------------------------------ manifestação */
  manifestar(nota, opcoes) {
    const lista = opcoes || [
      { tipo: 'CIENCIA', rotulo: 'Ciência da operação', exige_justificativa: false },
      { tipo: 'CONFIRMADA', rotulo: 'Confirmada', exige_justificativa: false },
      { tipo: 'DESCONHECIDA', rotulo: 'Desconhecida', exige_justificativa: false },
      { tipo: 'NAO_REALIZADA', rotulo: 'Operação não realizada', exige_justificativa: true },
    ];
    const explicacao = {
      CIENCIA: 'Você viu a nota e ainda vai conferir. Depois da ciência a SEFAZ passa a entregar o XML completo.',
      CONFIRMADA: 'A mercadoria/serviço foi mesmo recebida. É o aceite definitivo da operação.',
      DESCONHECIDA: 'A empresa não reconhece esta operação — ninguém comprou nada deste emitente.',
      NAO_REALIZADA: 'A operação foi cancelada, houve devolução total ou a mercadoria não chegou. Exige justificativa.',
    };
    const area = UI.abrirModal({
      titulo: `Manifestação do destinatário — NF-e ${nota.numero || ''}`,
      corpo: `
        <p class="mini" style="margin-top:0">A manifestação vai direto para a SEFAZ e
        <b>não pode ser apagada</b> depois de registrada. Ela fica no histórico da nota.</p>
        <div class="linha-campos">
          ${UI.campo('O que informar à SEFAZ',
            UI.select('tipo', lista.map((m) => ({ valor: m.tipo, rotulo: m.rotulo })),
              nota.manifestacao || 'CIENCIA', { vazio: false }))}
        </div>
        <div class="mini" id="explica-manifesto" style="margin:-4px 0 10px"></div>
        <div class="linha-campos">
          ${UI.campo('Justificativa', '<textarea name="justificativa" rows="3" placeholder="mínimo de 15 letras"></textarea>')}
        </div>
        ${nota.manifestacao ? `<div class="mini">Esta nota já foi manifestada como
          <b>${UI.escapar(nota.manifestacao_nome)}</b>. Enviar outra manifestação é permitido,
          mas a SEFAZ registra as duas.</div>` : ''}`,
      botoes: [
        { rotulo: 'Cancelar', acao: () => DFe.ficha(nota.id) },
        {
          rotulo: 'Enviar à SEFAZ',
          classe: 'btn-primario',
          acao: async (corpo) => {
            const dados = UI.lerFormulario(corpo);
            const escolha = lista.find((m) => m.tipo === dados.tipo) || {};
            if (escolha.exige_justificativa && (dados.justificativa || '').trim().length < 15) {
              return UI.erro('Escreva a justificativa com pelo menos 15 letras.');
            }
            UI.trocarBotoes([{ rotulo: 'Enviando à SEFAZ...', acao: () => {} }], corpo);
            try {
              const r = await Api.post(`/api/dfe/notas/${nota.id}/manifestar`, {
                empresa_id: Estado.empresaId,
                tipo: dados.tipo,
                justificativa: dados.justificativa || '',
              });
              UI.fecharModal();
              UI.sucesso(r.mensagem);
              DFe.telaDocumentos();
            } catch (e) {
              UI.erro(e.message);
              DFe.ficha(nota.id);
            }
          },
        },
      ],
    });

    const seletor = area.querySelector('[name=tipo]');
    const nota_ = area.querySelector('#explica-manifesto');
    const campoJustificativa = area.querySelector('[name=justificativa]').closest('.campo');
    const atualizar = () => {
      nota_.textContent = explicacao[seletor.value] || '';
      const exige = (lista.find((m) => m.tipo === seletor.value) || {}).exige_justificativa;
      campoJustificativa.style.display = exige || seletor.value === 'DESCONHECIDA' ? '' : 'none';
    };
    seletor.onchange = atualizar;
    atualizar();
  },

  /* -------------------------------------------------------------- importação */
  importar(nota) {
    const area = UI.abrirModal({
      titulo: `Importar NF-e ${nota.numero || ''} para o sistema`,
      corpo: `
        <p class="mini" style="margin-top:0">A importação grava os <b>itens</b> e os
        <b>pagamentos/duplicatas</b> da nota, completa o cadastro do
        <b>cliente/fornecedor</b> (IE, endereço, código do município) e o dos
        <b>produtos</b> (NCM, CEST, CFOP, unidade) e, se você quiser, já cria a conta a pagar.</p>
        <div class="linha-campos">
          <label class="campo" style="grid-column:span 2"><span>Cadastros</span>
            <span><input type="checkbox" name="criar_parceiro" checked> Criar/completar o cliente ou fornecedor do emitente</span></label>
          <label class="campo" style="grid-column:span 2"><span>&nbsp;</span>
            <span><input type="checkbox" name="atualizar_produtos" checked> Criar/completar os produtos da nota</span></label>
          <label class="campo" style="grid-column:span 2"><span>Financeiro</span>
            <span><input type="checkbox" name="gerar_titulo"> Gerar a conta a ${
              nota.sentido === 'Entrada' ? 'pagar' : 'receber'} com as parcelas da nota</span></label>
        </div>
        <div id="campos-titulo" class="linha-campos oculto">
          ${UI.campo('Conta contábil', UI.select('conta_contabil_id',
            UI.opcoesContas(['CUSTO', 'DESPESA', 'RECEITA', 'ATIVO']), '', { vazio: 'Usar a conta padrão' }))}
          ${UI.campo('Centro de custo', UI.select('centro_custo_id', UI.opcoesCentros(), '', { vazio: 'Nenhum' }))}
          ${UI.campo('Operação', UI.select('operacao_id', UI.opcoesOperacoes(), '', { vazio: 'Nenhuma' }))}
          ${UI.campo('Vencimento', `<input type="date" name="vencimento" value="">`,
            'usado só se a nota não trouxer duplicatas')}
        </div>`,
      largo: true,
      botoes: [
        { rotulo: 'Cancelar', acao: () => DFe.ficha(nota.id) },
        {
          rotulo: 'Importar',
          classe: 'btn-primario',
          acao: async (corpo) => {
            const dados = UI.lerFormulario(corpo);
            try {
              const r = await Api.post(`/api/dfe/notas/${nota.id}/importar`, {
                empresa_id: Estado.empresaId,
                criar_parceiro: Boolean(dados.criar_parceiro),
                atualizar_produtos: Boolean(dados.atualizar_produtos),
                gerar_titulo: Boolean(dados.gerar_titulo),
                conta_contabil_id: dados.conta_contabil_id || null,
                centro_custo_id: dados.centro_custo_id || null,
                operacao_id: dados.operacao_id || null,
                vencimento: dados.vencimento || null,
              });
              UI.fecharModal();
              UI.sucesso(r.mensagem);
              await Api.carregarCache(true);
              DFe.telaDocumentos();
            } catch (e) {
              UI.erro(e.message);
            }
          },
        },
      ],
    });
    const marcar = area.querySelector('[name=gerar_titulo]');
    const campos = area.querySelector('#campos-titulo');
    marcar.onchange = () => campos.classList.toggle('oculto', !marcar.checked);
  },

  /* ============================================================= certificado */
  async telaCertificado() {
    const alvo = DFe.alvo();
    const cert = await Api.get('/api/dfe/certificado', { empresa_id: Estado.empresaId });
    const empresa = (Estado.empresas || []).find((e) => e.id === Estado.empresaId) || {};

    alvo.innerHTML = `
      <div class="cartao" style="margin-bottom:16px">
        <div class="cartao-cabecalho"><div>
          <h3>Certificado digital A1</h3>
          <div class="mini">é com ele que o AgroDock se identifica na SEFAZ para baixar as
            notas e enviar a manifestação</div>
        </div></div>
        <div class="cartao-corpo">
          ${cert.configurado ? `
            <div class="grade g3">
              <div class="kpi ${cert.vencido ? 'destaque-vermelho' : 'destaque-verde'}">
                <div class="kpi-rotulo">Titular</div>
                <div class="kpi-valor" style="font-size:16px">${UI.escapar(cert.titular || '-')}</div>
                <div class="kpi-nota">${UI.escapar(cert.cnpj || '')}</div></div>
              <div class="kpi ${cert.vencido ? 'destaque-vermelho' : ''}">
                <div class="kpi-rotulo">Validade</div>
                <div class="kpi-valor" style="font-size:16px">${UI.data(cert.valido_ate)}</div>
                <div class="kpi-nota">${cert.vencido ? 'vencido' : `faltam ${cert.dias_para_vencer} dia(s)`}</div></div>
              <div class="kpi ${cert.ambiente === '2' ? 'destaque-ambar' : 'destaque-azul'}">
                <div class="kpi-rotulo">Ambiente</div>
                <div class="kpi-valor" style="font-size:16px">${UI.escapar(cert.ambiente_nome)}</div>
                <div class="kpi-nota">UF do consulente: ${UI.escapar(cert.uf_autor || '-')}</div></div>
            </div>
            <div class="mini" style="margin-top:12px">
              Arquivo: ${UI.escapar(cert.arquivo_nome || '-')} ·
              Último NSU recebido: ${Number(cert.ultimo_nsu || 0)} de ${Number(cert.max_nsu || 0)}
              ${cert.ultima_consulta ? ` · última busca em ${UI.data(cert.ultima_consulta)}` : ''}
              ${cert.ultima_mensagem ? `<br>Resposta da SEFAZ: ${UI.escapar(cert.ultima_mensagem)}` : ''}
            </div>
            <div class="espaco" style="margin-top:14px">
              <button class="btn btn-perigo" id="btn-remover-cert">Remover certificado</button>
            </div>`
            : `<div class="vazio">Nenhum certificado cadastrado para esta empresa.</div>`}
        </div>
      </div>

      <div class="cartao">
        <div class="cartao-cabecalho"><div>
          <h3>${cert.configurado ? 'Trocar o certificado' : 'Cadastrar o certificado'}</h3>
          <div class="mini">arquivo .pfx ou .p12 (certificado A1). Certificado A3 em cartão ou
            token não funciona em servidor.</div>
        </div></div>
        <div class="cartao-corpo">
          <div class="linha-campos">
            ${UI.campo('Arquivo do certificado (.pfx)', '<input type="file" id="cert-arquivo" accept=".pfx,.p12">')}
            ${UI.campo('Senha do certificado', '<input type="password" id="cert-senha" autocomplete="new-password">')}
            ${UI.campo('Ambiente', UI.select('ambiente', [
              { valor: '1', rotulo: 'Produção (notas reais)' },
              { valor: '2', rotulo: 'Homologação (teste)' },
            ], cert.ambiente || '1', { vazio: false }))}
            ${UI.campo('UF do consulente', UI.select('uf_autor',
              DFe.UFS.map((u) => ({ valor: u, rotulo: u })),
              cert.uf_autor || empresa.uf || '', { vazio: 'Usar a UF da empresa' }))}
          </div>
          <p class="mini">O arquivo é guardado <b>cifrado</b> no banco do sistema e nunca volta
          para a tela — nem o arquivo, nem a senha. Ele é usado só para falar com a SEFAZ.</p>
          <div class="espaco"><button class="btn btn-primario" id="btn-salvar-cert">Salvar certificado</button></div>
        </div>
      </div>`;

    const remover = alvo.querySelector('#btn-remover-cert');
    if (remover) {
      remover.onclick = async () => {
        if (!await UI.confirmar('Remover o certificado desta empresa? Sem ele o sistema não busca mais os documentos na SEFAZ.', 'Remover')) return;
        await Api.del(`/api/dfe/certificado?empresa_id=${Estado.empresaId}`);
        UI.sucesso('Certificado removido.');
        DFe.telaCertificado();
      };
    }

    alvo.querySelector('#btn-salvar-cert').onclick = async () => {
      const arquivo = alvo.querySelector('#cert-arquivo');
      const senha = alvo.querySelector('#cert-senha');
      if (!arquivo.files.length) return UI.erro('Escolha o arquivo do certificado (.pfx).');
      if (!senha.value) return UI.erro('Digite a senha do certificado.');
      const formulario = new FormData();
      formulario.append('empresa_id', Estado.empresaId);
      formulario.append('senha', senha.value);
      formulario.append('ambiente', alvo.querySelector('[name=ambiente]').value);
      formulario.append('uf_autor', alvo.querySelector('[name=uf_autor]').value || '');
      formulario.append('arquivo', arquivo.files[0]);
      try {
        await DFe.enviarFormulario('/api/dfe/certificado', formulario);
        senha.value = '';
        UI.sucesso('Certificado cadastrado. Agora dá para buscar os documentos na SEFAZ.');
        DFe.telaCertificado();
      } catch (e) {
        UI.erro(e.message);
      }
    };
  },
};
