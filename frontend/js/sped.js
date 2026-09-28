/* SPED Fiscal — o arquivo mensal da EFD ICMS/IPI para o contador.

   A tela segue a ordem de quem faz isso todo mês: escolhe o mês, **confere**,
   conserta o que apareceu, e só então baixa. O botão de baixar fica desligado
   enquanto houver impedimento — descobrir no PVA que a nota não tinha CFOP é
   descobrir tarde.

   Nada aqui é digitado: o arquivo é montado das notas que já estão no sistema
   (as importadas da SEFAZ, as NF-e emitidas e os cupons fiscais). */
const Sped = {
  _aba: 'gerar',
  _mes: '',
  _conferencia: null,
  _previa: null,
  _config: null,
  _inventario: false,
  _perfil: '',
  _finalidade: '0',

  MESES: ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho',
    'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'],

  /* O mês de referência é o anterior ao de hoje: em março se entrega fevereiro. */
  mesPadrao() {
    const hoje = new Date();
    const d = new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  },

  primeiroDia() {
    return `${Sped._mes || Sped.mesPadrao()}-01`;
  },

  rotuloDoMes() {
    const [ano, mes] = (Sped._mes || Sped.mesPadrao()).split('-');
    return `${Sped.MESES[Number(mes) - 1]} de ${ano}`;
  },

  /* ------------------------------------------------------------------ tela */
  async tela(aba) {
    if (aba) Sped._aba = aba;
    if (!Sped._mes) Sped._mes = Sped.mesPadrao();
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';
    try {
      Sped._config = (await Api.get('/api/sped/config', { empresa_id: Estado.empresaId }));
      if (!Sped._perfil) Sped._perfil = Sped._config.config.perfil || 'A';
      if (Sped._aba === 'gerar') await Sped.conferir(false);
      else Sped.desenhar();
    } catch (e) {
      alvo.innerHTML = `<div class="cartao"><div class="vazio">${UI.escapar(e.message)}</div></div>`;
    }
  },

  async conferir(redesenhar = true) {
    Sped._conferencia = await Api.get('/api/sped/conferir', {
      empresa_id: Estado.empresaId, de: Sped.primeiroDia(),
    });
    Sped._previa = null;
    if (redesenhar !== false) Sped.desenhar();
    else Sped.desenhar();
  },

  desenhar() {
    document.getElementById('pagina').innerHTML = `
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>SPED Fiscal — EFD ICMS/IPI</h3>
            <div class="mini">o arquivo do mês, montado das notas importadas, das NF-e
              emitidas e dos cupons fiscais. Quem valida, assina e transmite é o
              contador, no PVA.</div></div>
        </div>
        <div class="cartao-corpo">
          <div class="abas">
            <button class="aba ${Sped._aba === 'gerar' ? 'ativa' : ''}" data-aba="gerar">Gerar o arquivo</button>
            <button class="aba ${Sped._aba === 'config' ? 'ativa' : ''}" data-aba="config">Configuração</button>
          </div>
          ${Sped._aba === 'gerar' ? Sped.telaGerar() : Sped.telaConfig()}
        </div>
      </div>`;
    Sped.ligar();
  },

  /* ----------------------------------------------------------- gerar o mês */
  telaGerar() {
    const c = Sped._conferencia;
    if (!c) return '<div class="vazio">Escolha o mês e clique em Conferir.</div>';
    const n = c.notas || {};
    return `
      <div class="linha-campos" data-nao-suja>
        ${UI.campo('Mês de referência',
          `<input type="month" name="mes" value="${Sped._mes}">`,
          'a EFD é um arquivo por mês')}
        ${UI.campo('Perfil', UI.select('perfil',
          Object.keys(Sped._config.perfis).map((p) => ({ valor: p, rotulo: `Perfil ${p}` })),
          Sped._perfil), 'o padrão está na aba Configuração')}
        ${UI.campo('Finalidade', UI.select('finalidade', [
          { valor: '0', rotulo: 'Original — primeira entrega do mês' },
          { valor: '1', rotulo: 'Substituto — reenvio do mês' },
        ], Sped._finalidade))}
        <label class="campo">Inventário
          <span class="espaco" style="margin-top:6px">
            <input type="checkbox" name="inventario" ${Sped._inventario ? 'checked' : ''}>
            <span class="mini">incluir o bloco H</span>
          </span>
        </label>
      </div>

      <div class="grade g4" style="margin:12px 0">
        ${Sped.cartao('Saídas', n.saidas, 'NF-e e cupons emitidos', 'azul')}
        ${Sped.cartao('Entradas', n.entradas, 'notas importadas da SEFAZ', 'azul')}
        ${Sped.cartao('Cupons fiscais', n.cupons, 'modelo 65, dentro das saídas')}
        ${Sped.cartao('Canceladas', n.canceladas, 'entram só com o cabeçalho',
          n.canceladas ? 'ambar' : '')}
      </div>

      ${(c.impedimentos || []).length ? `
        <div class="erro-caixa">
          <b>Falta resolver antes de gerar</b>
          <ul class="lista-simples">${c.impedimentos.map((i) => `<li>${UI.escapar(i)}</li>`).join('')}</ul>
          ${(c.resumos || []).length || (c.sem_itens || []).length ? `
            <button class="btn btn-primario" id="btn-completar" style="margin-top:8px">
              Completar as notas de entrada</button>
            <div class="mini" style="margin-top:6px">dá ciência da operação na SEFAZ, busca os
              documentos de novo e grava os itens das notas que já têm o XML</div>` : ''}
        </div>` : `
        <div class="ok-caixa"><b>Pronto para gerar</b><br>
          nenhuma pendência em ${UI.escapar(Sped.rotuloDoMes())}. O PVA ainda é a palavra
          final — ele valida o que só o estado sabe.</div>`}

      ${(c.avisos || []).length ? `
        <div class="aviso-caixa"><b>Vale conferir</b>
          <ul class="lista-simples">${c.avisos.map((a) => `<li>${UI.escapar(a)}</li>`).join('')}</ul>
        </div>` : ''}

      ${Sped.listaPendencias()}

      <div class="espaco" style="margin-top:12px">
        <button class="btn" id="btn-conferir">Conferir de novo</button>
        <button class="btn" id="btn-previa">Ver a prévia</button>
        <button class="btn btn-primario" id="btn-baixar" ${c.pode_gerar ? '' : 'disabled'}>
          Baixar o arquivo (.txt)</button>
        ${c.pode_gerar ? '' : `<button class="btn btn-mini" id="btn-forcar">
          Baixar assim mesmo</button>`}
      </div>
      <div class="mini" style="margin-top:6px">leiaute ${UI.escapar(c.versao || '')} ·
        ${UI.escapar(Sped.rotuloDoMes())} · o arquivo sai em ISO-8859-1, como o PVA espera</div>

      ${Sped._previa ? Sped.telaPrevia() : ''}`;
  },

  listaPendencias() {
    const c = Sped._conferencia || {};
    const partes = [];
    if ((c.resumos || []).length) {
      partes.push(`<div class="cartao" style="margin-bottom:12px"><div class="cartao-corpo">
        <b>Notas que estão só como resumo</b>
        <div class="mini">a SEFAZ entrega o resumo de toda nota contra o CNPJ, e o XML inteiro
          só depois da ciência da operação. Sem o XML não há itens nem CFOP.</div>
        ${UI.tabela({
          colunas: [
            { titulo: 'Nota', valor: (n) => `<b>${UI.escapar(n.numero || '')}</b>
                <div class="mini">série ${UI.escapar(n.serie || '')}</div>` },
            { titulo: 'Emitente', valor: (n) => UI.escapar(n.emitente || '') },
            { titulo: 'Emissão', valor: (n) => UI.data(n.data) },
            { titulo: 'Manifestação', valor: (n) => n.manifestacao
              ? `<span class="tag">${UI.escapar(n.manifestacao)}</span>`
              : '<span class="mini alerta">sem ciência</span>' },
          ],
          linhas: c.resumos,
        })}</div></div>`);
    }
    if ((c.itens_sem_cfop || []).length) {
      partes.push(`<div class="cartao" style="margin-bottom:12px"><div class="cartao-corpo">
        <b>Itens sem CFOP</b>
        <div class="mini">corrija na tela de Notas Fiscais — o CFOP é a chave do registro
          analítico (C190).</div>
        ${UI.tabela({
          colunas: [
            { titulo: 'Nota', valor: (i) => UI.escapar(i.numero || '') },
            { titulo: 'Item', valor: (i) => UI.escapar(String(i.item || '')) },
            { titulo: 'Descrição', valor: (i) => UI.escapar(i.descricao || '') },
          ],
          linhas: c.itens_sem_cfop,
        })}</div></div>`);
    }
    if ((c.produtos_sem_ncm || []).length) {
      partes.push(`<div class="cartao" style="margin-bottom:12px"><div class="cartao-corpo">
        <b>Produtos sem NCM</b>
        <div class="mini">o registro 0200 sai sem a classificação fiscal:
          ${UI.escapar(c.produtos_sem_ncm.join(', '))}</div></div></div>`);
    }
    return partes.join('');
  },

  telaPrevia() {
    const p = Sped._previa;
    const r = p.resumo || {};
    const contagem = p.contagem || [];
    return `
      <div class="cartao" style="margin-top:12px">
        <div class="cartao-cabecalho"><div><h3>Prévia do arquivo</h3>
          <div class="mini">${UI.escapar(p.nome)} · ${p.linhas} linha(s)</div></div></div>
        <div class="cartao-corpo">
          <div class="grade g4" style="margin-bottom:12px">
            ${Sped.cartao('Valor das saídas', UI.moeda(r.valor_saidas), 'somado no C190')}
            ${Sped.cartao('Valor das entradas', UI.moeda(r.valor_entradas), 'somado no C190')}
            ${Sped.cartao('ICMS a recolher', UI.moeda(r.icms_a_recolher),
              r.simples ? 'zerado: empresa do Simples' : 'débito menos crédito',
              r.icms_a_recolher ? 'ambar' : '')}
            ${Sped.cartao('Saldo credor', UI.moeda(r.saldo_credor), 'transporta para o mês seguinte')}
          </div>
          <div class="mini" style="margin-bottom:8px">
            ${r.participantes} participante(s) no 0150 · ${r.itens} item(ns) no 0200
            ${r.inventariados ? ` · ${r.inventariados} linha(s) de inventário` : ''}
          </div>
          <div class="linha-campos">
            <div style="flex:1;min-width:280px">
              <b class="mini">Registros no arquivo</b>
              ${UI.tabela({
                colunas: [
                  { titulo: 'Registro', valor: (l) => `<code>${UI.escapar(l[0])}</code>` },
                  { titulo: 'Linhas', classe: 'direita', valor: (l) => String(l[1]) },
                ],
                linhas: contagem,
              })}
            </div>
            <div style="flex:2;min-width:320px">
              <b class="mini">Começo do arquivo</b>
              <pre class="bloco-codigo">${UI.escapar((p.primeiras || []).join('\n'))}</pre>
              <b class="mini">Fim do arquivo</b>
              <pre class="bloco-codigo">${UI.escapar((p.ultimas || []).join('\n'))}</pre>
            </div>
          </div>
        </div>
      </div>`;
  },

  cartao(titulo, valor, dica, cor = '') {
    return `<div class="kpi ${cor ? `destaque-${cor}` : ''}">
      <div class="kpi-rotulo">${UI.escapar(titulo)}</div>
      <div class="kpi-valor" ${cor ? `style="color:var(--${cor})"` : ''}>${
        typeof valor === 'string' ? UI.escapar(valor) : Number(valor || 0)}</div>
      <div class="kpi-nota">${UI.escapar(dica)}</div></div>`;
  },

  /* ---------------------------------------------------------- configuração */
  telaConfig() {
    const c = Sped._config.config || {};
    const csosn = Object.entries(Sped._config.csosn_padrao || {})
      .map(([de, para]) => `${de} → ${para}`).join(' · ');
    return `
      <form id="form-sped">
        <div class="mini" style="margin-bottom:10px">Isto é o que o SPED pede da empresa e não
          cabe no cadastro dela. O resto — razão social, CNPJ, inscrição estadual, código do
          município — sai de Cadastros → Empresas.</div>

        <div class="linha-campos">
          ${UI.campo('Perfil do arquivo', UI.select('perfil',
            Object.entries(Sped._config.perfis).map(([v, r]) => ({ valor: v, rotulo: r })),
            c.perfil || 'A'), 'quem diz qual é o seu contador')}
          ${UI.campo('Atividade', UI.select('atividade', [
            { valor: '1', rotulo: 'Outros — comércio, serviço' },
            { valor: '0', rotulo: 'Industrial ou equiparado a industrial' },
          ], c.atividade || '1'))}
        </div>

        <h4 style="margin:14px 0 4px">Contabilista (registro 0100)</h4>
        <div class="mini" style="margin-bottom:8px">Quem assina a escrituração — o escritório,
          não o dono da empresa.</div>
        <div class="linha-campos">
          ${UI.campo('Nome', `<input name="contador_nome" value="${UI.escapar(c.contador_nome || '')}">`)}
          ${UI.campo('CPF', `<input name="contador_cpf" value="${UI.escapar(c.contador_cpf || '')}">`)}
          ${UI.campo('CRC', `<input name="contador_crc" value="${UI.escapar(c.contador_crc || '')}">`)}
          ${UI.campo('CNPJ do escritório', `<input name="contador_cnpj" value="${UI.escapar(c.contador_cnpj || '')}">`)}
        </div>
        <div class="linha-campos">
          ${UI.campo('CEP', `<input name="contador_cep" value="${UI.escapar(c.contador_cep || '')}">`)}
          ${UI.campo('Logradouro', `<input name="contador_logradouro" value="${UI.escapar(c.contador_logradouro || '')}">`)}
          ${UI.campo('Número', `<input name="contador_numero" value="${UI.escapar(c.contador_numero || '')}">`)}
          ${UI.campo('Complemento', `<input name="contador_complemento" value="${UI.escapar(c.contador_complemento || '')}">`)}
        </div>
        <div class="linha-campos">
          ${UI.campo('Bairro', `<input name="contador_bairro" value="${UI.escapar(c.contador_bairro || '')}">`)}
          ${UI.campo('Telefone', `<input name="contador_telefone" value="${UI.escapar(c.contador_telefone || '')}">`)}
          ${UI.campo('E-mail', `<input name="contador_email" value="${UI.escapar(c.contador_email || '')}">`)}
          ${UI.campo('Código do município (IBGE)',
            `<input name="contador_codigo_municipio" value="${UI.escapar(c.contador_codigo_municipio || '')}">`)}
        </div>

        <h4 style="margin:14px 0 4px">De/para CSOSN → CST</h4>
        <div class="mini" style="margin-bottom:8px">Só serve para empresa do Simples Nacional: o
          item da nota leva CSOSN (102, 500...) e o SPED Fiscal só conhece a tabela de CST.
          Em branco usa o padrão do sistema, que é o conservador —
          ${UI.escapar(csosn)}. Para mudar, escreva no formato <code>102=20;500=60</code>.</div>
        ${UI.campo('De/para',
          `<input name="csosn_para_cst" value="${UI.escapar(c.csosn_para_cst || '')}"
             placeholder="102=20;500=60">`)}

        <h4 style="margin:14px 0 4px">Itens das notas de saída</h4>
        <label class="campo" style="max-width:none">
          <span class="espaco">
            <input type="checkbox" name="itens_das_saidas" ${c.itens_das_saidas ? 'checked' : ''}>
            <span>Escriturar o item (C170) também nas notas que a empresa emitiu</span>
          </span>
        </label>
        <div class="mini">O Guia Prático manda <b>não</b> informar o item da NF-e de emissão
          própria — a SEFAZ já tem o XML inteiro da nota —, "exceto nos casos previstos na
          legislação estadual". Alguns estados preveem. Deixe desligado a menos que o seu
          contador peça. No cupom fiscal (modelo 65) o item nunca entra, marcado ou não.</div>

        <div class="espaco" style="margin-top:14px">
          <button type="submit" class="btn btn-primario">Salvar</button>
        </div>
      </form>`;
  },

  /* ---------------------------------------------------------------- ações */
  ligar() {
    const pagina = document.getElementById('pagina');
    pagina.querySelectorAll('[data-aba]').forEach((b) => {
      b.onclick = () => Sped.tela(b.dataset.aba);
    });

    const mes = pagina.querySelector('[name=mes]');
    if (mes) {
      mes.onchange = () => {
        Sped._mes = mes.value || Sped.mesPadrao();
        Sped.conferir();
      };
    }
    const perfil = pagina.querySelector('.linha-campos [name=perfil]');
    if (perfil && Sped._aba === 'gerar') {
      perfil.onchange = () => { Sped._perfil = perfil.value; Sped._previa = null; };
    }
    const finalidade = pagina.querySelector('[name=finalidade]');
    if (finalidade) finalidade.onchange = () => { Sped._finalidade = finalidade.value; };
    const inventario = pagina.querySelector('[name=inventario]');
    if (inventario) {
      inventario.onchange = () => { Sped._inventario = inventario.checked; Sped._previa = null; };
    }

    const botao = (id, acao) => {
      const b = pagina.querySelector(`#${id}`);
      if (b) b.onclick = acao;
    };
    botao('btn-conferir', () => Sped.conferir());
    botao('btn-previa', () => Sped.verPrevia());
    botao('btn-baixar', () => Sped.baixar(false));
    botao('btn-forcar', () => Sped.baixar(true));
    botao('btn-completar', () => Sped.completar());

    const form = pagina.querySelector('#form-sped');
    if (form) {
      form.onsubmit = async (e) => {
        e.preventDefault();
        try {
          const dados = UI.lerFormulario(form);
          const r = await Api.put('/api/sped/config',
            { empresa_id: Estado.empresaId, ...dados });
          UI.sucesso(r.mensagem);
          Sped._perfil = r.config.perfil;
          await Sped.tela('config');
        } catch (erro) {
          UI.erro(erro.message);
        }
      };
    }
  },

  async verPrevia() {
    try {
      Sped._previa = await Api.get('/api/sped/previa', {
        empresa_id: Estado.empresaId, de: Sped.primeiroDia(),
        perfil: Sped._perfil, inventario: Sped._inventario,
      });
      Sped.desenhar();
    } catch (e) {
      UI.erro(e.message);
    }
  },

  /** Baixa o .txt levando o token — link direto não passa pela autenticação. */
  async baixar(forcar) {
    const params = new URLSearchParams({
      empresa_id: Estado.empresaId, de: Sped.primeiroDia(),
      perfil: Sped._perfil, finalidade: Sped._finalidade,
    });
    if (Sped._inventario) params.set('inventario', 'true');
    if (forcar) params.set('forcar', 'true');
    try {
      const resposta = await fetch(`/api/sped/arquivo?${params}`, {
        headers: Estado.token ? { Authorization: `Bearer ${Estado.token}` } : {},
      });
      if (!resposta.ok) {
        const corpo = await resposta.json().catch(() => ({}));
        throw new Error(corpo.detail || 'Não foi possível gerar o arquivo.');
      }
      const nome = (resposta.headers.get('Content-Disposition') || '')
        .split('filename=')[1]?.replace(/"/g, '') || 'SPED-FISCAL.txt';
      const blob = await resposta.blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = nome;
      link.click();
      URL.revokeObjectURL(link.href);
      UI.sucesso(`Arquivo de ${Sped.rotuloDoMes()} baixado. Entregue ao contador: `
        + 'é ele que valida no PVA, assina e transmite.');
    } catch (e) {
      UI.erro(e.message);
    }
  },

  async completar() {
    const botao = document.getElementById('btn-completar');
    if (botao) { botao.disabled = true; botao.textContent = 'Completando...'; }
    try {
      const r = await Api.post('/api/sped/completar', {
        empresa_id: Estado.empresaId, de: Sped.primeiroDia(),
      });
      if (r.falhas && r.falhas.length) {
        UI.aviso(`${r.mensagem} Não deu em: ${r.falhas.join(' | ')}`,
          r.faltam ? 'erro' : 'info');
      } else {
        UI.sucesso(r.mensagem);
      }
      await Sped.conferir();
    } catch (e) {
      UI.erro(e.message);
      if (botao) { botao.disabled = false; botao.textContent = 'Completar as notas de entrada'; }
    }
  },
};
