/* Assinatura: pagamento por Pix, situação da conta e administração das contas. */
const Assinaturas = {
  dados: null,

  /* ------------------------------------------------------------------- dados */
  async carregar() {
    Assinaturas.dados = await Api.get('/api/assinatura/minha');
    return Assinaturas.dados;
  },

  /* --------------------------------------------- bloco de pagamento (reusável) */
  blocoPagamento(dados, { compacto = false } = {}) {
    const s = dados.situacao || {};
    const p = dados.pagamento;
    if (!p) {
      return '<div class="ok-caixa">Esta conta é interna e não depende de assinatura.</div>';
    }
    const plano = p.plano;
    const planos = dados.planos || [];

    const escolha = planos
      .map((op) => `
        <label class="plano-opcao ${op.codigo === plano.codigo ? 'ativo' : ''}">
          <input type="radio" name="plano" value="${op.codigo}" ${op.codigo === plano.codigo ? 'checked' : ''}>
          <div>
            <div class="forte">${UI.escapar(op.nome)}</div>
            <div class="mini">${op.meses} meses · ${UI.moeda(op.valor_mes)}/mês</div>
          </div>
          <div class="plano-opcao-valor">${UI.moeda(op.valor)}</div>
        </label>`)
      .join('');

    const areaPix = p.configurado
      ? `
        <div class="pix-grade">
          <div class="pix-qr">${p.qrcode_svg || '<div class="mini">QR Code indisponível — use a chave ao lado.</div>'}</div>
          <div>
            <div class="pix-linha"><span class="mini">Valor</span><b>${UI.moeda(plano.valor)}</b></div>
            <div class="pix-linha"><span class="mini">Chave Pix</span><b id="pix-chave">${UI.escapar(p.pix_chave)}</b></div>
            ${p.pix_titular ? `<div class="pix-linha"><span class="mini">Titular</span><b>${UI.escapar(p.pix_titular)}</b></div>` : ''}
            ${p.pix_banco ? `<div class="pix-linha"><span class="mini">Banco</span><b>${UI.escapar(p.pix_banco)}</b></div>` : ''}
            <div class="pix-linha"><span class="mini">Identificador</span><b>${UI.escapar(p.identificador || '-')}</b></div>
            <div class="espaco" style="margin-top:10px">
              <button class="btn btn-mini" id="btn-copiar-chave">Copiar chave</button>
              <button class="btn btn-mini" id="btn-copiar-codigo">Copiar código Pix</button>
            </div>
            <textarea id="pix-codigo" readonly class="pix-codigo">${UI.escapar(p.copia_e_cola)}</textarea>
          </div>
        </div>`
      : `<div class="aviso-caixa">
           A chave Pix ainda não foi configurada neste sistema.
           ${p.contato_whatsapp || p.contato_email
             ? `Fale com o suporte para receber os dados de pagamento:
                ${UI.escapar([p.contato_whatsapp, p.contato_email].filter(Boolean).join(' · '))}`
             : 'Peça ao administrador do sistema para cadastrar a chave em Configurações.'}
         </div>`;

    return `
      <div class="assinatura-status ${s.liberado ? 'ok' : 'bloqueado'}">
        <div>
          <div class="kpi-rotulo">${UI.escapar(s.titulo || '')}</div>
          <div>${UI.escapar(s.mensagem || '')}</div>
        </div>
        <span class="tag ${s.liberado ? 'tag-pago' : 'tag-vencido'}">${UI.escapar(s.status || '')}</span>
      </div>

      ${compacto ? '' : `
      <h3 class="titulo-bloco">1. Escolha o plano</h3>
      <div class="planos-opcao">${escolha}</div>`}

      <h3 class="titulo-bloco">${compacto ? '' : '2. '}Pague por Pix</h3>
      ${areaPix}

      <h3 class="titulo-bloco">${compacto ? '' : '3. '}Avise que pagou</h3>
      <div class="mini" style="margin-bottom:8px">${UI.escapar(p.aviso || '')}</div>
      ${UI.campo('Observação (opcional)',
        '<input name="observacao" placeholder="ex.: pago pelo Banco X às 14h, em nome de ...">')}
      <button class="btn btn-verde btn-bloco" id="btn-informei-pix" style="margin-top:10px">
        Já fiz o Pix
      </button>
      ${s.pagamento_informado_em
        ? `<div class="mini" style="margin-top:8px">Pagamento informado em ${UI.data(s.pagamento_informado_em)} — aguardando confirmação.</div>`
        : ''}`;
  },

  ligarPagamento(raiz, aoAtualizar) {
    const copiar = async (texto, mensagem) => {
      try {
        await navigator.clipboard.writeText(texto);
        UI.sucesso(mensagem);
      } catch {
        UI.aviso('Copie manualmente: ' + texto);
      }
    };
    const chave = raiz.querySelector('#pix-chave');
    const codigo = raiz.querySelector('#pix-codigo');
    raiz.querySelector('#btn-copiar-chave')?.addEventListener('click', () =>
      copiar(chave.textContent.trim(), 'Chave Pix copiada.'));
    raiz.querySelector('#btn-copiar-codigo')?.addEventListener('click', () =>
      copiar(codigo.value, 'Código Pix copiado. Cole no aplicativo do seu banco.'));

    raiz.querySelectorAll('input[name=plano]').forEach((radio) => {
      radio.onchange = async () => {
        try {
          await Api.post('/api/assinatura/plano', { plano: radio.value });
          UI.sucesso('Plano atualizado.');
          aoAtualizar();
        } catch (e) {
          UI.erro(e.message);
        }
      };
    });

    raiz.querySelector('#btn-informei-pix')?.addEventListener('click', async () => {
      const obs = raiz.querySelector('[name=observacao]')?.value || '';
      try {
        const r = await Api.post('/api/assinatura/pagamento', { observacao: obs });
        UI.sucesso(r.mensagem);
        aoAtualizar();
      } catch (e) {
        UI.erro(e.message);
      }
    });
  },

  /* ------------------------------------------------- tela cheia de bloqueio */
  async bloquear(mensagem) {
    document.getElementById('app').classList.add('oculto');
    document.getElementById('site').classList.add('oculto');
    const tela = document.getElementById('tela-pagamento');
    tela.classList.remove('oculto');
    const alvo = document.getElementById('pagamento-conteudo');
    alvo.innerHTML = '<div class="vazio">Carregando dados da assinatura...</div>';

    let dados;
    try {
      dados = await Assinaturas.carregar();
    } catch {
      alvo.innerHTML = `<div class="vazio">${UI.escapar(mensagem || 'Não foi possível carregar a assinatura.')}</div>`;
      return;
    }

    alvo.innerHTML = `
      <div class="pagamento-topo">
        <div class="site-marca"><span class="marca-icone">₣</span><span>Assinatura</span></div>
        <button class="btn" id="btn-sair-pagamento">Sair</button>
      </div>
      <h2 style="margin-bottom:6px">${UI.escapar(dados.situacao.titulo || 'Liberar acesso')}</h2>
      <p class="mini" style="margin-bottom:18px">
        Seus dados continuam guardados. Assim que o pagamento for confirmado, tudo volta como estava.
      </p>
      <div id="area-pagamento">${Assinaturas.blocoPagamento(dados)}</div>`;

    Assinaturas.ligarPagamento(alvo, () => Assinaturas.bloquear());
    alvo.querySelector('#btn-sair-pagamento').onclick = () => Api.sair();
  },

  /* -------------------------------------------- página "Minha assinatura" */
  async minha() {
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando...</div></div>';
    const dados = await Assinaturas.carregar();

    if (!dados.pagamento) {
      alvo.innerHTML = `
        <div class="cartao"><div class="cartao-corpo">
          <div class="ok-caixa">Você está no perfil de administrador do sistema — esta conta não
          depende de assinatura. Use o menu <b>Assinaturas</b> para acompanhar os assinantes.</div>
        </div></div>`;
      return;
    }

    alvo.innerHTML = `
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Minha assinatura</h3>
            <div class="mini">Plano, pagamento por Pix e situação do acesso</div></div>
        </div>
        <div class="cartao-corpo" id="area-pagamento">${Assinaturas.blocoPagamento(dados)}</div>
      </div>
      ${Assinaturas.blocoUsuarios(dados)}`;
    Assinaturas.ligarPagamento(alvo, () => Assinaturas.minha());
    Assinaturas.ligarUsuarios(alvo, dados);
  },

  /* ------------------------------------------------- usuários e pacotes extras */
  blocoUsuarios(dados) {
    const u = dados.usuarios;
    if (!u || u.ilimitado) return '';
    const pendente = u.pacotes_solicitados
      ? `<div class="aviso-caixa" style="margin-top:12px">
           <b>${u.pacotes_solicitados} pacote(s)</b> aguardando confirmação do Pix
           — ${UI.moeda(u.valor_pacote * u.pacotes_solicitados)}.
           ${dados.pagamento_pacotes ? `<div class="mini">Pix copia e cola:</div>
             <div class="pix-codigo" id="pix-pacotes">${UI.escapar(dados.pagamento_pacotes.copia_e_cola || '')}</div>
             <button class="btn btn-mini" id="btn-copiar-pacotes">Copiar código Pix</button>` : ''}
           <button class="btn btn-mini btn-perigo" id="btn-cancelar-pacotes">Cancelar pedido</button>
         </div>`
      : '';
    return `
      <div class="cartao" style="margin-top:18px">
        <div class="cartao-cabecalho">
          <div><h3>Usuários do sistema</h3>
            <div class="mini">${u.incluidos} usuário(s) inclusos no plano · pacotes extras de
              ${u.por_pacote} com ${UI.numero(u.desconto_percentual, 0)}% de desconto</div></div>
          <button class="btn btn-primario" id="btn-comprar-pacote">+ Contratar pacote</button>
        </div>
        <div class="cartao-corpo">
          <div class="grade g4">
            <div class="kpi destaque-azul"><div class="kpi-rotulo">Em uso</div>
              <div class="kpi-valor">${u.usados}</div></div>
            <div class="kpi"><div class="kpi-rotulo">Limite contratado</div>
              <div class="kpi-valor">${u.limite}</div>
              <div class="kpi-nota">${u.incluidos} inclusos + ${u.pacotes} pacote(s)</div></div>
            <div class="kpi destaque-verde"><div class="kpi-rotulo">Disponíveis</div>
              <div class="kpi-valor ${u.disponiveis ? 'positivo' : 'negativo'}">${u.disponiveis}</div></div>
            <div class="kpi destaque-ambar"><div class="kpi-rotulo">Pacote de +${u.por_pacote}</div>
              <div class="kpi-valor" style="font-size:19px">${UI.moeda(u.valor_pacote)}</div>
              <div class="kpi-nota">${UI.moeda(u.valor_por_usuario)} por usuário</div></div>
          </div>
          ${pendente}
        </div>
      </div>`;
  },

  ligarUsuarios(alvo, dados) {
    const u = dados.usuarios;
    if (!u || u.ilimitado) return;
    const botao = alvo.querySelector('#btn-comprar-pacote');
    if (botao) botao.onclick = () => Assinaturas.comprarPacote(u);

    const copiar = alvo.querySelector('#btn-copiar-pacotes');
    if (copiar) {
      copiar.onclick = () => {
        navigator.clipboard.writeText(alvo.querySelector('#pix-pacotes').textContent.trim());
        UI.sucesso('Código Pix copiado.');
      };
    }
    const cancelar = alvo.querySelector('#btn-cancelar-pacotes');
    if (cancelar) {
      cancelar.onclick = async () => {
        if (!(await UI.confirmar('Cancelar o pedido de pacotes de usuários?', 'Cancelar pedido'))) return;
        await Api.post('/api/assinatura/pacotes/cancelar');
        UI.sucesso('Pedido cancelado.');
        Assinaturas.minha();
      };
    }
  },

  comprarPacote(u) {
    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <p>Cada pacote adiciona <b>${u.por_pacote} usuários</b> por
         <b>${UI.moeda(u.valor_pacote)}</b>
         (${UI.numero(u.desconto_percentual, 0)}% de desconto sobre o plano de
         ${UI.moeda(u.plano_valor)}), válido pelo mesmo período da assinatura.</p>
      <div class="linha-campos">
        ${UI.campo('Quantos pacotes', '<input type="number" name="quantidade" min="1" max="20" value="1">')}
      </div>
      <div class="ok-caixa" id="previa-pacote" style="margin-top:12px"></div>`;

    const campo = corpo.querySelector('[name=quantidade]');
    const previa = () => {
      const q = Math.max(1, Number(campo.value) || 1);
      corpo.querySelector('#previa-pacote').innerHTML =
        `+${q * u.por_pacote} usuários — total <b>${UI.moeda(q * u.valor_pacote)}</b>.
         O limite sobe após a confirmação do Pix.`;
    };
    campo.oninput = previa;
    previa();

    UI.abrirModal({
      titulo: 'Contratar usuários extras',
      corpo,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        {
          rotulo: 'Solicitar pacote',
          classe: 'btn-primario',
          acao: async () => {
            try {
              const r = await Api.post('/api/assinatura/pacotes', {
                quantidade: Math.max(1, Number(campo.value) || 1),
              });
              UI.fecharModal();
              UI.sucesso(r.mensagem);
              Assinaturas.minha();
            } catch (e) { UI.erro(e.message); }
          },
        },
      ],
    });
  },

  avisoBoasVindas(resposta) {
    const horas = Site.info?.horas_teste || 48;
    UI.abrirModal({
      titulo: 'Bem-vindo!',
      corpo: `
        <div class="ok-caixa">Sua conta está criada e liberada por <b>${horas} horas</b>.</div>
        <p>Já deixamos prontos para você:</p>
        <ul>
          <li>Plano de contas contábil completo</li>
          <li>Centros de custo e operações padrão</li>
          <li>Sua empresa cadastrada: <b>${UI.escapar(resposta.empresa?.razao_social || '')}</b></li>
        </ul>
        <p>Cadastre suas contas bancárias em <b>Bancos</b> e comece a lançar.
        Quando quiser assinar, vá em <b>Minha assinatura</b> e pague por Pix.</p>`,
      botoes: [
        { rotulo: 'Ver minha assinatura', acao: () => { UI.fecharModal(); location.hash = '#/assinatura'; } },
        { rotulo: 'Começar a usar', classe: 'btn-primario', acao: UI.fecharModal },
      ],
    });
  },

  /* --------------------------------------------------- faixa dentro do app */
  faixa(situacao) {
    const barra = document.getElementById('faixa-assinatura');
    if (!situacao || situacao.status === 'INTERNA' || situacao.motivo === '') {
      barra.classList.add('oculto');
      return;
    }
    if (situacao.motivo === 'EM_TESTE') {
      barra.className = 'faixa-assinatura teste';
      barra.innerHTML = `
        <span>Período de teste — faltam
          <b>${situacao.horas_restantes}h${String(situacao.minutos_restantes).padStart(2, '0')}min</b>.
          ${situacao.status === 'AGUARDANDO' ? 'Pagamento informado, aguardando confirmação.' : ''}</span>
        <a href="#/assinatura" class="btn btn-mini">Assinar agora</a>`;
      barra.classList.remove('oculto');
      return;
    }
    if (situacao.dias_restantes !== undefined && situacao.dias_restantes !== null
        && situacao.dias_restantes <= 15) {
      barra.className = 'faixa-assinatura aviso';
      barra.innerHTML = `
        <span>Sua assinatura vence em <b>${situacao.dias_restantes} dia(s)</b>.</span>
        <a href="#/assinatura" class="btn btn-mini">Renovar</a>`;
      barra.classList.remove('oculto');
      return;
    }
    barra.classList.add('oculto');
  },

  /* ------------------------------------------------------- administração */
  async admin() {
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando assinaturas...</div></div>';
    const dados = await Api.get('/api/admin/assinaturas');
    const r = dados.resumo;

    const rotulos = {
      TESTE: 'Em teste', AGUARDANDO: 'Aguardando Pix', ATIVA: 'Ativa',
      EXPIRADA: 'Expirada', CANCELADA: 'Cancelada', BLOQUEADA: 'Bloqueada',
    };

    alvo.innerHTML = `
      <div class="grade g4" style="margin-bottom:18px">
        <div class="kpi destaque-azul"><div class="kpi-rotulo">Contas cadastradas</div>
          <div class="kpi-valor">${r.total}</div></div>
        <div class="kpi destaque-ambar"><div class="kpi-rotulo">Em teste</div>
          <div class="kpi-valor">${r.em_teste}</div><div class="kpi-nota">48h após o cadastro</div></div>
        <div class="kpi destaque-vermelho"><div class="kpi-rotulo">Aguardando confirmação</div>
          <div class="kpi-valor">${r.aguardando}</div><div class="kpi-nota">informaram o Pix</div></div>
        <div class="kpi destaque-verde"><div class="kpi-rotulo">Assinaturas ativas</div>
          <div class="kpi-valor">${r.ativas}</div><div class="kpi-nota">${UI.moeda(r.receita_ativa)} contratados</div></div>
      </div>

      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Assinantes</h3><div class="mini">Confirme o Pix para liberar o acesso da conta</div></div>
          <button class="btn" id="btn-exportar">Exportar CSV</button>
        </div>
        <div class="cartao-corpo sem-padding" id="lista-assinaturas"></div>
      </div>`;

    alvo.querySelector('#lista-assinaturas').innerHTML = UI.tabela({
      colunas: [
        { titulo: 'Cliente', valor: (a) => `<div class="forte">${UI.escapar(a.usuario_nome)}</div>
            <div class="mini">${UI.escapar(a.usuario_email)}</div>` },
        { titulo: 'Empresa', valor: (a) => UI.escapar(a.empresa_nome) },
        { titulo: 'Contato', valor: (a) => `<span class="mini">${UI.escapar(a.usuario_telefone || '-')}</span>` },
        { titulo: 'Plano', valor: (a) => `${a.plano === 'ANUAL' ? 'Anual' : 'Semestral'}<div class="mini">${UI.moeda(a.valor)}</div>` },
        { titulo: 'Usuários', classe: 'centro', valor: (a) => `${a.limite_usuarios}
            <div class="mini">${a.pacotes_usuarios || 0} pacote(s)${a.pacotes_solicitados
              ? ` · <b>${a.pacotes_solicitados} pendente(s)</b>` : ''}</div>` },
        { titulo: 'Cadastro', valor: (a) => UI.data(a.criado_em) },
        { titulo: 'Teste até', valor: (a) => (a.teste_fim ? UI.data(a.teste_fim) : '-') },
        { titulo: 'Pix informado', valor: (a) => (a.pagamento_informado_em
            ? `${UI.data(a.pagamento_informado_em)}<div class="mini">${UI.escapar(a.pagamento_observacao || '')}</div>`
            : '<span class="mini">-</span>') },
        { titulo: 'Vence em', valor: (a) => (a.data_fim ? UI.data(a.data_fim) : '-') },
        { titulo: 'Situação', classe: 'centro', valor: (a) => {
          const rotulo = a.status === 'TESTE' && !a.liberado
            ? 'Teste encerrado'
            : (rotulos[a.status] || a.status);
          return `<span class="tag ${a.liberado ? 'tag-pago' : 'tag-vencido'}">${rotulo}</span>`;
        } },
        { titulo: 'Ações', classe: 'centro', valor: (a, i) => `
            ${a.status !== 'ATIVA' || !a.liberado
              ? `<button class="btn btn-mini btn-verde" data-confirmar="${i}">Confirmar Pix</button>` : ''}
            ${a.pacotes_solicitados
              ? `<button class="btn btn-mini btn-verde" data-pacotes="${i}">Liberar pacotes</button>` : ''}
            <button class="btn btn-mini" data-gerenciar="${i}">Gerenciar</button>` },
      ],
      linhas: dados.linhas,
      vazio: 'Nenhuma conta cadastrada ainda.',
    });

    alvo.querySelector('#btn-exportar').onclick = () =>
      UI.exportarTabela('assinaturas', '#lista-assinaturas table');

    alvo.querySelectorAll('[data-confirmar]').forEach((b) => {
      b.onclick = () => Assinaturas.confirmar(dados.linhas[Number(b.dataset.confirmar)]);
    });
    alvo.querySelectorAll('[data-gerenciar]').forEach((b) => {
      b.onclick = () => Assinaturas.gerenciar(dados.linhas[Number(b.dataset.gerenciar)]);
    });
    alvo.querySelectorAll('[data-pacotes]').forEach((b) => {
      b.onclick = () => Assinaturas.liberarPacotes(dados.linhas[Number(b.dataset.pacotes)]);
    });
  },

  async liberarPacotes(assinatura) {
    const total = assinatura.valor_pacote * assinatura.pacotes_solicitados;
    if (!(await UI.confirmar(
      `Confirmar o Pix de ${UI.moeda(total)} e liberar ${assinatura.pacotes_solicitados} `
      + `pacote(s) de usuários para ${assinatura.usuario_nome}?`, 'Liberar'))) return;
    try {
      await Api.post(`/api/admin/assinaturas/${assinatura.id}/pacotes`, {
        quantidade: assinatura.pacotes_solicitados,
      });
      UI.sucesso('Pacotes liberados.');
      Assinaturas.admin();
    } catch (e) { UI.erro(e.message); }
  },

  confirmar(assinatura) {
    const meses = assinatura.plano === 'ANUAL' ? 12 : 6;
    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <p>Confirmar o recebimento do Pix de <b>${UI.escapar(assinatura.usuario_nome)}</b>
         no valor de <b>${UI.moeda(assinatura.valor)}</b>?</p>
      <div class="linha-campos">
        ${UI.campo('Meses a liberar', `<input type="number" name="meses" value="${meses}" min="1" max="60">`)}
        ${UI.campo('Observação interna', '<input name="observacao" placeholder="ex.: Pix recebido em 10/09">')}
      </div>
      <div class="ok-caixa" style="margin-top:12px">
        O acesso da conta é liberado imediatamente e vale até a nova data de vencimento.
      </div>`;

    UI.abrirModal({
      titulo: 'Confirmar pagamento',
      corpo,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        {
          rotulo: 'Confirmar e liberar',
          classe: 'btn-verde',
          acao: async () => {
            const d = UI.lerFormulario(corpo);
            try {
              await Api.post(`/api/admin/assinaturas/${assinatura.id}/confirmar`, {
                status: 'ATIVA', meses: Number(d.meses) || meses, observacao: d.observacao,
              });
              UI.fecharModal();
              UI.sucesso('Assinatura liberada.');
              Assinaturas.admin();
            } catch (e) {
              UI.erro(e.message);
            }
          },
        },
      ],
    });
  },

  gerenciar(assinatura) {
    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <div class="linha-campos">
        ${UI.campo('Situação', UI.select('status', [
          { valor: 'TESTE', rotulo: 'Em teste' },
          { valor: 'AGUARDANDO', rotulo: 'Aguardando Pix' },
          { valor: 'ATIVA', rotulo: 'Ativa' },
          { valor: 'EXPIRADA', rotulo: 'Expirada' },
          { valor: 'CANCELADA', rotulo: 'Cancelada' },
          { valor: 'BLOQUEADA', rotulo: 'Bloqueada' },
        ], assinatura.status, { vazio: false }))}
        ${UI.campo('Plano', UI.select('plano', [
          { valor: 'SEMESTRAL', rotulo: 'Semestral' }, { valor: 'ANUAL', rotulo: 'Anual' },
        ], assinatura.plano, { vazio: false }))}
        ${UI.campo('Horas de teste', '<input type="number" name="horas_teste" placeholder="ex.: 48">',
          'preenchido apenas ao reabrir um teste')}
        ${UI.campo('Observação interna', `<input name="observacao" value="${UI.escapar(assinatura.observacao_admin || '')}">`)}
      </div>`;

    UI.abrirModal({
      titulo: `Conta de ${assinatura.usuario_nome}`,
      corpo,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        {
          rotulo: 'Salvar',
          classe: 'btn-primario',
          acao: async () => {
            const d = UI.lerFormulario(corpo);
            try {
              await Api.post(`/api/admin/assinaturas/${assinatura.id}/status`, {
                status: d.status,
                plano: d.plano,
                horas_teste: d.horas_teste ? Number(d.horas_teste) : null,
                observacao: d.observacao,
              });
              UI.fecharModal();
              UI.sucesso('Assinatura atualizada.');
              Assinaturas.admin();
            } catch (e) {
              UI.erro(e.message);
            }
          },
        },
      ],
    });
  },

  /* ------------------------------------------- empresas e acessos (MASTER) */
  async empresas() {
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando empresas...</div></div>';
    const dados = await Api.get('/api/admin/empresas');
    const r = dados.resumo;
    Assinaturas._empresas = dados.linhas;

    const somarDias = (dias) => {
      const d = new Date(); d.setDate(d.getDate() + dias);
      return d.toISOString().slice(0, 10);
    };
    const diasAte = (iso) => {
      if (!iso) return null;
      const hoje = new Date(UI.hoje() + 'T00:00:00');
      return Math.round((new Date(iso + 'T00:00:00') - hoje) / 86400000);
    };
    const situacao = (l) => {
      if (l.status === 'BLOQUEADA') return '<span class="tag tag-vencido">Bloqueada</span>';
      if (!l.liberado) return `<span class="tag tag-vencido">${UI.escapar(l.situacao_titulo || 'Sem acesso')}</span>`;
      if (l.status === 'ATIVA') {
        const d = diasAte(l.data_fim);
        if (d !== null && d <= 15) return `<span class="tag tag-parcial">Liberada · vence em ${d} dia(s)</span>`;
        return '<span class="tag tag-pago">Liberada</span>';
      }
      return `<span class="tag tag-aberto">${UI.escapar(l.situacao_titulo || l.status)}</span>`;
    };

    alvo.innerHTML = `
      <div class="grade g4" style="margin-bottom:18px">
        <div class="kpi destaque-azul"><div class="kpi-rotulo">Empresas cadastradas</div>
          <div class="kpi-valor">${r.total}</div><div class="kpi-nota">${r.usuarios} usuário(s) ativos</div></div>
        <div class="kpi destaque-verde"><div class="kpi-rotulo">Com acesso liberado</div>
          <div class="kpi-valor">${r.liberadas}</div></div>
        <div class="kpi destaque-ambar"><div class="kpi-rotulo">Vencem em até 15 dias</div>
          <div class="kpi-valor">${r.vencem_15_dias}</div></div>
        <div class="kpi destaque-vermelho"><div class="kpi-rotulo">Bloqueadas / sem acesso</div>
          <div class="kpi-valor">${r.bloqueadas}</div></div>
      </div>
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Empresas</h3><div class="mini">Libere o acesso até uma data (depois dela a empresa bloqueia sozinha),
            bloqueie na hora e ajuste quantos usuários cada empresa pode ter
            (padrão: ${dados.usuarios_incluidos}).</div></div>
          <input id="busca-empresa" placeholder="Buscar empresa, CNPJ ou e-mail" style="max-width:260px">
        </div>
        <div class="cartao-corpo sem-padding" id="lista-empresas"></div>
      </div>`;

    const desenhar = (filtro = '') => {
      const f = filtro.trim().toLowerCase();
      const linhas = dados.linhas.filter((l) => !f || [l.empresa_nome, l.cnpj, l.usuario_nome, l.usuario_email]
        .concat(l.empresas.map((e) => e.nome)).join(' ').toLowerCase().includes(f));
      alvo.querySelector('#lista-empresas').innerHTML = UI.tabela({
        colunas: [
          { titulo: 'Empresa', valor: (l) => `<div class="forte">${UI.escapar(l.empresa_nome)}</div>
              <div class="mini">${UI.escapar(l.cnpj || 'sem CNPJ')}${l.empresas.length > 1 ? ` · +${l.empresas.length - 1} empresa(s)` : ''}</div>` },
          { titulo: 'Responsável', valor: (l) => `${UI.escapar(l.usuario_nome)}
              <div class="mini">${UI.escapar(l.usuario_email)}${l.usuario_telefone ? ` · ${UI.escapar(l.usuario_telefone)}` : ''}</div>` },
          { titulo: 'Situação', valor: (l) => situacao(l) },
          { titulo: 'Liberada até', valor: (l) => (l.status === 'ATIVA' && l.data_fim ? UI.data(l.data_fim)
              : l.status === 'TESTE' && l.teste_fim ? `<span class="mini">teste até ${UI.data(l.teste_fim)}</span>` : '-') },
          { titulo: 'Usuários', classe: 'centro', valor: (l) => `<span class="forte" ${l.usuarios_em_uso > l.limite_usuarios ? 'style="color:var(--vermelho)" title="Acima do limite: novos usuários ficam barrados"' : ''}>${l.usuarios_em_uso} / ${l.limite_usuarios}</span>
              <div class="mini">${l.limite_personalizado ? 'limite definido por você' : 'padrão do plano'}</div>` },
          { titulo: 'Cadastro', valor: (l) => UI.data(l.criado_em) },
          { titulo: 'Ações', classe: 'centro', valor: (l) => {
            const i = dados.linhas.indexOf(l);
            return `<button class="btn btn-mini btn-verde" data-liberar="${i}">Liberar até…</button>
              ${l.status !== 'BLOQUEADA' ? `<button class="btn btn-mini btn-perigo" data-bloquear="${i}">Bloquear</button>` : ''}
              <button class="btn btn-mini" data-limite="${i}">Limite</button>
              <button class="btn btn-mini" data-usuarios="${i}">Usuários (${l.usuarios.length})</button>`;
          } },
        ],
        linhas,
        vazio: f ? 'Nenhuma empresa encontrada para a busca.' : 'Nenhuma empresa cadastrada ainda.',
      });
      const ligar = (attr, fn) => alvo.querySelectorAll(`[data-${attr}]`).forEach((b) => {
        b.onclick = () => fn(dados.linhas[Number(b.dataset[attr])]);
      });
      ligar('liberar', (l) => Assinaturas.liberarEmpresa(l, somarDias));
      ligar('bloquear', (l) => Assinaturas.bloquearEmpresa(l));
      ligar('limite', (l) => Assinaturas.limiteEmpresa(l));
      ligar('usuarios', (l) => Assinaturas.usuariosEmpresa(l));
    };
    desenhar();
    alvo.querySelector('#busca-empresa').oninput = (e) => desenhar(e.target.value);
  },

  liberarEmpresa(l, somarDias) {
    const atual = l.status === 'ATIVA' && l.data_fim && l.data_fim >= UI.hoje() ? l.data_fim : '';
    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <p style="margin-top:0">Liberar <b>${UI.escapar(l.empresa_nome)}</b> até o dia escolhido.
        No dia seguinte o acesso bloqueia sozinho.</p>
      <div class="linha-campos">
        ${UI.campo('Liberado até *', `<input type="date" name="ate" id="liberar-ate" min="${UI.hoje()}" value="${atual || somarDias(30)}">`)}
        ${UI.campo('Observação interna', `<input name="observacao" placeholder="ex.: Pix de 16/09 — semestral" value="${UI.escapar(l.observacao_admin || '')}">`)}
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
        ${[['+30 dias', 30], ['+6 meses', 182], ['+1 ano', 365]].map(([t, d]) =>
          `<button type="button" class="btn btn-mini" data-dias="${d}">${t}</button>`).join('')}
      </div>`;
    corpo.querySelectorAll('[data-dias]').forEach((b) => {
      b.onclick = () => { corpo.querySelector('#liberar-ate').value = somarDias(Number(b.dataset.dias)); };
    });
    UI.abrirModal({
      titulo: 'Liberar acesso da empresa',
      corpo,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        { rotulo: 'Liberar', classe: 'btn-verde', acao: async () => {
          const d = UI.lerFormulario(corpo);
          if (!d.ate) return UI.erro('Escolha até que dia o acesso fica liberado.');
          try {
            await Api.post(`/api/admin/empresas/${l.id}/acesso`, { acao: 'LIBERAR', ate: d.ate, observacao: d.observacao });
            UI.fecharModal();
            UI.sucesso(`Empresa liberada até ${UI.data(d.ate)}.`);
            Assinaturas.empresas();
          } catch (e) { UI.erro(e.message); }
        } },
      ],
    });
  },

  async bloquearEmpresa(l) {
    if (!(await UI.confirmar(`Bloquear agora o acesso de ${l.empresa_nome}? Todos os usuários dela `
      + 'deixam de entrar até você liberar de novo. Os dados ficam guardados.', 'Bloquear'))) return;
    try {
      await Api.post(`/api/admin/empresas/${l.id}/acesso`, { acao: 'BLOQUEAR' });
      UI.sucesso('Empresa bloqueada.');
      Assinaturas.empresas();
    } catch (e) { UI.erro(e.message); }
  },

  limiteEmpresa(l) {
    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <p style="margin-top:0"><b>${UI.escapar(l.empresa_nome)}</b> usa hoje
        <b>${l.usuarios_em_uso}</b> usuário(s). O padrão do plano é <b>${l.limite_padrao}</b>.</p>
      <div class="linha-campos">
        ${UI.campo('Limite de usuários', `<input type="number" name="limite" min="1" max="500" value="${l.limite_personalizado ? l.limite_usuarios : ''}" placeholder="${l.limite_padrao} (padrão)">`,
          'deixe em branco para voltar ao padrão do plano')}
      </div>`;
    UI.abrirModal({
      titulo: 'Limite de usuários',
      corpo,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        { rotulo: 'Salvar', classe: 'btn-primario', acao: async () => {
          const d = UI.lerFormulario(corpo);
          try {
            const r = await Api.post(`/api/admin/empresas/${l.id}/limite`, { limite: d.limite || null });
            UI.fecharModal();
            UI.sucesso(`Limite de ${r.limite_usuarios} usuário(s) salvo.`);
            Assinaturas.empresas();
          } catch (e) { UI.erro(e.message); }
        } },
      ],
    });
  },

  usuariosEmpresa(l) {
    const hoje = UI.hoje();
    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <p style="margin-top:0">Usuários de <b>${UI.escapar(l.empresa_nome)}</b> —
        ${l.usuarios_em_uso} de ${l.limite_usuarios} em uso.
        Deixe a data em branco para não ter prazo. Depois da data o usuário não entra mais.</p>
      ${UI.tabela({
        colunas: [
          { titulo: 'Usuário', valor: (u) => `<div class="forte">${UI.escapar(u.nome)}${u.dono ? ' <span class="mini">(responsável)</span>' : ''}</div>
              <div class="mini">${UI.escapar(u.email)} · ${UI.escapar(u.perfil)}</div>` },
          { titulo: 'Situação', valor: (u) => (u.perfil === 'MASTER' ? '<span class="tag tag-aberto">Administrador do site</span>'
              : !u.ativo ? '<span class="tag tag-vencido">Bloqueado</span>'
              : u.vencido ? '<span class="tag tag-vencido">Prazo vencido</span>'
              : '<span class="tag tag-pago">Liberado</span>') },
          { titulo: 'Acesso até', valor: (u) => (u.perfil === 'MASTER' ? '-'
              : `<input type="date" data-ate="${u.id}" value="${u.acesso_ate || ''}" min="${hoje}" style="min-width:140px">`) },
          { titulo: 'Liberado', classe: 'centro', valor: (u) => (u.perfil === 'MASTER' ? '-'
              : `<input type="checkbox" data-ativo="${u.id}" ${u.ativo ? 'checked' : ''} style="width:20px;height:20px">`) },
          { titulo: '', classe: 'centro', valor: (u) => (u.perfil === 'MASTER' ? ''
              : `<button class="btn btn-mini btn-primario" data-salvar-usuario="${u.id}">Salvar</button>`) },
        ],
        linhas: l.usuarios,
        vazio: 'Nenhum usuário nesta empresa.',
      })}`;
    corpo.querySelectorAll('[data-salvar-usuario]').forEach((b) => {
      b.onclick = async () => {
        const id = b.dataset.salvarUsuario;
        const ate = corpo.querySelector(`[data-ate="${id}"]`).value || null;
        const ativo = corpo.querySelector(`[data-ativo="${id}"]`).checked;
        try {
          await Api.post(`/api/admin/usuarios/${id}/acesso`, { ativo, acesso_ate: ate });
          UI.sucesso(ativo ? (ate ? `Usuário liberado até ${UI.data(ate)}.` : 'Usuário liberado sem prazo.') : 'Usuário bloqueado.');
        } catch (e) { UI.erro(e.message); }
      };
    });
    UI.abrirModal({
      titulo: 'Usuários da empresa',
      corpo,
      largo: true,
      botoes: [{ rotulo: 'Fechar', acao: () => { UI.fecharModal(); Assinaturas.empresas(); } }],
    });
  },

  /* --------------------------------------------------- configurações do site */
  async configuracoes() {
    const alvo = document.getElementById('pagina');
    const dados = await Api.get('/api/admin/configuracoes');
    const grupos = {
      'Identidade do site': ['nome_produto', 'slogan', 'empresa_titular'],
      'Contato exibido no site': ['contato_whatsapp', 'contato_email'],
      'Recebimento por Pix': ['pix_chave', 'pix_titular', 'pix_banco', 'pix_cidade', 'aviso_pagamento'],
      'Faixa de cotações e painel Mercado do Café': ['cotacoes_ativas', 'cotacoes_minutos', 'mercado_minutos',
        'noticias_minutos', 'mercado_agnocafe'],
      'Planos e teste': ['plano_semestral_valor', 'plano_semestral_meses', 'plano_anual_valor',
        'plano_anual_meses', 'horas_teste'],
      'Consulta de CNPJ (API do governo)': ['cnpj_provedor', 'cnpj_tipo_consulta', 'cnpj_endpoint',
        'cnpj_consumer_key', 'cnpj_consumer_secret', 'cnpj_cpf_usuario', 'cnpj_incluir_socios'],
      'Consulta de CEP (Correios)': ['cep_provedor', 'cep_endpoint', 'cep_usuario', 'cep_senha',
        'cep_cartao_postagem'],
    };
    const opcoes = {
      cnpj_provedor: ['AUTO', 'CONECTA_GOV', 'BRASILAPI', 'DESATIVADO'],
      cnpj_tipo_consulta: ['basica', 'qsa', 'empresa'],
      cnpj_incluir_socios: ['1', '0'],
      cotacoes_ativas: ['1', '0'],
      mercado_agnocafe: ['1', '0'],
      cep_provedor: ['AUTO', 'CORREIOS', 'VIACEP', 'BRASILAPI', 'DESATIVADO'],
    };
    const sensiveis = ['cnpj_consumer_secret', 'cep_senha'];

    const bloco = (titulo, chaves) => `
      <div class="cartao">
        <div class="cartao-cabecalho"><h3>${UI.escapar(titulo)}</h3></div>
        <div class="cartao-corpo linha-campos">
          ${chaves.map((c) => UI.campo(
            c.replace(/^(cnpj|cep)_/, '').replaceAll('_', ' ').replace(/^\w/, (l) => l.toUpperCase()),
            opcoes[c]
              ? UI.select(c, opcoes[c].map((v) => ({ valor: v, rotulo: v })),
                  dados.valores[c] ?? '', { vazio: false })
              : `<input type="${sensiveis.includes(c) ? 'password' : 'text'}" name="${c}" value="${UI.escapar(dados.valores[c] ?? '')}">`,
            dados.descricoes[c],
          )).join('')}
        </div>
      </div>`;

    alvo.innerHTML = `
      <form id="form-config">
        <div class="cartao"><div class="cartao-corpo espaco">
          <div class="mini">Estes dados aparecem no site e na tela de pagamento dos assinantes.</div>
          <button type="button" class="btn btn-primario direita" id="btn-salvar-config">Salvar configurações</button>
        </div></div>
        ${Object.entries(grupos).map(([t, c]) => bloco(t, c)).join('')}
      </form>`;

    alvo.querySelector('#btn-salvar-config').onclick = async () => {
      const valores = UI.lerFormulario(alvo.querySelector('#form-config'));
      try {
        await Api.put('/api/admin/configuracoes', { valores });
        UI.sucesso('Configurações salvas.');
        Site.info = null;
      } catch (e) {
        UI.erro(e.message);
      }
    };
  },
};
