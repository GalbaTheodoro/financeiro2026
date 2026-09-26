/* Folha de impressão do contrato de corretagem.

   Monta uma página A4 completa e independente do sistema (estilo próprio, sem
   depender do CSS do app) e abre numa janela nova já na caixa de impressão do
   navegador — onde dá para escolher "Salvar como PDF". */
const Impressao = {
  /* -------------------------------------------------------------- utilidades */
  esc(v) {
    return String(v ?? '').replace(/[&<>"]/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  },

  moeda(v) {
    return `R$ ${Number(v || 0).toLocaleString('pt-BR', {
      minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  },

  numero(v, casas = 2) {
    return Number(v || 0).toLocaleString('pt-BR', {
      minimumFractionDigits: casas, maximumFractionDigits: casas });
  },

  data(v) {
    if (!v) return '-';
    const d = new Date(`${String(v).slice(0, 10)}T12:00:00`);
    return Number.isNaN(d.getTime()) ? '-' : d.toLocaleDateString('pt-BR');
  },

  dataHora(v) {
    if (!v) return '';
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('pt-BR', {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  },

  /** Valor por extenso em reais — o contrato é documento, ajuda a evitar adulteração. */
  extenso(valor) {
    const n = Math.round(Number(valor || 0) * 100);
    const reais = Math.floor(n / 100);
    const centavos = n % 100;
    const u = ['zero', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove',
      'dez', 'onze', 'doze', 'treze', 'quatorze', 'quinze', 'dezesseis', 'dezessete',
      'dezoito', 'dezenove'];
    const d = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta',
      'oitenta', 'noventa'];
    const c = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos',
      'seiscentos', 'setecentos', 'oitocentos', 'novecentos'];

    const ate999 = (x) => {
      if (x === 0) return '';
      if (x === 100) return 'cem';
      const partes = [];
      const centena = Math.floor(x / 100);
      const resto = x % 100;
      if (centena) partes.push(c[centena]);
      if (resto) {
        if (resto < 20) partes.push(u[resto]);
        else {
          const dez = Math.floor(resto / 10);
          const un = resto % 10;
          partes.push(un ? `${d[dez]} e ${u[un]}` : d[dez]);
        }
      }
      return partes.join(' e ');
    };

    const bloco = (x, singular, plural) => {
      if (!x) return '';
      if (x === 1 && singular === 'mil') return 'mil';
      return `${ate999(x)} ${x === 1 ? singular : plural}`;
    };

    const escrever = (x) => {
      if (x === 0) return 'zero';
      const milhoes = Math.floor(x / 1000000);
      const milhares = Math.floor((x % 1000000) / 1000);
      const resto = x % 1000;
      const grupos = [
        bloco(milhoes, 'milhão', 'milhões'),
        bloco(milhares, 'mil', 'mil'),
        ate999(resto),
      ].filter(Boolean);
      if (grupos.length === 1) return grupos[0];
      // "e" antes do último grupo quando ele é menor que cem ou centena redonda:
      // 435.600 = quatrocentos e trinta e cinco mil E seiscentos
      // 1.320   = mil trezentos e vinte
      const ultimoValor = resto || milhares;
      const ligacao = (ultimoValor < 100 || ultimoValor % 100 === 0) ? ' e ' : ' ';
      const ultimo = grupos.pop();
      return grupos.join(' ') + ligacao + ultimo;
    };

    const unidadeReais = reais === 1
      ? 'real'
      : (reais >= 1000000 && reais % 1000000 === 0 ? 'de reais' : 'reais');
    const texto = [];
    if (reais || !centavos) texto.push(`${escrever(reais)} ${unidadeReais}`);
    if (centavos) texto.push(`${escrever(centavos)} ${centavos === 1 ? 'centavo' : 'centavos'}`);
    return texto.join(' e ');
  },

  /* ------------------------------------------------------------- blocos HTML */
  cabecalho(e) {
    const linhas = [
      e.cnpj ? `CNPJ ${Impressao.esc(e.cnpj)}` : '',
      e.inscricao_estadual ? `IE ${Impressao.esc(e.inscricao_estadual)}` : '',
    ].filter(Boolean).join(' · ');
    const contato = [e.telefone, e.email, e.site].filter(Boolean)
      .map(Impressao.esc).join(' · ');
    return `
      <header class="topo">
        ${e.logo ? `<div class="logo"><img src="${Impressao.esc(e.logo)}" alt=""></div>` : ''}
        <div class="empresa">
          <div class="empresa-nome">${Impressao.esc(e.nome_fantasia || e.razao_social)}</div>
          ${e.nome_fantasia && e.razao_social !== e.nome_fantasia
            ? `<div>${Impressao.esc(e.razao_social)}</div>` : ''}
          ${linhas ? `<div>${linhas}</div>` : ''}
          ${e.endereco ? `<div>${Impressao.esc(e.endereco)}</div>` : ''}
          ${contato ? `<div>${contato}</div>` : ''}
        </div>
      </header>`;
  },

  parte(titulo, p, formas) {
    if (p && p.e_minha_empresa) formas = false;   // a empresa não recebe os próprios dados
    const contato = [p.telefone, p.celular, p.email].filter(Boolean).map(Impressao.esc).join(' · ');
    const pagamento = formas && p.formas && p.formas.length
      ? `<div class="parte-pagamento">
           <span class="rotulo-mini">Dados para pagamento</span>
           ${p.formas.map((f) => `<div>${f.principal ? '<b>' : ''}${Impressao.esc(f.resumo)}${
             f.apelido ? ` <span class="cinza">(${Impressao.esc(f.apelido)})</span>` : ''
           }${f.principal ? '</b>' : ''}</div>`).join('')}
         </div>`
      : '';
    return `
      <div class="parte">
        <div class="parte-titulo">${Impressao.esc(titulo)}</div>
        <div class="parte-nome">${Impressao.esc(p.nome)}</div>
        ${p.nome_fantasia ? `<div>${Impressao.esc(p.nome_fantasia)}</div>` : ''}
        ${p.cpf_cnpj ? `<div><span class="rotulo-mini">${p.pessoa === 'F' ? 'CPF' : 'CNPJ'}</span>
          ${Impressao.esc(p.cpf_cnpj)}${p.rg_ie ? ` · ${Impressao.esc(p.rg_ie)}` : ''}</div>` : ''}
        ${p.endereco ? `<div>${Impressao.esc(p.endereco)}</div>` : ''}
        ${contato ? `<div>${contato}</div>` : ''}
        ${p.contato ? `<div><span class="rotulo-mini">Contato</span>${Impressao.esc(p.contato)}</div>` : ''}
        ${pagamento}
      </div>`;
  },

  celula(rotulo, valor, classe = '') {
    return `<div class="celula ${classe}">
      <span class="rotulo">${Impressao.esc(rotulo)}</span>
      <span class="valor">${valor || '-'}</span>
    </div>`;
  },

  /* ------------------------------------------------------------ folha inteira */
  folha(d) {
    const c = d.contrato;
    const e = d.empresa;
    const un = d.unidade;
    const total = Number(c.comissao_total || 0);

    const pesoUnidade = un && Number(un.peso_conversao)
      ? `${Impressao.numero(un.peso_conversao, 3)} kg por ${Impressao.esc(un.codigo)}` : '';

    const logistica = [
      c.local_coleta ? Impressao.celula('Local de coleta', Impressao.esc(c.local_coleta), 'larga') : '',
      c.local_descarga ? Impressao.celula('Local de descarga', Impressao.esc(c.local_descarga), 'larga') : '',
      c.numero_compra ? Impressao.celula('Nº de compra', Impressao.esc(c.numero_compra)) : '',
      c.numero_venda ? Impressao.celula('Nº de venda', Impressao.esc(c.numero_venda)) : '',
      c.data_embarque ? Impressao.celula('Embarque', Impressao.data(c.data_embarque)) : '',
      c.data_pagamento ? Impressao.celula('Pagamento', Impressao.data(c.data_pagamento)) : '',
    ].filter(Boolean).join('');

    return `
      ${Impressao.cabecalho(e)}

      <div class="titulo-documento">
        <h1>${{ COMPRA: 'Contrato de compra', VENDA: 'Contrato de venda' }[c.tipo]
          || 'Contrato de intermediação'}</h1>
        <div class="numero-contrato">
          <span class="rotulo-mini">Contrato nº</span><b>${Impressao.esc(c.numero)}</b>
          <span class="rotulo-mini">Data</span><b>${Impressao.data(c.data)}</b>
        </div>
      </div>

      <div class="partes">
        ${Impressao.parte(c.tipo === 'COMPRA' ? 'Comprador (nós)' : 'Comprador', d.comprador, true)}
        ${Impressao.parte(c.tipo === 'VENDA' ? 'Vendedor (nós)' : 'Vendedor', d.vendedor, true)}
      </div>
      ${d.agente ? `<div class="partes" style="margin-top:6px">
        ${Impressao.parte('Agente', d.agente, true)}
      </div>` : ''}

      <h2>Objeto do contrato</h2>
      <div class="grade">
        ${Impressao.celula('Mercadoria', Impressao.esc(c.produto_nome || c.produto || ''), 'larga')}
        ${Impressao.celula('Modalidade', Impressao.esc(c.modalidade_nome || c.modalidade || ''))}
        ${Impressao.celula('Embalagem', Impressao.esc(c.embalagem || ''))}
        ${Impressao.celula('Quantidade',
          `${Impressao.numero(c.quantidade, 3)} ${Impressao.esc(c.unidade || '')}`)}
        ${Impressao.celula('Peso total', c.peso_total
          ? `${Impressao.numero(c.peso_total, 3)} kg${pesoUnidade ? `<span class="nota">${pesoUnidade}</span>` : ''}`
          : '-')}
        ${Impressao.celula('Preço unitário', Impressao.moeda(c.preco_unitario))}
        ${Impressao.celula('Diferencial', c.diferencial ? Impressao.moeda(c.diferencial) : '-')}
        ${Impressao.celula('Valor negociado',
          `<b class="destaque">${Impressao.moeda(c.valor_total)}</b>
           <span class="nota">${Impressao.extenso(c.valor_total)}</span>`, 'larga')}
        ${Number(c.icms_percentual) ? Impressao.celula(
          `ICMS${c.icms_regra ? ` (${c.icms_regra})` : ''}`,
          `<b>${Impressao.moeda(c.icms_valor)}</b> · alíquota ${Impressao.numero(c.icms_percentual, 2)}%
           <span class="nota">sobre o valor negociado; valor informativo, não somado ao total</span>`, 'larga') : ''}
      </div>

      ${c.tipo === 'CORRETAGEM' ? `
      <h2>Corretagem</h2>
      <table class="tabela">
        <thead>
          <tr><th>Parte</th><th class="num">Percentual</th><th class="num">Valor da comissão</th></tr>
        </thead>
        <tbody>
          <tr>
            <td>${Impressao.esc(d.comprador.nome)} <span class="cinza">(comprador)</span></td>
            <td class="num">${Impressao.numero(c.comissao_comprador_percentual, 3)}%</td>
            <td class="num">${Impressao.moeda(c.comissao_comprador_valor)}</td>
          </tr>
          <tr>
            <td>${Impressao.esc(d.vendedor.nome)} <span class="cinza">(vendedor)</span></td>
            <td class="num">${Impressao.numero(c.comissao_vendedor_percentual, 3)}%</td>
            <td class="num">${Impressao.moeda(c.comissao_vendedor_valor)}</td>
          </tr>
          ${Number(c.agente_valor) ? `<tr>
            <td>${Impressao.esc(c.agente_nome || '')} <span class="cinza">(agente)</span></td>
            <td class="num">${Impressao.numero(c.agente_percentual, 3)}%</td>
            <td class="num">${Impressao.moeda(c.agente_valor)}</td>
          </tr>` : ''}
        </tbody>
        <tfoot>
          <tr>
            <td>Total da corretagem</td>
            <td class="num">${Impressao.numero(c.percentual_total, 3)}%</td>
            <td class="num"><b>${Impressao.moeda(total)}</b></td>
          </tr>
        </tfoot>
      </table>
      <div class="extenso">${Impressao.extenso(total)}, a pagar
        ${c.data_pagamento ? `em ${Impressao.data(c.data_pagamento)}` : 'conforme combinado'}.</div>
      ` : `
      <h2>${c.tipo === 'COMPRA' ? 'Pagamento' : 'Recebimento'}</h2>
      <table class="tabela">
        <thead>
          <tr><th>Quem</th><th>O que</th><th class="num">Valor</th></tr>
        </thead>
        <tbody>
          <tr>
            <td>${Impressao.esc(c.tipo === 'COMPRA' ? d.vendedor.nome : d.comprador.nome)}
              <span class="cinza">(${c.tipo === 'COMPRA' ? 'fornecedor' : 'cliente'})</span></td>
            <td>${c.tipo === 'COMPRA' ? 'Café comprado' : 'Café vendido'}
              ${c.data_pagamento ? `<span class="cinza">— ${c.tipo === 'COMPRA' ? 'a pagar' : 'a receber'} em ${Impressao.data(c.data_pagamento)}</span>` : ''}</td>
            <td class="num"><b>${Impressao.moeda(c.valor_total)}</b></td>
          </tr>
          ${Number(c.agente_valor) ? `<tr>
            <td>${Impressao.esc(c.agente_nome || '')} <span class="cinza">(agente)</span></td>
            <td>Comissão de ${Impressao.numero(c.agente_percentual, 3)}% sobre o valor do contrato
              <span class="cinza">— a pagar</span></td>
            <td class="num">${Impressao.moeda(c.agente_valor)}</td>
          </tr>` : ''}
        </tbody>
      </table>
      <div class="extenso">${Impressao.extenso(c.valor_total)}${
        Number(c.agente_valor) ? `, mais ${Impressao.extenso(c.agente_valor)} de comissão do agente` : ''}.</div>
      `}

      ${logistica ? `<h2>Embarque e pagamento</h2><div class="grade">${logistica}</div>` : ''}

      ${c.observacao ? `<h2>Observações</h2><p class="texto">${Impressao.esc(c.observacao)}</p>` : ''}
      ${e.texto_contrato ? `<p class="clausulas">${Impressao.esc(e.texto_contrato)}</p>` : ''}

      <div class="assinaturas">
        <div class="assinatura">
          <div class="linha-assinatura"></div>
          <div class="assinatura-nome">${Impressao.esc(d.comprador.nome)}</div>
          <div class="cinza">Comprador</div>
        </div>
        <div class="assinatura">
          <div class="linha-assinatura"></div>
          <div class="assinatura-nome">${Impressao.esc(d.vendedor.nome)}</div>
          <div class="cinza">Vendedor</div>
        </div>
        ${c.tipo === 'CORRETAGEM' ? `<div class="assinatura">
          <div class="linha-assinatura"></div>
          <div class="assinatura-nome">${Impressao.esc(e.nome_fantasia || e.razao_social)}</div>
          <div class="cinza">Interveniente${c.representante_nome
            ? ` · ${Impressao.esc(c.representante_nome)}` : ''}</div>
        </div>` : (d.agente ? `<div class="assinatura">
          <div class="linha-assinatura"></div>
          <div class="assinatura-nome">${Impressao.esc(d.agente.nome)}</div>
          <div class="cinza">Agente</div>
        </div>` : `<div class="assinatura">
          <div class="linha-assinatura"></div>
          <div class="assinatura-nome">${Impressao.esc(c.representante_nome || '')}</div>
          <div class="cinza">Testemunha</div>
        </div>`)}
      </div>

      <footer class="rodape">
        <span>${Impressao.esc(e.cidade || '')}${e.cidade ? ', ' : ''}${Impressao.data(c.data)}</span>
        <span>Contrato ${Impressao.esc(c.numero)} · emitido em ${Impressao.dataHora(d.emitido_em)}</span>
      </footer>`;
  },

  estilo() {
    return `
      @page { size: A4; margin: 14mm 13mm; }
      * { box-sizing: border-box; }
      body { margin:0; font-family: "Segoe UI", Roboto, Arial, sans-serif; font-size: 10pt;
             color:#111827; line-height:1.4; }
      .folha { max-width: 190mm; margin: 0 auto; }
      @media screen { body { background:#e5e7eb; }
        .folha { background:#fff; max-width:210mm; min-height:297mm; padding:14mm 13mm;
                 margin:16px auto; box-shadow:0 2px 14px rgba(0,0,0,.18); } }

      .topo { display:flex; gap:14px; align-items:center; border-bottom:2px solid #111827;
              padding-bottom:8px; margin-bottom:11px; }
      .topo .logo { width:110px; flex-shrink:0; }
      .topo .logo img { max-width:110px; max-height:60px; object-fit:contain; }
      .empresa { font-size:9pt; color:#374151; line-height:1.4; }
      .empresa-nome { font-size:13pt; font-weight:700; color:#111827; letter-spacing:.2px; }

      .titulo-documento { display:flex; justify-content:space-between; align-items:flex-end;
                          margin-bottom:9px; gap:16px; }
      h1 { font-size:15pt; margin:0; text-transform:uppercase; letter-spacing:.6px; }
      .numero-contrato { text-align:right; font-size:10pt; white-space:nowrap; }
      .numero-contrato b { margin-right:12px; }
      h2 { font-size:9pt; text-transform:uppercase; letter-spacing:1px; color:#6b7280;
           margin:9px 0 5px; border-bottom:1px solid #d1d5db; padding-bottom:3px; }

      .partes { display:flex; gap:10px; }
      .parte { flex:1; border:1px solid #d1d5db; border-radius:5px; padding:7px 9px; font-size:9pt;
               line-height:1.4; }
      .parte-titulo { font-size:8pt; text-transform:uppercase; letter-spacing:1px; color:#6b7280;
                      margin-bottom:3px; }
      .parte-nome { font-size:11pt; font-weight:700; line-height:1.25; }
      .parte-pagamento { margin-top:6px; padding-top:5px; border-top:1px dashed #d1d5db; }
      .rotulo-mini { color:#6b7280; margin-right:5px; }

      .grade { display:flex; flex-wrap:wrap; gap:1px; background:#e5e7eb; border:1px solid #e5e7eb;
               border-radius:5px; overflow:hidden; }
      .celula { background:#fff; padding:5px 9px; flex:1 1 22%; min-width:110px; }
      .celula.larga { flex:1 1 46%; }
      .celula .rotulo { display:block; font-size:7.5pt; text-transform:uppercase; letter-spacing:.6px;
                        color:#6b7280; }
      .celula .valor { font-size:10pt; }
      .destaque { font-size:12.5pt; }
      .nota { display:block; font-size:8pt; color:#6b7280; }

      .tabela { width:100%; border-collapse:collapse; font-size:10pt; }
      .tabela th { text-align:left; font-size:8pt; text-transform:uppercase; letter-spacing:.6px;
                   color:#6b7280; border-bottom:1px solid #111827; padding:4px 7px; }
      .tabela td { padding:5px 7px; border-bottom:1px solid #e5e7eb; }
      .tabela tfoot td { border-top:1.5px solid #111827; border-bottom:none; font-weight:600; }
      .num { text-align:right; white-space:nowrap; }
      .cinza { color:#6b7280; }
      .extenso { font-size:9pt; color:#374151; margin-top:5px; font-style:italic; }

      .texto, .clausulas { font-size:9.5pt; text-align:justify; margin:6px 0 0;
                           white-space:pre-wrap; }
      .clausulas { margin-top:10px; color:#374151; }

      .assinaturas { display:flex; gap:16px; margin-top:22px; page-break-inside:avoid; }
      .assinatura { flex:1; text-align:center; font-size:9pt; }
      .linha-assinatura { border-top:1px solid #111827; margin-bottom:5px; }
      .assinatura-nome { font-weight:600; }

      .rodape { display:flex; justify-content:space-between; margin-top:14px; padding-top:5px;
                border-top:1px solid #e5e7eb; font-size:8pt; color:#6b7280; }

      .barra-tela { max-width:210mm; margin:16px auto 0; display:flex; gap:8px; justify-content:flex-end; }
      .barra-tela button { font:inherit; font-size:13px; padding:9px 16px; border-radius:8px;
                           border:1px solid #d1d5db; background:#fff; cursor:pointer; }
      .barra-tela button.principal { background:#1d4ed8; border-color:#1d4ed8; color:#fff;
                                     font-weight:600; }
      @media print { .barra-tela { display:none; } }`;
  },

  /* ------------------------------------------- pedido de venda / orçamento */
  /** A folha que o cliente leva: itens, total, condição de pagamento e parcelas. */
  folhaPedido(d) {
    const p = d.pedido;
    const orcamento = p.tipo === 'ORCAMENTO';
    const cliente = d.cliente;

    const linhas = p.itens.map((i, pos) => `
      <tr>
        <td class="cinza">${pos + 1}</td>
        <td>${Impressao.esc(i.descricao)}</td>
        <td class="num">${Impressao.numero(i.quantidade, 0)} ${Impressao.esc(i.unidade || '')}</td>
        <td class="num">${Impressao.moeda(i.valor_unitario)}</td>
        <td class="num">${i.desconto ? Impressao.moeda(i.desconto) : '-'}</td>
        <td class="num">${Impressao.moeda(i.valor_total)}</td>
      </tr>`).join('');

    /* As parcelas vêm do título quando o pedido já virou venda — o papel do
       cliente tem de dizer os mesmos vencimentos que estão em Contas a Receber. */
    const parcelas = (d.parcelas || []).length ? `
      <h2>Parcelas</h2>
      <table class="tabela">
        <thead><tr><th>Parcela</th><th>Vencimento</th><th class="num">Valor</th></tr></thead>
        <tbody>${d.parcelas.map((x) => `<tr>
          <td>${Impressao.esc(x.numero)}</td>
          <td>${Impressao.data(x.vencimento)}</td>
          <td class="num">${Impressao.moeda(x.valor)}</td></tr>`).join('')}
        </tbody>
        <tfoot><tr><td colspan="2">Total</td>
          <td class="num">${Impressao.moeda(
            d.parcelas.reduce((s, x) => s + Number(x.valor || 0), 0))}</td></tr></tfoot>
      </table>` : '';

    const pagamento = p.condicao ? `
      <h2>Pagamento</h2>
      <div class="grade">
        ${Impressao.celula('Condição', Impressao.esc(p.condicao_rotulo))}
        ${p.parcelas > 1 ? Impressao.celula('Parcelas', `${p.parcelas}x`) : ''}
        ${p.documento_rotulo
          ? Impressao.celula('Documento fiscal', Impressao.esc(p.documento_rotulo)) : ''}
        ${p.nota_numero ? Impressao.celula('Nº do documento', Impressao.esc(p.nota_numero)) : ''}
      </div>` : '';

    return `
      ${Impressao.cabecalho(d.empresa)}

      <div class="titulo-documento">
        <h1>${orcamento ? 'Orçamento' : 'Pedido de venda'}</h1>
        <div class="numero-contrato">
          <span class="rotulo-mini">Nº</span><b>${Impressao.esc(p.numero)}</b>
          <span class="rotulo-mini">Data</span><b>${Impressao.data(p.data)}</b>
        </div>
      </div>

      <div class="partes">
        <div class="parte">
          <div class="parte-titulo">Cliente</div>
          <div class="parte-nome">${Impressao.esc(
            (cliente && cliente.nome) || 'Consumidor não identificado')}</div>
          ${cliente && cliente.cpf_cnpj
            ? `<div><span class="rotulo-mini">CPF/CNPJ</span>${Impressao.esc(cliente.cpf_cnpj)}</div>`
            : ''}
          ${cliente && cliente.endereco ? `<div>${Impressao.esc(cliente.endereco)}</div>` : ''}
          ${cliente && cliente.telefone ? `<div>${Impressao.esc(cliente.telefone)}</div>` : ''}
        </div>
      </div>

      <h2>Itens</h2>
      <table class="tabela">
        <thead><tr>
          <th>#</th><th>Descrição</th><th class="num">Qtd.</th>
          <th class="num">Valor unit.</th><th class="num">Desconto</th><th class="num">Total</th>
        </tr></thead>
        <tbody>${linhas}</tbody>
        <tfoot>
          <tr><td colspan="5">Subtotal</td>
            <td class="num">${Impressao.moeda(p.valor_produtos)}</td></tr>
          ${p.desconto ? `<tr><td colspan="5">Desconto</td>
            <td class="num">− ${Impressao.moeda(p.desconto)}</td></tr>` : ''}
          <tr><td colspan="5"><b>Total</b></td>
            <td class="num destaque"><b>${Impressao.moeda(p.valor_total)}</b></td></tr>
        </tfoot>
      </table>
      <div class="extenso">${Impressao.esc(Impressao.extenso(p.valor_total))}</div>

      ${pagamento}
      ${parcelas}

      ${p.observacao ? `<h2>Observação</h2><p class="texto">${Impressao.esc(p.observacao)}</p>` : ''}

      ${orcamento ? `<p class="texto" style="margin-top:10px">
        ${p.validade
          ? `Este orçamento é válido até <b>${Impressao.data(p.validade)}</b>.`
          : 'Orçamento sujeito a confirmação de preço e disponibilidade.'}
        Este documento <b>não tem valor fiscal</b>.</p>` : `
        <p class="texto" style="margin-top:10px">Este documento não tem valor fiscal —
        ${p.documento_rotulo
          ? `o documento fiscal da venda é a ${Impressao.esc(p.documento_rotulo)}.`
          : 'o documento fiscal é emitido na finalização da venda.'}</p>`}

      <div class="assinaturas">
        <div class="assinatura"><div class="linha-assinatura"></div>
          <div class="assinatura-nome">${Impressao.esc(
            d.empresa.nome_fantasia || d.empresa.razao_social || '')}</div>
          <div class="cinza">vendedor</div></div>
        <div class="assinatura"><div class="linha-assinatura"></div>
          <div class="assinatura-nome">${Impressao.esc(
            (cliente && cliente.nome) || 'Cliente')}</div>
          <div class="cinza">de acordo</div></div>
      </div>

      <div class="rodape">
        <span>${Impressao.esc(p.tipo_rotulo)} nº ${Impressao.esc(p.numero)} ·
          ${Impressao.esc(p.situacao_rotulo)}</span>
        <span>Emitido em ${Impressao.dataHora(d.emitido_em)}</span>
      </div>`;
  },

  async pedido(id) {
    let dados;
    try {
      dados = await Api.get(`/api/pedidos/${id}/impressao`);
    } catch (e) {
      return UI.erro(e.message);
    }
    const p = dados.pedido;
    Impressao.abrirFolha(
      `${p.tipo === 'ORCAMENTO' ? 'Orçamento' : 'Pedido'} ${p.numero}`,
      Impressao.folhaPedido(dados));
  },

  /** Abre a janela de impressão com a folha pronta. */
  abrirFolha(titulo, conteudo) {
    const janela = window.open('', '_blank');
    if (!janela) {
      return UI.erro('O navegador bloqueou a janela de impressão. '
        + 'Libere as janelas pop-up para este endereço e tente de novo.');
    }
    janela.document.write(`<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>${Impressao.esc(titulo)}</title>
<style>${Impressao.estilo()}</style>
</head><body>
<div class="barra-tela">
  <button onclick="window.close()">Fechar</button>
  <button class="principal" onclick="window.print()">Imprimir / Salvar em PDF</button>
</div>
<div class="folha">${conteudo}</div>
</body></html>`);
    janela.document.close();
    janela.focus();
    setTimeout(() => {
      try { janela.print(); } catch { /* o usuário pode imprimir pelo botão */ }
    }, 400);
    return null;
  },

  /* ------------------------------------------------------------------ abrir */
  async contrato(id) {
    let dados;
    try {
      dados = await Api.get(`/api/contratos/${id}/impressao`);
    } catch (e) {
      return UI.erro(e.message);
    }

    const janela = window.open('', '_blank');
    if (!janela) {
      return UI.erro('O navegador bloqueou a janela de impressão. '
        + 'Libere as janelas pop-up para este endereço e tente de novo.');
    }

    const titulo = `${dados.contrato.tipo_nome || 'Contrato'} ${dados.contrato.numero}`;
    janela.document.write(`<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>${Impressao.esc(titulo)}</title>
<style>${Impressao.estilo()}</style>
</head><body>
<div class="barra-tela">
  <button onclick="window.close()">Fechar</button>
  <button class="principal" onclick="window.print()">Imprimir / Salvar em PDF</button>
</div>
<div class="folha">${Impressao.folha(dados)}</div>
</body></html>`);
    janela.document.close();
    janela.focus();
    /* espera o logotipo carregar antes de chamar a impressão */
    setTimeout(() => {
      try { janela.print(); } catch { /* o usuário pode imprimir pelo botão */ }
    }, 400);
  },
};
