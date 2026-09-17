/* Telas de cadastro (CRUD genérico + telas específicas). */
const Cadastros = {
  /** Onde as telas de cadastro desenham: dentro do hub de abas, se estiver aberto. */
  alvo() {
    return document.getElementById('area-cadastro') || document.getElementById('pagina');
  },

  /* --------------------------------------------------- menu único de cadastros */
  ABAS: [
    { id: 'parceiros', rotulo: 'Clientes/Fornecedores', acao: () => Cadastros.parceiros() },
    { id: 'produtos', rotulo: 'Produtos', acao: () => Cadastros.produtos() },
    { id: 'unidades', rotulo: 'Unidades', acao: () => Cadastros.unidades() },
    { id: 'modalidades', rotulo: 'Modalidades', acao: () => Cadastros.modalidades() },
    { id: 'icms', rotulo: 'ICMS', acao: () => Cadastros.icms() },
    { id: 'bancos', rotulo: 'Bancos', acao: () => Cadastros.bancos() },
    { id: 'centros-custo', rotulo: 'Centros de Custo', acao: () => Cadastros.centrosCusto() },
    { id: 'operacoes', rotulo: 'Operações', acao: () => Cadastros.operacoes() },
    { id: 'plano-contas', rotulo: 'Plano de Contas', acao: () => Cadastros.contasContabeis() },
    { id: 'empresas', rotulo: 'Empresas', acao: () => Cadastros.empresas() },
    { id: 'usuarios', rotulo: 'Usuários', acao: () => Cadastros.usuarios() },
    { id: 'parametros', rotulo: 'Parâmetros contábeis', acao: () => Cadastros.parametros() },
  ],

  async hub(aba) {
    const atual = Cadastros.ABAS.find((a) => a.id === aba) ? aba : 'parceiros';
    Cadastros._aba = atual;
    const pagina = document.getElementById('pagina');
    pagina.innerHTML = `
      <div class="abas">${Cadastros.ABAS
        .map((a) => `<button class="aba ${a.id === atual ? 'ativa' : ''}" data-cad="${a.id}">${a.rotulo}</button>`)
        .join('')}</div>
      <div id="area-cadastro"><div class="cartao"><div class="vazio">Carregando...</div></div></div>`;

    pagina.querySelectorAll('[data-cad]').forEach((b) => {
      b.onclick = () => { location.hash = `#/cadastros/${b.dataset.cad}`; };
    });
    await Cadastros.ABAS.find((a) => a.id === atual).acao();
  },

  /* ---------------------------------------------------------- CRUD genérico */
  async tela(cfg) {
    const alvo = Cadastros.alvo();
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';
    const registros = await cfg.listar();
    Cadastros._registros = registros;

    const cabecalho = `
      <div class="cartao-cabecalho">
        <div>
          <h3>${UI.escapar(cfg.titulo)}</h3>
          <div class="mini">${registros.length} registro(s)${cfg.ajuda ? ' — ' + UI.escapar(cfg.ajuda) : ''}</div>
        </div>
        <div class="espaco">
          <input id="busca-cadastro" placeholder="Filtrar..." style="width:200px">
          ${(cfg.acoesExtras || []).map((a, i) => `<button class="btn" data-extra="${i}">${UI.escapar(a.rotulo)}</button>`).join('')}
          <button class="btn btn-primario" id="btn-novo">+ Novo</button>
        </div>
      </div>`;

    const extras = cfg.acoesLinha || [];
    const colunas = cfg.colunas.concat([
      {
        titulo: 'Ações',
        classe: 'centro',
        valor: (r, i) => `
          ${extras.map((a, j) => `<button class="btn btn-mini ${a.classe || ''}" data-acao="${j}" data-linha="${i}">${UI.escapar(a.rotulo(r))}</button>`).join('')}
          <button class="btn btn-mini" data-editar="${i}">Editar</button>
          <button class="btn btn-mini btn-perigo" data-excluir="${i}">Excluir</button>`,
      },
    ]);

    const desenhar = (lista) => {
      alvo.querySelector('#lista-cadastro').innerHTML = UI.tabela({ colunas, linhas: lista });
      alvo.querySelectorAll('[data-editar]').forEach((b) => {
        b.onclick = () => Cadastros.formulario(cfg, lista[Number(b.dataset.editar)]);
      });
      alvo.querySelectorAll('[data-excluir]').forEach((b) => {
        b.onclick = () => Cadastros.excluir(cfg, lista[Number(b.dataset.excluir)]);
      });
      alvo.querySelectorAll('[data-acao]').forEach((b) => {
        b.onclick = () => extras[Number(b.dataset.acao)].acao(lista[Number(b.dataset.linha)]);
      });
    };

    alvo.innerHTML = `<div class="cartao">${cabecalho}<div class="cartao-corpo sem-padding" id="lista-cadastro"></div></div>`;
    desenhar(registros);

    alvo.querySelector('#btn-novo').onclick = () => Cadastros.formulario(cfg, null);
    alvo.querySelector('#busca-cadastro').oninput = (e) => {
      const termo = e.target.value.toLowerCase();
      desenhar(registros.filter((r) => JSON.stringify(r).toLowerCase().includes(termo)));
    };
    (cfg.acoesExtras || []).forEach((a, i) => {
      const botao = alvo.querySelector(`[data-extra="${i}"]`);
      if (botao) botao.onclick = () => a.acao();
    });
  },

  formulario(cfg, registro) {
    const edicao = Boolean(registro);
    const html = `<div class="linha-campos">${cfg.campos
      .map((campo) => {
        const valor = registro ? registro[campo.nome] : campo.padrao ?? '';
        const estilo = campo.largura === 2 ? 'style="grid-column:span 2"' : '';
        let controle;
        switch (campo.tipo) {
          case 'select':
            controle = UI.select(campo.nome, campo.opcoes(), valor ?? '', {
              obrigatorio: campo.obrigatorio, vazio: campo.vazio,
            });
            break;
          case 'checkbox':
            return `<label class="campo" ${estilo}><span>${UI.escapar(campo.rotulo)}</span>
              <span><input type="checkbox" name="${campo.nome}" ${valor === false ? '' : 'checked'}> ${UI.escapar(campo.textoCheck || 'Sim')}</span></label>`;
          case 'textarea':
            controle = `<textarea name="${campo.nome}" ${campo.linhas ? `rows="${campo.linhas}"` : ''}>${UI.escapar(valor ?? '')}</textarea>`;
            break;
          case 'imagem':
            controle = `
              <div class="campo-imagem" data-imagem="${campo.nome}">
                <div class="imagem-previa">${valor
                  ? `<img src="${UI.escapar(valor)}" alt="logotipo">`
                  : '<span class="mini">sem imagem</span>'}</div>
                <div>
                  <input type="hidden" name="${campo.nome}" value="${UI.escapar(valor ?? '')}">
                  <input type="file" accept="image/png,image/jpeg,image/gif,image/webp">
                  <button type="button" class="btn btn-mini btn-perigo" data-limpar>Remover</button>
                </div>
              </div>`;
            break;
          case 'dinheiro':
            controle = `<input type="number" step="0.01" name="${campo.nome}" value="${valor ?? 0}">`;
            break;
          case 'numero':
            controle = `<input type="number" name="${campo.nome}" value="${valor ?? ''}">`;
            break;
          case 'data':
            controle = `<input type="date" name="${campo.nome}" value="${(valor || '').slice(0, 10)}">`;
            break;
          default:
            controle = `<input type="${campo.tipo || 'text'}" name="${campo.nome}" value="${UI.escapar(valor ?? '')}" ${campo.obrigatorio ? 'required' : ''}>`;
        }
        return `<label class="campo" ${estilo}>${UI.escapar(campo.rotulo)}${campo.dica ? `<span class="dica">${UI.escapar(campo.dica)}</span>` : ''}${controle}</label>`;
      })
      .join('')}</div>`;

    const area = UI.abrirModal({
      titulo: `${edicao ? 'Editar' : 'Novo'} — ${cfg.titulo}`,
      corpo: html,
      largo: cfg.campos.length > 8,
      botoes: [
        { rotulo: 'Cancelar', acao: UI.fecharModal },
        {
          rotulo: 'Salvar',
          classe: 'btn-primario',
          acao: async (corpo) => {
            try {
              const dados = UI.lerFormulario(corpo);
              if (cfg.incluiEmpresa !== false) dados.empresa_id = Estado.empresaId;
              const obrigatorio = cfg.campos.find(
                (c) => c.obrigatorio && (dados[c.nome] === null || dados[c.nome] === ''),
              );
              if (obrigatorio) return UI.erro(`Preencha o campo "${obrigatorio.rotulo}".`);
              const corpoFinal = cfg.montarPayload ? cfg.montarPayload(dados, registro) : dados;
              if (edicao) await Api.put(`${cfg.endpoint}/${registro.id}`, corpoFinal);
              else await Api.post(cfg.endpoint, corpoFinal);
              UI.fecharModal();
              UI.sucesso('Registro salvo.');
              await Api.carregarCache(true);
              App.recarregar();
            } catch (e) {
              UI.erro(e.message);
            }
          },
        },
      ],
    });

    Cadastros.ligarImagens(area);
    if (cfg.aoMontarFormulario) cfg.aoMontarFormulario(area, registro);
  },

  /** Campos de imagem: lê o arquivo escolhido e guarda como data URL no campo oculto. */
  ligarImagens(area) {
    area.querySelectorAll('[data-imagem]').forEach((caixa) => {
      const oculto = caixa.querySelector('input[type=hidden]');
      const arquivo = caixa.querySelector('input[type=file]');
      const previa = caixa.querySelector('.imagem-previa');
      const mostrar = (src) => {
        previa.innerHTML = src
          ? `<img src="${src}" alt="logotipo">`
          : '<span class="mini">sem imagem</span>';
      };
      arquivo.onchange = () => {
        const f = arquivo.files[0];
        if (!f) return;
        if (f.size > 400 * 1024) {
          arquivo.value = '';
          return UI.erro('Imagem muito grande. Use um arquivo de até 400 KB.');
        }
        const leitor = new FileReader();
        leitor.onload = () => { oculto.value = leitor.result; mostrar(leitor.result); };
        leitor.readAsDataURL(f);
      };
      caixa.querySelector('[data-limpar]').onclick = () => {
        oculto.value = '';
        arquivo.value = '';
        mostrar('');
      };
    });
  },

  /* -------------------------------------------- buscas automáticas (CNPJ e CEP) */
  async servicos() {
    if (!Cadastros._servicos) {
      try {
        Cadastros._servicos = await Api.get('/api/consulta/situacao');
      } catch {
        Cadastros._servicos = {
          cnpj: { disponivel: false, descricao: 'consulta indisponível' },
          cep: { disponivel: false, descricao: 'consulta indisponível' },
        };
      }
    }
    return Cadastros._servicos;
  },

  /** Coloca um botão "Buscar" ao lado de um campo do formulário. */
  botaoNoCampo(area, nome) {
    const campo = area.querySelector(`[name=${nome}]`);
    if (!campo || campo.closest('.campo-com-botao')) return null;
    const caixa = document.createElement('div');
    caixa.className = 'campo-com-botao';
    campo.parentNode.insertBefore(caixa, campo);
    caixa.appendChild(campo);
    const botao = document.createElement('button');
    botao.type = 'button';
    botao.className = 'btn btn-primario';
    botao.textContent = 'Buscar';
    caixa.appendChild(botao);
    return { campo, botao, rotulo: campo.closest('label.campo') };
  },

  preencherCampo(area, nome, valor) {
    const alvo = area.querySelector(`[name=${nome}]`);
    if (alvo && valor) alvo.value = valor;
  },

  /* -------------------------------------------- busca do CEP nos Correios */
  async buscaCep(area) {
    const alvo = Cadastros.botaoNoCampo(area, 'cep');
    if (!alvo) return;
    const { campo, botao } = alvo;

    const servico = (await Cadastros.servicos()).cep || {};
    if (!servico.disponivel) {
      botao.disabled = true;
      botao.title = servico.descricao || 'busca de CEP indisponível';
      return;
    }
    campo.placeholder = '00000-000';
    botao.title = servico.descricao;

    const buscar = async (silencioso = false) => {
      const cep = (campo.value || '').replace(/\D/g, '');
      if (cep.length !== 8) {
        if (!silencioso) UI.erro('Digite os 8 dígitos do CEP para buscar.');
        return;
      }
      botao.disabled = true;
      botao.textContent = '...';
      try {
        const d = await Api.get(`/api/consulta/cep/${cep}`);
        campo.value = d.cep || campo.value;
        Cadastros.preencherCampo(area, 'logradouro', d.logradouro);
        Cadastros.preencherCampo(area, 'bairro', d.bairro);
        Cadastros.preencherCampo(area, 'cidade', d.cidade);
        Cadastros.preencherCampo(area, 'uf', d.uf);
        if (d.complemento) Cadastros.preencherCampo(area, 'complemento', d.complemento);
        const numero = area.querySelector('[name=numero]');
        if (numero && !numero.value) numero.focus();
        UI.sucesso(`Endereço encontrado (${d.fonte}).`);
      } catch (e) {
        if (!silencioso) UI.erro(e.message);
      } finally {
        botao.disabled = false;
        botao.textContent = 'Buscar';
      }
    };

    botao.onclick = () => buscar(false);
    campo.onkeydown = (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        buscar(false);
      }
    };
    // busca sozinho quando o CEP é digitado e o endereço ainda está vazio
    campo.onblur = () => {
      const logradouro = area.querySelector('[name=logradouro]');
      if (logradouro && !logradouro.value) buscar(true);
    };
  },

  /* ------------------------------------------- busca do CNPJ na API do governo */
  async buscaCnpj(area) {
    const alvo = Cadastros.botaoNoCampo(area, 'cpf_cnpj');
    if (!alvo) return;
    const { campo, botao, rotulo } = alvo;

    const resultado = document.createElement('div');
    resultado.className = 'resultado-consulta oculto';
    rotulo.parentNode.insertBefore(resultado, rotulo.nextSibling);
    resultado.style.gridColumn = '1 / -1';

    const servico = (await Cadastros.servicos()).cnpj || {};
    if (!servico.disponivel) {
      botao.disabled = true;
      botao.title = servico.descricao;
    } else {
      campo.placeholder = 'digite o CNPJ e clique em Buscar';
      botao.title = servico.descricao;
    }

    const preencher = (nome, valor) => Cadastros.preencherCampo(area, nome, valor);

    const buscar = async () => {
      const cnpj = (campo.value || '').replace(/\D/g, '');
      if (cnpj.length !== 14) {
        return UI.erro('Digite os 14 dígitos do CNPJ para buscar.');
      }
      botao.disabled = true;
      botao.textContent = 'Buscando...';
      resultado.classList.add('oculto');
      try {
        const d = await Api.get(`/api/consulta/cnpj/${cnpj}`);
        campo.value = d.cnpj || campo.value;
        preencher('nome', d.razao_social);
        preencher('nome_fantasia', d.nome_fantasia);
        preencher('logradouro', d.logradouro);
        preencher('numero', d.numero);
        preencher('complemento', d.complemento);
        preencher('bairro', d.bairro);
        preencher('cidade', d.cidade);
        preencher('uf', d.uf);
        preencher('cep', d.cep);
        preencher('telefone', d.telefone);
        preencher('email', d.email);
        const pessoa = area.querySelector('[name=pessoa]');
        if (pessoa) pessoa.value = 'J';

        const inativa = d.situacao && !/ATIVA/i.test(d.situacao);
        resultado.className = `resultado-consulta ${inativa ? 'alerta' : ''}`;
        resultado.style.gridColumn = '1 / -1';
        resultado.innerHTML = `
          <div class="espaco" style="justify-content:space-between">
            <span class="forte">${UI.escapar(d.razao_social || '')}</span>
            ${d.situacao ? `<span class="tag ${inativa ? 'tag-vencido' : 'tag-pago'}">${UI.escapar(d.situacao)}</span>` : ''}
          </div>
          <div class="mini">
            ${[d.natureza_juridica, d.porte, d.data_abertura ? `aberta em ${UI.data(d.data_abertura) || d.data_abertura}` : '']
              .filter(Boolean).map(UI.escapar).join(' · ')}
          </div>
          ${d.cnae_principal ? `<div class="mini">Atividade principal: ${UI.escapar(d.cnae_principal)}</div>` : ''}
          ${d.socios && d.socios.length
            ? `<div class="mini" style="margin-top:6px"><b>Sócios:</b> ${d.socios
                .map((s) => UI.escapar(`${s.nome}${s.qualificacao ? ` (${s.qualificacao})` : ''}`))
                .join(' · ')}</div>`
            : ''}
          <div class="mini" style="margin-top:6px;opacity:.75">Fonte: ${UI.escapar(d.fonte || '')}</div>`;
        resultado.classList.remove('oculto');
        UI.sucesso('Dados carregados. Confira antes de salvar.');
      } catch (e) {
        UI.erro(e.message);
      } finally {
        botao.disabled = false;
        botao.textContent = 'Buscar';
      }
    };

    botao.onclick = buscar;
    campo.onkeydown = (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        buscar();
      }
    };
  },

  async excluir(cfg, registro) {
    const ok = await UI.confirmar(
      `Excluir "${registro.nome || registro.razao_social || registro.codigo || registro.regra}"? Esta ação não pode ser desfeita.`,
      'Excluir',
    );
    if (!ok) return;
    try {
      await Api.del(`${cfg.endpoint}/${registro.id}`);
      UI.sucesso('Registro excluído.');
      await Api.carregarCache(true);
      App.recarregar();
    } catch (e) {
      UI.erro(e.message);
    }
  },

  /* ------------------------------------------------------------- empresas */
  empresas() {
    return Cadastros.tela({
      titulo: 'Empresas',
      endpoint: '/api/empresas',
      incluiEmpresa: false,
      ajuda: 'ao criar uma empresa o plano de contas padrão é gerado automaticamente',
      aoMontarFormulario: (area) => Cadastros.buscaCep(area),
      listar: () => Api.get('/api/empresas'),
      colunas: [
        { titulo: 'Razão social', valor: (r) => UI.escapar(r.razao_social) },
        { titulo: 'Fantasia', valor: (r) => UI.escapar(r.nome_fantasia || '-') },
        { titulo: 'CNPJ', valor: (r) => UI.escapar(r.cnpj || '-') },
        { titulo: 'Cidade/UF', valor: (r) => `${UI.escapar(r.cidade || '-')}/${UI.escapar(r.uf || '')}` },
        { titulo: 'Regime', valor: (r) => UI.escapar(r.regime_tributario || '-') },
        { titulo: 'Situação', classe: 'centro', valor: (r) => (r.ativo ? '<span class="tag tag-pago">Ativa</span>' : '<span class="tag tag-cancelado">Inativa</span>') },
      ],
      campos: [
        { nome: 'razao_social', rotulo: 'Razão social', obrigatorio: true, largura: 2 },
        { nome: 'nome_fantasia', rotulo: 'Nome fantasia' },
        { nome: 'cnpj', rotulo: 'CNPJ' },
        { nome: 'inscricao_estadual', rotulo: 'Inscrição estadual' },
        { nome: 'inscricao_municipal', rotulo: 'Inscrição municipal' },
        {
          nome: 'regime_tributario', rotulo: 'Regime tributário', tipo: 'select', vazio: false,
          opcoes: () => ['SIMPLES NACIONAL', 'LUCRO PRESUMIDO', 'LUCRO REAL', 'MEI', 'TERCEIRO SETOR']
            .map((v) => ({ valor: v, rotulo: v })),
        },
        { nome: 'responsavel', rotulo: 'Responsável' },
        { nome: 'logradouro', rotulo: 'Logradouro', largura: 2 },
        { nome: 'numero', rotulo: 'Número' },
        { nome: 'complemento', rotulo: 'Complemento' },
        { nome: 'bairro', rotulo: 'Bairro' },
        { nome: 'cidade', rotulo: 'Cidade' },
        { nome: 'uf', rotulo: 'UF' },
        { nome: 'cep', rotulo: 'CEP' },
        { nome: 'telefone', rotulo: 'Telefone' },
        { nome: 'email', rotulo: 'E-mail', tipo: 'email' },
        { nome: 'site', rotulo: 'Site' },
        {
          nome: 'logo', rotulo: 'Logotipo', tipo: 'imagem', largura: 2,
          dica: 'aparece no cabeçalho do contrato impresso (PNG ou JPG até 400 KB)',
        },
        {
          nome: 'texto_contrato', rotulo: 'Cláusulas do contrato', tipo: 'textarea',
          largura: 2, linhas: 4,
          dica: 'texto fixo impresso no rodapé do contrato (condições gerais, foro...)',
        },
        { nome: 'ativo', rotulo: 'Situação', tipo: 'checkbox', textoCheck: 'Empresa ativa' },
      ],
    });
  },

  /* --------------------------------------------------- clientes/fornecedores */
  parceiros() {
    return Cadastros.tela({
      titulo: 'Clientes e Fornecedores',
      endpoint: '/api/parceiros',
      ajuda: 'busque pelo CNPJ na Receita Federal e pelo CEP nos Correios',
      aoMontarFormulario: (area) => {
        Cadastros.buscaCnpj(area);
        Cadastros.buscaCep(area);
      },
      listar: () => Api.get('/api/parceiros', { empresa_id: Estado.empresaId }),
      colunas: [
        { titulo: 'Nome / Razão social', valor: (r) => UI.escapar(r.nome) },
        { titulo: 'Tipo', valor: (r) => ({ CLIENTE: 'Cliente', FORNECEDOR: 'Fornecedor', AMBOS: 'Cliente e Fornecedor' }[r.tipo]) },
        { titulo: 'CPF/CNPJ', valor: (r) => UI.escapar(r.cpf_cnpj || '-') },
        { titulo: 'Cidade/UF', valor: (r) => `${UI.escapar(r.cidade || '-')}/${UI.escapar(r.uf || '')}` },
        { titulo: 'Telefone', valor: (r) => UI.escapar(r.telefone || r.celular || '-') },
        {
          titulo: 'Onde pagar',
          valor: (r) => (r.qtd_formas_pagamento
            ? `<div class="mini">${UI.escapar(r.forma_principal || '')}</div>
               ${r.qtd_formas_pagamento > 1 ? `<div class="mini">+ ${r.qtd_formas_pagamento - 1} outra(s)</div>` : ''}`
            : '<span class="mini">não cadastrado</span>'),
        },
        { titulo: 'Situação', classe: 'centro', valor: (r) => (r.ativo ? '<span class="tag tag-pago">Ativo</span>' : '<span class="tag tag-cancelado">Inativo</span>') },
      ],
      acoesLinha: [
        {
          rotulo: (r) => (r.qtd_formas_pagamento
            ? `Pagamento (${r.qtd_formas_pagamento})` : '+ Pagamento'),
          classe: 'btn-verde',
          acao: (r) => Cadastros.formasPagamento(r),
        },
      ],
      campos: [
        {
          nome: 'tipo', rotulo: 'Tipo', tipo: 'select', vazio: false, padrao: 'CLIENTE',
          opcoes: () => [
            { valor: 'CLIENTE', rotulo: 'Cliente' },
            { valor: 'FORNECEDOR', rotulo: 'Fornecedor' },
            { valor: 'AMBOS', rotulo: 'Cliente e Fornecedor' },
          ],
        },
        {
          nome: 'pessoa', rotulo: 'Pessoa', tipo: 'select', vazio: false, padrao: 'J',
          opcoes: () => [{ valor: 'J', rotulo: 'Jurídica' }, { valor: 'F', rotulo: 'Física' }],
        },
        { nome: 'nome', rotulo: 'Nome / Razão social', obrigatorio: true, largura: 2 },
        { nome: 'nome_fantasia', rotulo: 'Nome fantasia' },
        { nome: 'cpf_cnpj', rotulo: 'CPF / CNPJ', largura: 2, dica: 'busca automática pelo CNPJ' },
        { nome: 'rg_ie', rotulo: 'RG / Inscrição estadual' },
        { nome: 'contato', rotulo: 'Pessoa de contato' },
        { nome: 'logradouro', rotulo: 'Logradouro', largura: 2 },
        { nome: 'numero', rotulo: 'Número' },
        { nome: 'complemento', rotulo: 'Complemento' },
        { nome: 'bairro', rotulo: 'Bairro' },
        { nome: 'cidade', rotulo: 'Cidade' },
        { nome: 'uf', rotulo: 'UF' },
        { nome: 'cep', rotulo: 'CEP' },
        { nome: 'telefone', rotulo: 'Telefone' },
        { nome: 'celular', rotulo: 'Celular' },
        { nome: 'email', rotulo: 'E-mail', tipo: 'email' },
        { nome: 'observacao', rotulo: 'Observações', tipo: 'textarea', largura: 2 },
        { nome: 'ativo', rotulo: 'Situação', tipo: 'checkbox', textoCheck: 'Cadastro ativo' },
      ],
    });
  },

  /* ------------------------------- formas de pagamento do cliente/fornecedor */
  async formasPagamento(parceiro) {
    const corpo = document.createElement('div');
    corpo.innerHTML = '<div class="vazio">Carregando...</div>';

    UI.abrirModal({
      titulo: `Onde pagar — ${parceiro.nome}`,
      corpo,
      largo: true,
      botoes: [{ rotulo: 'Fechar', classe: 'btn-primario', acao: () => {
        UI.fecharModal();
        App.recarregar();
      } }],
    });

    const dados = await Api.get(`/api/parceiros/${parceiro.id}/formas-pagamento`);

    const desenhar = () => {
      const cartoes = dados.formas.length
        ? dados.formas.map((f, i) => `
            <div class="forma-cartao ${f.principal ? 'principal' : ''} ${f.ativo ? '' : 'inativa'}">
              <div class="forma-topo">
                <div>
                  <span class="tag ${f.principal ? 'tag-pago' : 'tag-aberto'}">${UI.escapar(f.tipo_nome)}</span>
                  ${f.principal ? '<span class="tag tag-pago">Principal</span>' : ''}
                  ${f.ativo ? '' : '<span class="tag tag-cancelado">Inativa</span>'}
                  ${f.apelido ? `<span class="mini"> ${UI.escapar(f.apelido)}</span>` : ''}
                </div>
                <div class="espaco">
                  ${f.principal || !f.ativo ? '' : `<button class="btn btn-mini" data-principal="${i}">Tornar principal</button>`}
                  <button class="btn btn-mini" data-copiar="${i}">Copiar</button>
                  <button class="btn btn-mini" data-editar-forma="${i}">Editar</button>
                  <button class="btn btn-mini btn-perigo" data-excluir-forma="${i}">Excluir</button>
                </div>
              </div>
              <div class="forma-resumo">${UI.escapar(f.resumo)}</div>
              <div class="mini">
                ${[f.titular ? `Titular: ${f.titular}` : '', f.documento_titular || '', f.observacao || '']
                  .filter(Boolean).map(UI.escapar).join(' · ')}
              </div>
            </div>`).join('')
        : `<div class="vazio">Nenhuma forma de pagamento cadastrada para
             ${UI.escapar(parceiro.nome)}. Cadastre a chave Pix ou a conta bancária.</div>`;

      corpo.innerHTML = `
        <div class="mini" style="margin-bottom:12px">
          Cadastre quantas formas quiser — Pix, contas em bancos diferentes, boleto.
          A marcada como <b>principal</b> aparece sugerida na hora de dar baixa no título.
        </div>
        <div id="lista-formas">${cartoes}</div>
        <div style="margin-top:14px">
          <button class="btn btn-primario" id="btn-nova-forma">+ Nova forma de pagamento</button>
        </div>
        <div id="painel-forma" class="oculto"></div>`;

      corpo.querySelector('#btn-nova-forma').onclick = () => editar(null);
      corpo.querySelectorAll('[data-editar-forma]').forEach((b) => {
        b.onclick = () => editar(dados.formas[Number(b.dataset.editarForma)]);
      });
      corpo.querySelectorAll('[data-principal]').forEach((b) => {
        b.onclick = async () => {
          try {
            await Api.post(`/api/formas-pagamento/${dados.formas[Number(b.dataset.principal)].id}/principal`);
            await recarregar();
            UI.sucesso('Forma principal atualizada.');
          } catch (e) { UI.erro(e.message); }
        };
      });
      corpo.querySelectorAll('[data-copiar]').forEach((b) => {
        b.onclick = async () => {
          const f = dados.formas[Number(b.dataset.copiar)];
          try {
            await navigator.clipboard.writeText(f.texto_copia);
            UI.sucesso('Dados copiados.');
          } catch {
            UI.aviso(f.texto_copia);
          }
        };
      });
      corpo.querySelectorAll('[data-excluir-forma]').forEach((b) => {
        b.onclick = async () => {
          const f = dados.formas[Number(b.dataset.excluirForma)];
          if (!(await UI.confirmar(`Excluir "${f.resumo}"?`, 'Excluir'))) return;
          try {
            await Api.del(`/api/formas-pagamento/${f.id}`);
            await recarregar();
            UI.sucesso('Forma de pagamento excluída.');
          } catch (e) { UI.erro(e.message); }
        };
      });
    };

    const recarregar = async () => {
      const novo = await Api.get(`/api/parceiros/${parceiro.id}/formas-pagamento`);
      dados.formas = novo.formas;
      desenhar();
    };

    const editar = (forma) => {
      const v = (campo) => UI.escapar(forma ? (forma[campo] ?? '') : '');
      const painel = corpo.querySelector('#painel-forma');
      corpo.querySelector('#lista-formas').classList.add('oculto');
      corpo.querySelector('#btn-nova-forma').classList.add('oculto');
      painel.classList.remove('oculto');
      painel.innerHTML = `
        <div class="cartao" style="box-shadow:none;margin:0">
          <div class="cartao-cabecalho"><h3>${forma ? 'Editar' : 'Nova'} forma de pagamento</h3></div>
          <div class="cartao-corpo">
            <div class="linha-campos">
              ${UI.campo('Tipo *', UI.select('tipo', dados.tipos.map((t) => ({ valor: t.valor, rotulo: t.rotulo })),
                forma ? forma.tipo : 'PIX', { vazio: false }))}
              ${UI.campo('Apelido', `<input name="apelido" value="${v('apelido')}" placeholder="ex.: conta principal">`)}
            </div>

            <div class="linha-campos grupo-pix" style="margin-top:10px">
              ${UI.campo('Tipo da chave', UI.select('pix_tipo', dados.tipos_pix, forma ? forma.pix_tipo : '', { vazio: 'Não informado' }))}
              ${UI.campo('Chave Pix *', `<input name="pix_chave" value="${v('pix_chave')}" placeholder="CPF, CNPJ, e-mail, telefone ou chave aleatória">`)}
            </div>

            <div class="linha-campos grupo-banco" style="margin-top:10px">
              ${UI.campo('Código do banco', `<input name="banco_codigo" value="${v('banco_codigo')}" placeholder="001, 341, 237...">`)}
              ${UI.campo('Nome do banco *', `<input name="banco_nome" value="${v('banco_nome')}">`)}
              ${UI.campo('Agência', `<input name="agencia" value="${v('agencia')}">`)}
              ${UI.campo('Operação', `<input name="operacao" value="${v('operacao')}" placeholder="Caixa: 001, 013">`)}
              ${UI.campo('Conta *', `<input name="conta" value="${v('conta')}">`)}
              ${UI.campo('Tipo de conta', UI.select('tipo_conta', [
                { valor: 'CORRENTE', rotulo: 'Conta corrente' },
                { valor: 'POUPANCA', rotulo: 'Poupança' },
                { valor: 'PAGAMENTO', rotulo: 'Conta de pagamento' },
              ], forma ? forma.tipo_conta : 'CORRENTE', { vazio: false }))}
            </div>

            <div class="linha-campos" style="margin-top:10px">
              ${UI.campo('Titular', `<input name="titular" value="${v('titular')}" placeholder="em branco usa o nome do cadastro">`)}
              ${UI.campo('CPF/CNPJ do titular', `<input name="documento_titular" value="${v('documento_titular')}">`)}
              ${UI.campo('Observação', `<input name="observacao" value="${v('observacao')}">`)}
            </div>

            <div class="linha-campos" style="margin-top:10px">
              ${UI.campo('Principal', `<span><input type="checkbox" name="principal" ${forma && forma.principal ? 'checked' : ''}> usar como padrão nos pagamentos</span>`)}
              ${UI.campo('Situação', `<span><input type="checkbox" name="ativo" ${!forma || forma.ativo ? 'checked' : ''}> ativa</span>`)}
            </div>

            <div class="espaco" style="margin-top:14px;justify-content:flex-end">
              <button class="btn" id="btn-cancelar-forma">Cancelar</button>
              <button class="btn btn-primario" id="btn-salvar-forma">Salvar forma</button>
            </div>
          </div>
        </div>`;

      const ajustarCampos = () => {
        const tipo = painel.querySelector('[name=tipo]').value;
        painel.querySelectorAll('.grupo-pix').forEach((g) => g.classList.toggle('oculto', tipo !== 'PIX'));
        painel.querySelectorAll('.grupo-banco').forEach((g) =>
          g.classList.toggle('oculto', !['DEPOSITO', 'TED'].includes(tipo)));
      };
      painel.querySelector('[name=tipo]').onchange = ajustarCampos;
      ajustarCampos();

      painel.querySelector('#btn-cancelar-forma').onclick = () => {
        painel.classList.add('oculto');
        corpo.querySelector('#lista-formas').classList.remove('oculto');
        corpo.querySelector('#btn-nova-forma').classList.remove('oculto');
      };
      painel.querySelector('#btn-salvar-forma').onclick = async () => {
        const d = UI.lerFormulario(painel);
        try {
          if (forma) await Api.put(`/api/formas-pagamento/${forma.id}`, d);
          else await Api.post(`/api/parceiros/${parceiro.id}/formas-pagamento`, d);
          await recarregar();
          UI.sucesso('Forma de pagamento salva.');
        } catch (e) {
          UI.erro(e.message);
        }
      };
    };

    desenhar();
  },

  /* ------------------------------------------- unidades, modalidades, produtos */
  unidades() {
    return Cadastros.tela({
      titulo: 'Unidades de medida',
      endpoint: '/api/unidades',
      ajuda: 'o peso de conversão em quilos permite calcular o peso total do contrato',
      listar: () => Api.get('/api/unidades', { empresa_id: Estado.empresaId }),
      acoesExtras: [],
      colunas: [
        { titulo: 'Código', valor: (r) => `<span class="forte">${UI.escapar(r.codigo)}</span>` },
        { titulo: 'Nome', valor: (r) => UI.escapar(r.nome) },
        { titulo: 'Peso de conversão (kg)', classe: 'num', valor: (r) => (r.peso_conversao ? UI.numero(r.peso_conversao, 3) : '-') },
        { titulo: 'Observação', valor: (r) => UI.escapar(r.observacao || '-') },
        { titulo: 'Situação', classe: 'centro', valor: (r) => (r.ativo ? '<span class="tag tag-pago">Ativa</span>' : '<span class="tag tag-cancelado">Inativa</span>') },
      ],
      campos: [
        { nome: 'codigo', rotulo: 'Código', obrigatorio: true, dica: 'ex.: SC, TON, AR' },
        { nome: 'nome', rotulo: 'Nome', obrigatorio: true, largura: 2 },
        { nome: 'peso_conversao', rotulo: 'Peso de conversão (kg)', tipo: 'dinheiro', padrao: 0,
          dica: 'quantos quilos vale 1 unidade — saca de 60 kg = 60' },
        { nome: 'observacao', rotulo: 'Observação', largura: 2 },
        { nome: 'ativo', rotulo: 'Situação', tipo: 'checkbox', textoCheck: 'Unidade ativa' },
      ],
    });
  },

  modalidades() {
    return Cadastros.tela({
      titulo: 'Modalidades de contrato',
      endpoint: '/api/modalidades',
      ajuda: 'como o negócio foi fechado: disponível, futuro, a fixar, CIF, FOB...',
      listar: () => Api.get('/api/modalidades', { empresa_id: Estado.empresaId }),
      colunas: [
        { titulo: 'Código', valor: (r) => `<span class="forte">${UI.escapar(r.codigo)}</span>` },
        { titulo: 'Nome', valor: (r) => UI.escapar(r.nome) },
        { titulo: 'Descrição', valor: (r) => UI.escapar(r.descricao || '-') },
        { titulo: 'Situação', classe: 'centro', valor: (r) => (r.ativo ? '<span class="tag tag-pago">Ativa</span>' : '<span class="tag tag-cancelado">Inativa</span>') },
      ],
      campos: [
        { nome: 'codigo', rotulo: 'Código', obrigatorio: true },
        { nome: 'nome', rotulo: 'Nome', obrigatorio: true, largura: 2 },
        { nome: 'descricao', rotulo: 'Descrição', largura: 2 },
        { nome: 'ativo', rotulo: 'Situação', tipo: 'checkbox', textoCheck: 'Modalidade ativa' },
      ],
    });
  },

  produtos() {
    return Cadastros.tela({
      titulo: 'Produtos',
      endpoint: '/api/produtos',
      ajuda: 'mercadorias negociadas nos contratos, com a unidade padrão de cada uma',
      listar: () => Api.get('/api/produtos', { empresa_id: Estado.empresaId }),
      colunas: [
        { titulo: 'Código', valor: (r) => `<span class="forte">${UI.escapar(r.codigo)}</span>` },
        { titulo: 'Produto', valor: (r) => UI.escapar(r.nome) },
        { titulo: 'Unidade', valor: (r) => UI.escapar(r.unidade_nome || '-') },
        { titulo: 'Embalagem', valor: (r) => UI.escapar(r.embalagem || '-') },
        { titulo: 'Descrição', valor: (r) => UI.escapar(r.descricao || '-') },
        { titulo: 'Situação', classe: 'centro', valor: (r) => (r.ativo ? '<span class="tag tag-pago">Ativo</span>' : '<span class="tag tag-cancelado">Inativo</span>') },
      ],
      campos: [
        { nome: 'codigo', rotulo: 'Código', obrigatorio: true },
        { nome: 'nome', rotulo: 'Produto', obrigatorio: true, largura: 2 },
        { nome: 'unidade_id', rotulo: 'Unidade padrão', tipo: 'select',
          opcoes: () => (Estado.cache.unidades || []).filter((u) => u.ativo)
            .map((u) => ({ valor: u.id, rotulo: `${u.codigo} — ${u.nome}` })) },
        { nome: 'embalagem', rotulo: 'Embalagem', dica: 'a granel, sacaria...' },
        { nome: 'descricao', rotulo: 'Descrição', largura: 2 },
        { nome: 'ativo', rotulo: 'Situação', tipo: 'checkbox', textoCheck: 'Produto ativo' },
      ],
    });
  },

  /* ------------------------------------------------------------------ ICMS
     Grade UF do vendedor x UF do comprador (x produto) usada no contrato. */
  UFS: ['AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA', 'PB',
    'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO'],

  opcoesUf() {
    return Cadastros.UFS.map((uf) => ({ valor: uf, rotulo: uf }));
  },

  icms() {
    return Cadastros.tela({
      titulo: 'Tabela de ICMS',
      endpoint: '/api/icms',
      ajuda: 'o contrato busca a alíquota pela UF do vendedor e do comprador; a linha de um produto vale antes da linha "todos os produtos"',
      listar: () => Api.get('/api/icms', { empresa_id: Estado.empresaId }),
      acoesExtras: [{ rotulo: 'Gerar alíquotas interestaduais', acao: () => Cadastros.gerarIcmsPadrao() }],
      colunas: [
        { titulo: 'UF vendedor', classe: 'centro', valor: (r) => `<span class="forte">${UI.escapar(r.uf_origem)}</span>` },
        { titulo: '', classe: 'centro', valor: () => '→' },
        { titulo: 'UF comprador', classe: 'centro', valor: (r) => `<span class="forte">${UI.escapar(r.uf_destino)}</span>` },
        { titulo: 'Produto', valor: (r) => (r.produto_nome ? UI.escapar(r.produto_nome) : '<span class="mini">Todos os produtos</span>') },
        { titulo: 'Alíquota', classe: 'num', valor: (r) => `<span class="forte">${UI.numero(r.aliquota, 2)}%</span>` },
        { titulo: 'Observação', valor: (r) => UI.escapar(r.observacao || '-') },
        { titulo: 'Situação', classe: 'centro', valor: (r) => (r.ativo ? '<span class="tag tag-pago">Ativa</span>' : '<span class="tag tag-cancelado">Inativa</span>') },
      ],
      campos: [
        { nome: 'uf_origem', rotulo: 'UF do vendedor', tipo: 'select', obrigatorio: true,
          opcoes: () => Cadastros.opcoesUf(), dica: 'de onde sai a mercadoria' },
        { nome: 'uf_destino', rotulo: 'UF do comprador', tipo: 'select', obrigatorio: true,
          opcoes: () => Cadastros.opcoesUf(), dica: 'para onde vai' },
        { nome: 'aliquota', rotulo: 'Alíquota de ICMS (%)', tipo: 'dinheiro', padrao: 0,
          obrigatorio: true, dica: 'ex.: 12 para 12%' },
        { nome: 'produto_id', rotulo: 'Produto', tipo: 'select', vazio: 'Todos os produtos',
          opcoes: () => Api.produtosAtivos().map((p) => ({ valor: p.id, rotulo: `${p.codigo} — ${p.nome}` })),
          dica: 'deixe em branco para valer para qualquer produto' },
        { nome: 'observacao', rotulo: 'Observação', largura: 2, dica: 'ex.: diferimento, redução de base, fundamento legal' },
        { nome: 'ativo', rotulo: 'Situação', tipo: 'checkbox', textoCheck: 'Alíquota ativa' },
      ],
      montarPayload: (d) => ({
        ...d,
        produto_id: d.produto_id ? Number(d.produto_id) : null,
        aliquota: Number(d.aliquota || 0),
      }),
    });
  },

  gerarIcmsPadrao() {
    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <p class="mini" style="margin-top:0">
        Cria as linhas "todos os produtos" saindo do estado escolhido para os outros 26, com a
        alíquota interestadual de referência: <b>7%</b> de MG, PR, RJ, RS, SC e SP para o Norte,
        Nordeste, Centro-Oeste e ES; <b>12%</b> nas demais. Confirme com o contador —
        isenção, diferimento e redução de base do café variam por estado.
      </p>
      <div class="linha-campos">
        ${UI.campo('UF do vendedor *', UI.select('uf_origem', Cadastros.opcoesUf(), 'MG', { vazio: false }))}
        ${UI.campo('Alíquota interna (%)', '<input type="number" step="0.01" name="aliquota_interna" placeholder="opcional">', 'venda dentro do mesmo estado; em branco = não cria')}
      </div>
      <label class="mini" style="display:block;margin-top:10px">
        <input type="checkbox" name="substituir"> substituir as alíquotas gerais que já existem para esse estado
      </label>`;
    UI.abrirModal({
      titulo: 'Gerar alíquotas interestaduais',
      corpo,
      botoes: [
        { rotulo: 'Cancelar', acao: UI.fecharModal },
        {
          rotulo: 'Gerar',
          classe: 'btn-primario',
          acao: async () => {
            const d = UI.lerFormulario(corpo);
            try {
              const r = await Api.post('/api/icms/gerar-padrao', {
                empresa_id: Estado.empresaId,
                uf_origem: d.uf_origem,
                aliquota_interna: d.aliquota_interna === null ? null : Number(d.aliquota_interna),
                substituir: Boolean(d.substituir),
              });
              UI.fecharModal();
              UI.sucesso(r.mensagem);
              await Api.carregarCache(true);
              App.recarregar();
            } catch (e) {
              UI.erro(e.message);
            }
          },
        },
      ],
    });
  },

  /* ---------------------------------------------------------------- bancos */
  bancos() {
    return Cadastros.tela({
      titulo: 'Bancos e Contas de Caixa',
      endpoint: '/api/bancos',
      ajuda: 'o saldo inicial gera automaticamente o lançamento contábil de abertura',
      listar: () => Api.get('/api/bancos', { empresa_id: Estado.empresaId }),
      colunas: [
        { titulo: 'Código', valor: (r) => UI.escapar(r.codigo || '-') },
        { titulo: 'Nome', valor: (r) => UI.escapar(r.nome) },
        { titulo: 'Tipo', valor: (r) => ({ CAIXA: 'Caixa', CORRENTE: 'Conta corrente', POUPANCA: 'Poupança', APLICACAO: 'Aplicação', CARTAO: 'Cartão' }[r.tipo] || r.tipo) },
        { titulo: 'Agência / Conta', valor: (r) => `${UI.escapar(r.agencia || '-')} / ${UI.escapar(r.conta || '-')}` },
        { titulo: 'Conta contábil', valor: (r) => UI.escapar(r.conta_contabil_nome || '-') },
        { titulo: 'Saldo inicial', classe: 'num', valor: (r) => UI.moeda(r.saldo_inicial) },
        { titulo: 'Situação', classe: 'centro', valor: (r) => (r.ativo ? '<span class="tag tag-pago">Ativa</span>' : '<span class="tag tag-cancelado">Inativa</span>') },
      ],
      campos: [
        { nome: 'codigo', rotulo: 'Código interno' },
        { nome: 'nome', rotulo: 'Nome da conta', obrigatorio: true, largura: 2 },
        {
          nome: 'tipo', rotulo: 'Tipo', tipo: 'select', vazio: false, padrao: 'CORRENTE',
          opcoes: () => [
            { valor: 'CAIXA', rotulo: 'Caixa' },
            { valor: 'CORRENTE', rotulo: 'Conta corrente' },
            { valor: 'POUPANCA', rotulo: 'Poupança' },
            { valor: 'APLICACAO', rotulo: 'Aplicação financeira' },
            { valor: 'CARTAO', rotulo: 'Cartão' },
          ],
        },
        { nome: 'codigo_banco', rotulo: 'Código do banco', dica: 'ex.: 001, 341, 237' },
        { nome: 'agencia', rotulo: 'Agência' },
        { nome: 'conta', rotulo: 'Conta' },
        { nome: 'titular', rotulo: 'Titular' },
        {
          nome: 'conta_contabil_id', rotulo: 'Conta contábil', tipo: 'select', largura: 2,
          opcoes: () => UI.opcoesContas(['ATIVO']),
          dica: 'onde o saldo desta conta aparece no balancete',
        },
        { nome: 'saldo_inicial', rotulo: 'Saldo inicial', tipo: 'dinheiro', padrao: 0 },
        { nome: 'data_saldo_inicial', rotulo: 'Data do saldo inicial', tipo: 'data', padrao: UI.hoje() },
        { nome: 'ativo', rotulo: 'Situação', tipo: 'checkbox', textoCheck: 'Conta ativa' },
      ],
    });
  },

  /* -------------------------------------------------------- centros de custo */
  centrosCusto() {
    return Cadastros.tela({
      titulo: 'Centros de Custo',
      endpoint: '/api/centros-custo',
      listar: () => Api.get('/api/centros-custo', { empresa_id: Estado.empresaId }),
      acoesExtras: [
        {
          rotulo: 'Gerar padrão',
          acao: async () => {
            await Api.postQuery('/api/centros-custo/padrao', { empresa_id: Estado.empresaId });
            UI.sucesso('Centros de custo padrão criados.');
            await Api.carregarCache(true);
            App.recarregar();
          },
        },
      ],
      colunas: [
        { titulo: 'Código', valor: (r) => UI.escapar(r.codigo) },
        { titulo: 'Nome', valor: (r) => UI.escapar(r.nome) },
        { titulo: 'Tipo', valor: (r) => UI.escapar(r.tipo || '-') },
        { titulo: 'Aceita lançamento', classe: 'centro', valor: (r) => (r.aceita_lancamento ? 'Sim' : 'Não') },
        { titulo: 'Situação', classe: 'centro', valor: (r) => (r.ativo ? '<span class="tag tag-pago">Ativo</span>' : '<span class="tag tag-cancelado">Inativo</span>') },
      ],
      campos: [
        { nome: 'codigo', rotulo: 'Código', obrigatorio: true },
        { nome: 'nome', rotulo: 'Nome', obrigatorio: true, largura: 2 },
        {
          nome: 'tipo', rotulo: 'Tipo', tipo: 'select', vazio: false, padrao: 'ADMINISTRATIVO',
          opcoes: () => ['ADMINISTRATIVO', 'COMERCIAL', 'OPERACIONAL', 'PRODUCAO', 'PROJETO', 'OUTROS']
            .map((v) => ({ valor: v, rotulo: v })),
        },
        {
          nome: 'pai_id', rotulo: 'Centro de custo superior', tipo: 'select',
          opcoes: () => UI.opcoesCentros(),
        },
        { nome: 'aceita_lancamento', rotulo: 'Lançamentos', tipo: 'checkbox', textoCheck: 'Aceita lançamento' },
        { nome: 'ativo', rotulo: 'Situação', tipo: 'checkbox', textoCheck: 'Centro ativo' },
      ],
    });
  },

  /* -------------------------------------------------------------- operações */
  operacoes() {
    return Cadastros.tela({
      titulo: 'Operações',
      endpoint: '/api/operacoes',
      ajuda: 'a operação define a natureza do movimento e sugere a classificação contábil',
      listar: () => Api.get('/api/operacoes', { empresa_id: Estado.empresaId }),
      acoesExtras: [
        {
          rotulo: 'Gerar padrão',
          acao: async () => {
            await Api.postQuery('/api/operacoes/padrao', { empresa_id: Estado.empresaId });
            UI.sucesso('Operações padrão criadas.');
            await Api.carregarCache(true);
            App.recarregar();
          },
        },
      ],
      colunas: [
        { titulo: 'Código', valor: (r) => UI.escapar(r.codigo) },
        { titulo: 'Nome', valor: (r) => UI.escapar(r.nome) },
        { titulo: 'Natureza', valor: (r) => ({ ENTRADA: 'Entrada', SAIDA: 'Saída', AMBAS: 'Ambas' }[r.natureza]) },
        { titulo: 'Conta contábil sugerida', valor: (r) => UI.escapar(r.conta_contabil_nome || '-') },
        { titulo: 'Centro de custo', valor: (r) => UI.escapar(r.centro_custo_nome || '-') },
        { titulo: 'Situação', classe: 'centro', valor: (r) => (r.ativo ? '<span class="tag tag-pago">Ativa</span>' : '<span class="tag tag-cancelado">Inativa</span>') },
      ],
      campos: [
        { nome: 'codigo', rotulo: 'Código', obrigatorio: true },
        { nome: 'nome', rotulo: 'Nome', obrigatorio: true, largura: 2 },
        {
          nome: 'natureza', rotulo: 'Natureza', tipo: 'select', vazio: false, padrao: 'ENTRADA',
          opcoes: () => [
            { valor: 'ENTRADA', rotulo: 'Entrada (recebimento)' },
            { valor: 'SAIDA', rotulo: 'Saída (pagamento)' },
            { valor: 'AMBAS', rotulo: 'Ambas' },
          ],
        },
        {
          nome: 'conta_contabil_id', rotulo: 'Conta contábil sugerida', tipo: 'select', largura: 2,
          opcoes: () => UI.opcoesContas(),
        },
        {
          nome: 'centro_custo_id', rotulo: 'Centro de custo sugerido', tipo: 'select',
          opcoes: () => UI.opcoesCentros(),
        },
        { nome: 'descricao', rotulo: 'Descrição', tipo: 'textarea', largura: 2 },
        { nome: 'ativo', rotulo: 'Situação', tipo: 'checkbox', textoCheck: 'Operação ativa' },
      ],
    });
  },

  /* ---------------------------------------------------------- plano de contas */
  contasContabeis() {
    return Cadastros.tela({
      titulo: 'Plano de Contas',
      endpoint: '/api/contas-contabeis',
      ajuda: 'contas sintéticas apenas agrupam; as analíticas recebem os lançamentos',
      listar: () => Api.get('/api/contas-contabeis', { empresa_id: Estado.empresaId }),
      acoesExtras: [
        {
          rotulo: 'Gerar plano padrão',
          acao: async () => {
            const r = await Api.postQuery('/api/contas-contabeis/plano-padrao', { empresa_id: Estado.empresaId });
            UI.sucesso(`${r.criadas} conta(s) criada(s).`);
            await Api.carregarCache(true);
            App.recarregar();
          },
        },
      ],
      colunas: [
        {
          titulo: 'Código',
          valor: (r) => `<span class="recuo-${Math.min(r.nivel - 1, 3)}" style="padding-left:${(r.nivel - 1) * 14}px">${UI.escapar(r.codigo)}</span>`,
        },
        { titulo: 'Descrição', valor: (r) => (r.analitica ? UI.escapar(r.nome) : `<span class="forte">${UI.escapar(r.nome)}</span>`) },
        { titulo: 'Tipo', valor: (r) => ({ ATIVO: 'Ativo', PASSIVO: 'Passivo', PATRIMONIO_LIQUIDO: 'Patrimônio líquido', RECEITA: 'Receita', CUSTO: 'Custo', DESPESA: 'Despesa' }[r.tipo] || r.tipo) },
        { titulo: 'Natureza', classe: 'centro', valor: (r) => (r.natureza === 'D' ? 'Devedora' : 'Credora') },
        { titulo: 'Classificação', classe: 'centro', valor: (r) => (r.analitica ? 'Analítica' : 'Sintética') },
        { titulo: 'Grupo no DRE', valor: (r) => UI.escapar((r.grupo_dre || '-').replaceAll('_', ' ')) },
      ],
      campos: [
        { nome: 'codigo', rotulo: 'Código', obrigatorio: true, dica: 'use pontos para a hierarquia: 4.3.01.001' },
        { nome: 'nome', rotulo: 'Descrição', obrigatorio: true, largura: 2 },
        {
          nome: 'tipo', rotulo: 'Tipo', tipo: 'select', vazio: false, padrao: 'DESPESA',
          opcoes: () => [
            { valor: 'ATIVO', rotulo: 'Ativo' },
            { valor: 'PASSIVO', rotulo: 'Passivo' },
            { valor: 'PATRIMONIO_LIQUIDO', rotulo: 'Patrimônio líquido' },
            { valor: 'RECEITA', rotulo: 'Receita' },
            { valor: 'CUSTO', rotulo: 'Custo' },
            { valor: 'DESPESA', rotulo: 'Despesa' },
          ],
        },
        {
          nome: 'natureza', rotulo: 'Natureza', tipo: 'select', vazio: false, padrao: 'D',
          opcoes: () => [{ valor: 'D', rotulo: 'Devedora' }, { valor: 'C', rotulo: 'Credora' }],
        },
        {
          nome: 'grupo_dre', rotulo: 'Grupo no DRE', tipo: 'select',
          dica: 'obrigatório para contas de resultado',
          opcoes: () => [
            'RECEITA_BRUTA', 'DEDUCOES', 'CUSTO', 'DESPESA_PESSOAL', 'DESPESA_ADMINISTRATIVA',
            'DESPESA_COMERCIAL', 'DESPESA_TRIBUTARIA', 'RECEITA_FINANCEIRA', 'DESPESA_FINANCEIRA',
            'OUTRAS_RECEITAS', 'OUTRAS_DESPESAS', 'IMPOSTO_RENDA',
          ].map((v) => ({ valor: v, rotulo: v.replaceAll('_', ' ') })),
        },
        { nome: 'saldo_inicial', rotulo: 'Saldo de abertura', tipo: 'dinheiro', padrao: 0, dica: 'não use em contas de banco/caixa' },
        { nome: 'analitica', rotulo: 'Classificação', tipo: 'checkbox', textoCheck: 'Analítica (aceita lançamento)' },
        { nome: 'ativo', rotulo: 'Situação', tipo: 'checkbox', textoCheck: 'Conta ativa' },
      ],
    });
  },

  /* ------------------------------------------------------------- usuários */
  usuarios() {
    return Cadastros.tela({
      titulo: 'Usuários',
      endpoint: '/api/usuarios',
      incluiEmpresa: false,
      ajuda: 'deixe a senha em branco ao editar para mantê-la',
      listar: () => Api.get('/api/usuarios'),
      colunas: [
        { titulo: 'Nome', valor: (r) => UI.escapar(r.nome) },
        { titulo: 'E-mail', valor: (r) => UI.escapar(r.email) },
        { titulo: 'Perfil', valor: (r) => ({ ADMIN: 'Administrador', OPERADOR: 'Operador', CONSULTA: 'Consulta' }[r.perfil]) },
        { titulo: 'Telefone', valor: (r) => UI.escapar(r.telefone || '-') },
        { titulo: 'Situação', classe: 'centro', valor: (r) => (r.ativo ? '<span class="tag tag-pago">Ativo</span>' : '<span class="tag tag-cancelado">Inativo</span>') },
      ],
      campos: [
        { nome: 'nome', rotulo: 'Nome', obrigatorio: true, largura: 2 },
        { nome: 'email', rotulo: 'E-mail', tipo: 'email', obrigatorio: true },
        { nome: 'senha', rotulo: 'Senha', tipo: 'password' },
        {
          nome: 'perfil', rotulo: 'Perfil', tipo: 'select', vazio: false, padrao: 'OPERADOR',
          opcoes: () => [
            { valor: 'ADMIN', rotulo: 'Administrador' },
            { valor: 'OPERADOR', rotulo: 'Operador' },
            { valor: 'CONSULTA', rotulo: 'Somente consulta' },
          ],
        },
        { nome: 'telefone', rotulo: 'Telefone' },
        { nome: 'ativo', rotulo: 'Situação', tipo: 'checkbox', textoCheck: 'Usuário ativo' },
      ],
    });
  },

  /* ------------------------------------------------------------ parâmetros */
  async parametros() {
    const alvo = Cadastros.alvo();
    const dados = await Api.get('/api/parametros', { empresa_id: Estado.empresaId });
    const opcoes = UI.opcoesContas();
    const campos = Object.entries(dados.valores)
      .map(([chave, valor]) => UI.campo(
        chave.replace('conta_', 'Conta: ').replaceAll('_', ' '),
        UI.select(chave, opcoes, valor ?? ''),
        dados.descricoes[chave],
      ))
      .join('');

    alvo.innerHTML = `
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div>
            <h3>Parâmetros contábeis</h3>
            <div class="mini">Contas usadas automaticamente pelo sistema ao lançar títulos, baixas e saldos iniciais</div>
          </div>
          <button class="btn btn-primario" id="btn-salvar-param">Salvar parâmetros</button>
        </div>
        <div class="cartao-corpo"><form id="form-param" class="linha-campos">${campos}</form></div>
      </div>`;

    alvo.querySelector('#btn-salvar-param').onclick = async () => {
      const valores = UI.lerFormulario(alvo.querySelector('#form-param'));
      Object.keys(valores).forEach((k) => { valores[k] = valores[k] ? Number(valores[k]) : null; });
      try {
        await Api.put('/api/parametros', { empresa_id: Estado.empresaId, valores });
        UI.sucesso('Parâmetros salvos.');
      } catch (e) {
        UI.erro(e.message);
      }
    };
  },
};
