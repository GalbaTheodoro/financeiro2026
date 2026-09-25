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

    /* Cada plano é um bloco: o que ele libera e, dentro, os dois prazos. O que
       muda de um plano para o outro não é o prazo, é o que a conta pode usar —
       por isso o prazo vem depois, dentro do plano escolhido. */
    const escolha = planos
      .map((op) => `
        <div class="plano-bloco ${op.prazos.some((z) => z.codigo === plano.codigo) ? 'ativo' : ''}">
          <div class="plano-bloco-topo">
            <div>
              <div class="forte">${UI.escapar(op.nome)}</div>
              <div class="mini">${UI.escapar(op.para)}</div>
            </div>
            ${op.destaque ? '<span class="tag tag-pago">completo</span>' : ''}
          </div>
          <ul class="plano-modulos">
            ${op.modulos.map((m) => `<li>${UI.escapar(m.nome)}</li>`).join('')}
          </ul>
          <div class="planos-opcao">
            ${op.prazos.map((z) => `
              <label class="plano-opcao ${z.codigo === plano.codigo ? 'ativo' : ''}">
                <input type="radio" name="plano" value="${z.codigo}" ${z.codigo === plano.codigo ? 'checked' : ''}>
                <div>
                  <div class="forte">${UI.escapar(z.rotulo)}</div>
                  <div class="mini">${z.meses} meses · ${UI.moeda(z.valor_mes)}/mês</div>
                </div>
                <div class="plano-opcao-valor">${UI.moeda(z.valor)}</div>
              </label>`).join('')}
          </div>
        </div>`)
      .join('');

    const areaPix = p.configurado
      ? `
        <div class="pix-grade">
          <div class="pix-qr">${p.qrcode_svg || '<div class="mini">QR Code indisponível — use a chave ao lado.</div>'}</div>
          <div>
            ${p.cupom_desconto
              ? `<div class="pix-linha"><span class="mini">Valor do plano</span>
                   <span class="riscado">${UI.moeda(p.valor_cheio)}</span></div>
                 <div class="pix-linha"><span class="mini">Cupom ${UI.escapar(p.cupom)}</span>
                   <b class="positivo">− ${UI.moeda(p.cupom_desconto)}</b></div>
                 <div class="pix-linha"><span class="mini">Valor a pagar</span>
                   <b>${UI.moeda(p.valor_cobranca)}</b></div>`
              : `<div class="pix-linha"><span class="mini">Valor</span><b>${UI.moeda(p.valor_cobranca)}</b></div>`}
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
      <div class="planos-blocos">${escolha}</div>`}

      ${p.configurado ? `
      <div class="cupom-caixa">
        <div>
          <div class="forte">Tem um cupom de desconto?</div>
          <div class="mini">${p.cupom
            ? `Cupom <b>${UI.escapar(p.cupom)}</b> aplicado — ${Assinaturas.porcento(p.cupom_percentual)} de desconto nesta cobrança.`
            : 'Digite o código que você recebeu e o valor do Pix muda na hora.'}</div>
        </div>
        <div class="cupom-campos">
          <input name="cupom" placeholder="ex.: PRIMAVERA10" value="${UI.escapar(p.cupom || '')}"
                 autocapitalize="characters" spellcheck="false">
          <button class="btn btn-mini" id="btn-aplicar-cupom">Aplicar</button>
          ${p.cupom ? '<button class="btn btn-mini" id="btn-tirar-cupom">Tirar</button>' : ''}
        </div>
      </div>` : ''}

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
          // o plano decide o menu: recarrega a conta e redesenha a barra lateral
          Estado.usuario = await Api.get('/api/auth/me');
          App.desenharMenu();
          UI.sucesso('Plano atualizado.');
          aoAtualizar();
        } catch (e) {
          UI.erro(e.message);
        }
      };
    });

    /* O cupom: o servidor devolve o Pix já refeito, então basta redesenhar. */
    const mandarCupom = async (codigo) => {
      try {
        const r = await Api.post('/api/assinatura/cupom', { codigo });
        UI.sucesso(r.mensagem);
        aoAtualizar();
      } catch (e) {
        UI.erro(e.message);
      }
    };
    raiz.querySelector('#btn-aplicar-cupom')?.addEventListener('click', () =>
      mandarCupom(raiz.querySelector('[name=cupom]')?.value || ''));
    raiz.querySelector('#btn-tirar-cupom')?.addEventListener('click', () => mandarCupom(''));
    raiz.querySelector('[name=cupom]')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); mandarCupom(e.target.value); }
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
    Assinaturas._planos = dados.planos || [];
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
        { titulo: 'Plano', valor: (a) => `${UI.escapar(a.plano_nome || a.plano)}
            <div class="mini">${UI.escapar((a.plano_periodo || '').toLowerCase())} · ${UI.moeda(a.valor)}</div>
            ${a.cupom ? `<div class="mini positivo">cupom ${UI.escapar(a.cupom)}:
              paga ${UI.moeda(a.valor_cobranca)}</div>` : ''}
            ${!a.cupom && a.cupom_usado_codigo
              ? `<div class="mini">entrou com o cupom ${UI.escapar(a.cupom_usado_codigo)}</div>` : ''}` },
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

  /** Os oito códigos (quatro planos x dois prazos) para os selects da administração. */
  opcoesDePlano() {
    return (Assinaturas._planos || []).flatMap((p) => p.prazos.map((z) => ({
      valor: z.codigo,
      rotulo: `${p.nome} ${z.rotulo.toLowerCase()} — ${UI.moeda(z.valor)}`,
    })));
  },

  confirmar(assinatura) {
    const meses = (assinatura.plano_periodo || assinatura.plano) === 'ANUAL' ? 12 : 6;
    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <p>Confirmar o recebimento do Pix de <b>${UI.escapar(assinatura.usuario_nome)}</b>
         no valor de <b>${UI.moeda(assinatura.valor_cobranca ?? assinatura.valor)}</b>?</p>
      ${assinatura.cupom ? `<div class="ok-caixa" style="margin-bottom:12px">
        Esta conta aplicou o cupom <b>${UI.escapar(assinatura.cupom)}</b>:
        ${UI.moeda(assinatura.cupom_desconto)} de desconto sobre ${UI.moeda(assinatura.valor)}.
        O cupom é gasto agora — a renovação volta ao preço cheio.
      </div>` : ''}
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

  /** "P3_ANUAL" -> 3. Código antigo (só SEMESTRAL/ANUAL) responde 4, como no servidor. */
  nivelDoPlano(codigo) {
    const achado = String(codigo || '').match(/^P(\d)_/);
    return achado ? Number(achado[1]) : 4;
  },

  /** O catálogo de menus, buscado uma vez por sessão. */
  async gradeDeMenus() {
    if (!Assinaturas._grade) Assinaturas._grade = await Api.get('/api/admin/modulos');
    return Assinaturas._grade;
  },

  async gerenciar(assinatura) {
    const grade = await Assinaturas.gradeDeMenus();
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
        ${UI.campo('Plano', UI.select('plano', Assinaturas.opcoesDePlano(),
          assinatura.plano, { vazio: false }), 'o plano decide quais telas a conta enxerga')}
        ${UI.campo('Horas de teste', '<input type="number" name="horas_teste" placeholder="ex.: 48">',
          'preenchido apenas ao reabrir um teste')}
        ${UI.campo('Observação interna', `<input name="observacao" value="${UI.escapar(assinatura.observacao_admin || '')}">`)}
      </div>

      <div class="cartao" style="margin-top:14px">
        <div class="cartao-cabecalho">
          <div><h3>Acessos combinados</h3>
            <div class="mini">marque o que <b>esta conta</b> enxerga. O plano e o valor
              cobrado não mudam — serve para a negociação: fechou o Plano 1 e ficou
              combinado dar a Nota fiscal, então marque a Nota fiscal aqui.</div></div>
        </div>
        <div class="cartao-corpo sem-padding">
          <div class="tabela-wrap"><table><thead><tr>
            <th>Menu</th><th class="centro">Enxerga</th><th>De onde vem</th>
          </tr></thead><tbody id="acessos-conta"></tbody></table></div>
        </div>
      </div>`;

    /* A linha mostra a origem do acesso, senão o administrador não sabe se
       aquele "sim" vem do plano ou de uma combinação antiga. */
    const desenharAcessos = () => {
      const plano = corpo.querySelector('[name="plano"]').value;
      const nivel = Assinaturas.nivelDoPlano(plano);
      const doPlano = (grade.planos.find((p) => p.nivel === nivel) || {}).modulos || [];
      const extras = assinatura.modulos_extras || [];
      const bloqueados = assinatura.modulos_bloqueados || [];
      corpo.querySelector('#acessos-conta').innerHTML = grade.modulos.map((m) => {
        const noPlano = doPlano.includes(m.codigo);
        const marcado = noPlano ? !bloqueados.includes(m.codigo) : extras.includes(m.codigo);
        const origem = noPlano
          ? (marcado ? 'vem do plano' : '<span class="alerta">o plano dá, foi tirado desta conta</span>')
          : (marcado ? '<span class="positivo">fora do plano, liberado só para esta conta</span>'
                     : 'não está no plano');
        return `<tr>
          <td><b>${UI.escapar(m.nome)}</b><div class="mini">${UI.escapar(m.texto)}</div></td>
          <td class="centro"><input type="checkbox" name="acesso_${m.codigo}" ${marcado ? 'checked' : ''}></td>
          <td class="mini">${origem}</td>
        </tr>`;
      }).join('');
    };
    desenharAcessos();
    // trocou o plano: a coluna "de onde vem" tem de acompanhar antes de salvar
    corpo.querySelector('[name="plano"]').onchange = desenharAcessos;

    UI.abrirModal({
      titulo: `Conta de ${assinatura.usuario_nome}`,
      corpo,
      largo: true,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        {
          rotulo: 'Salvar',
          classe: 'btn-primario',
          acao: async () => {
            const d = UI.lerFormulario(corpo);
            /* As exceções são calculadas contra o plano escolhido agora, não
               contra o antigo: quem sobe de plano não fica com "extra" de um
               menu que o plano novo já dá. */
            const nivel = Assinaturas.nivelDoPlano(d.plano);
            const doPlano = (grade.planos.find((p) => p.nivel === nivel) || {}).modulos || [];
            const extras = grade.modulos
              .filter((m) => d[`acesso_${m.codigo}`] && !doPlano.includes(m.codigo))
              .map((m) => m.codigo);
            const bloqueados = grade.modulos
              .filter((m) => !d[`acesso_${m.codigo}`] && doPlano.includes(m.codigo))
              .map((m) => m.codigo);
            try {
              await Api.post(`/api/admin/assinaturas/${assinatura.id}/status`, {
                status: d.status,
                plano: d.plano,
                horas_teste: d.horas_teste ? Number(d.horas_teste) : null,
                observacao: d.observacao,
              });
              const r = await Api.post(`/api/admin/assinaturas/${assinatura.id}/modulos`, {
                extras, bloqueados,
              });
              UI.fecharModal();
              UI.sucesso(r.mensagem || 'Assinatura atualizada.');
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

  /** "20" e não "20,00"; meia porcentagem continua aparecendo: "7,5". */
  porcento(valor) {
    const n = Number(valor || 0);
    return `${UI.numero(n, n % 1 ? 2 : 0)}%`;
  },

  /* ------------------------------------------ cupons de desconto (MASTER) */
  async cupons() {
    const alvo = document.getElementById('pagina');
    alvo.innerHTML = '<div class="cartao"><div class="vazio">Carregando cupons...</div></div>';
    const dados = await Api.get('/api/admin/cupons');
    const ativos = dados.linhas.filter((c) => c.ativo).length;
    const usos = dados.linhas.reduce((s, c) => s + c.usos, 0);

    alvo.innerHTML = `
      <div class="grade g3" style="margin-bottom:16px">
        <div class="kpi destaque-verde"><div class="kpi-rotulo">Cupons ativos</div>
          <div class="kpi-valor">${ativos}</div>
          <div class="kpi-nota">valendo agora, para quem digitar</div></div>
        <div class="kpi"><div class="kpi-rotulo">Cupons cadastrados</div>
          <div class="kpi-valor">${dados.linhas.length}</div></div>
        <div class="kpi destaque-azul"><div class="kpi-rotulo">Vezes usado</div>
          <div class="kpi-valor">${usos}</div>
          <div class="kpi-nota">contas que pagaram com desconto</div></div>
      </div>
      <div class="cartao">
        <div class="cartao-cabecalho espaco">
          <div><h3>Cupons de desconto</h3>
            <div class="mini">o cliente digita o código no cadastro ou na tela de pagamento e
              o Pix já sai com o valor menor. O desconto vale na primeira cobrança;
              a renovação volta ao preço cheio.</div></div>
          <button class="btn btn-primario" id="btn-novo-cupom">Novo cupom</button>
        </div>
        <div class="cartao-corpo sem-padding" id="lista-cupons"></div>
      </div>`;

    alvo.querySelector('#lista-cupons').innerHTML = UI.tabela({
      colunas: [
        { titulo: 'Código', chave: 'codigo',
          valor: (c) => `<b>${UI.escapar(c.codigo)}</b>` },
        { titulo: 'Para que serve', valor: (c) => UI.escapar(c.descricao || '-') },
        { titulo: 'Desconto', classe: 'centro',
          valor: (c) => `<b>${Assinaturas.porcento(c.percentual)}</b>` },
        { titulo: 'Já usado', classe: 'centro', valor: (c) => `${c.usos} vez(es)` },
        { titulo: 'Situação', classe: 'centro', valor: (c) =>
          `<span class="tag ${c.ativo ? 'tag-pago' : 'tag-vencido'}">${c.ativo ? 'ativo' : 'desligado'}</span>` },
        { titulo: 'Ações', classe: 'centro', valor: (c, i) => `
            <button class="btn btn-mini" data-editar="${i}">Editar</button>
            <button class="btn btn-mini" data-ligar="${i}">${c.ativo ? 'Desligar' : 'Ligar'}</button>
            <button class="btn btn-mini btn-perigo" data-apagar="${i}">Apagar</button>` },
      ],
      linhas: dados.linhas,
      vazio: 'Nenhum cupom cadastrado. Crie um e passe o código para o cliente.',
    });

    alvo.querySelector('#btn-novo-cupom').onclick = () => Assinaturas.formularioCupom(null);
    alvo.querySelectorAll('[data-editar]').forEach((b) => {
      b.onclick = () => Assinaturas.formularioCupom(dados.linhas[Number(b.dataset.editar)]);
    });
    alvo.querySelectorAll('[data-ligar]').forEach((b) => {
      b.onclick = async () => {
        const c = dados.linhas[Number(b.dataset.ligar)];
        try {
          await Api.put(`/api/admin/cupons/${c.id}`, { ativo: !c.ativo });
          UI.sucesso(c.ativo ? `Cupom ${c.codigo} desligado.` : `Cupom ${c.codigo} ligado.`);
          Assinaturas.cupons();
        } catch (e) { UI.erro(e.message); }
      };
    });
    alvo.querySelectorAll('[data-apagar]').forEach((b) => {
      b.onclick = async () => {
        const c = dados.linhas[Number(b.dataset.apagar)];
        if (!(await UI.confirmar(
          `Apagar o cupom ${c.codigo}? Quem já aplicou não perde o desconto combinado.`,
          'Apagar'))) return;
        try {
          await Api.del(`/api/admin/cupons/${c.id}`);
          UI.sucesso('Cupom apagado.');
          Assinaturas.cupons();
        } catch (e) { UI.erro(e.message); }
      };
    });
  },

  formularioCupom(cupom) {
    const novo = !cupom;
    const corpo = document.createElement('div');
    corpo.innerHTML = `
      <div class="linha-campos">
        ${UI.campo('Código *', `<input name="codigo" value="${UI.escapar(cupom?.codigo || '')}"
          placeholder="ex.: PRIMAVERA10" autocapitalize="characters" spellcheck="false"
          style="text-transform:uppercase">`, 'é o que o cliente digita — sem espaço')}
        ${UI.campo('Desconto (%) *', `<input type="number" name="percentual" step="0.01" min="0.01" max="100"
          value="${cupom ? cupom.percentual : ''}" placeholder="ex.: 10">`,
          'sobre o valor do plano escolhido')}
        ${UI.campo('Para que serve', `<input name="descricao" value="${UI.escapar(cupom?.descricao || '')}"
          placeholder="ex.: campanha da feira de setembro">`, 'anotação sua, o cliente não vê')}
        ${UI.campo('Situação', UI.select('ativo', [
          { valor: '1', rotulo: 'Ativo — valendo' },
          { valor: '0', rotulo: 'Desligado' },
        ], cupom && !cupom.ativo ? '0' : '1', { vazio: false }))}
      </div>
      <div class="ok-caixa" style="margin-top:12px">
        O desconto entra na <b>primeira cobrança</b> da conta que digitar o código. Pacote de
        usuários extra não recebe desconto.
      </div>`;

    UI.abrirModal({
      titulo: novo ? 'Novo cupom de desconto' : `Cupom ${cupom.codigo}`,
      corpo,
      botoes: [
        { rotulo: 'Cancelar', acao: () => UI.tentarFecharModal() },
        {
          rotulo: 'Salvar',
          classe: 'btn-primario',
          acao: async () => {
            const d = UI.lerFormulario(corpo);
            const corpoEnvio = {
              codigo: d.codigo, percentual: d.percentual,
              descricao: d.descricao || '', ativo: d.ativo === '1',
            };
            try {
              if (novo) await Api.post('/api/admin/cupons', corpoEnvio);
              else await Api.put(`/api/admin/cupons/${cupom.id}`, corpoEnvio);
              UI.fecharModal();
              UI.sucesso('Cupom salvo.');
              Assinaturas.cupons();
            } catch (e) { UI.erro(e.message); }
          },
        },
      ],
    });
  },

  /* --------------------------------------------------- configurações do site */
  async configuracoes() {
    const alvo = document.getElementById('pagina');
    const dados = await Api.get('/api/admin/configuracoes');
    const grade = await Api.get('/api/admin/modulos');
    const grupos = {
      'Identidade do site': ['nome_produto', 'slogan', 'empresa_titular'],
      'Contato exibido no site': ['contato_whatsapp', 'contato_email'],
      'Recebimento por Pix': ['pix_chave', 'pix_titular', 'pix_banco', 'pix_cidade', 'aviso_pagamento'],
      'Faixa de cotações e painel Mercado do Café': ['cotacoes_ativas', 'cotacoes_minutos', 'mercado_minutos',
        'noticias_minutos', 'mercado_agnocafe'],
      'Preço de cada plano': ['plano1_semestral_valor', 'plano1_anual_valor',
        'plano2_semestral_valor', 'plano2_anual_valor',
        'plano3_semestral_valor', 'plano3_anual_valor',
        'plano4_semestral_valor', 'plano4_anual_valor'],
      'Prazos e teste': ['plano_semestral_meses', 'plano_anual_meses', 'horas_teste'],
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
    /* Os preços: "plano3_anual_valor" vira "Plano 3 — anual". O que cada plano
       libera está escrito na descrição que vem do servidor. */
    const rotuloDaChave = (c) => {
      const preco = c.match(/^plano(\d)_(semestral|anual)_valor$/);
      if (preco) return `Plano ${preco[1]} — ${preco[2]}`;
      return c.replace(/^(cnpj|cep)_/, '').replaceAll('_', ' ').replace(/^\w/, (l) => l.toUpperCase());
    };

    const bloco = (titulo, chaves) => `
      <div class="cartao">
        <div class="cartao-cabecalho"><h3>${UI.escapar(titulo)}</h3></div>
        <div class="cartao-corpo linha-campos">
          ${chaves.map((c) => UI.campo(
            rotuloDaChave(c),
            opcoes[c]
              ? UI.select(c, opcoes[c].map((v) => ({ valor: v, rotulo: v })),
                  dados.valores[c] ?? '', { vazio: false })
              : `<input type="${sensiveis.includes(c) ? 'password' : 'text'}" name="${c}" value="${UI.escapar(dados.valores[c] ?? '')}">`,
            dados.descricoes[c],
          )).join('')}
        </div>
      </div>`;

    /* O quadro de menus: uma linha por menu, uma coluna por plano. É aqui que o
       Plano 1 ganha ou perde a nota fiscal, e o site e o menu de todo assinante
       daquele plano mudam junto. */
    const quadroDeMenus = () => `
      <div class="cartao">
        <div class="cartao-cabecalho">
          <div><h3>Menus de cada plano</h3>
            <div class="mini">marque o que cada plano libera — vale para todos os
              assinantes daquele plano e muda a página inicial junto</div></div>
        </div>
        <div class="cartao-corpo sem-padding">
          <div class="tabela-wrap"><table><thead><tr>
            <th>Menu</th>
            ${grade.planos.map((p) => `<th class="centro">${UI.escapar(p.nome)}</th>`).join('')}
          </tr></thead><tbody>
            ${grade.modulos.map((m) => `<tr>
              <td><b>${UI.escapar(m.nome)}</b>
                <div class="mini">${UI.escapar(m.texto)}</div>
                <div class="mini">telas: ${m.rotas.map((r) => UI.escapar(r)).join(', ') || '—'}</div></td>
              ${grade.planos.map((p) => `<td class="centro">
                <input type="checkbox" name="mod_${p.nivel}_${m.codigo}"
                  ${p.modulos.includes(m.codigo) ? 'checked' : ''}></td>`).join('')}
            </tr>`).join('')}
          </tbody></table></div>
          <div class="mini" style="padding:12px 18px">
            Plano sem nenhum menu marcado é aceito — a conta entra e só enxerga os
            Cadastros e a Minha Assinatura. Para abrir um menu <b>só para um cliente</b>,
            sem mexer no plano dele, use <b>Assinaturas → Gerenciar → Acessos combinados</b>.
          </div>
        </div>
      </div>`;

    alvo.innerHTML = `
      <form id="form-config">
        <div class="cartao"><div class="cartao-corpo espaco">
          <div class="mini">Estes dados aparecem no site e na tela de pagamento dos assinantes.</div>
          <button type="button" class="btn btn-primario direita" id="btn-salvar-config">Salvar configurações</button>
        </div></div>
        ${bloco('Preço de cada plano', grupos['Preço de cada plano'])}
        ${quadroDeMenus()}
        ${Object.entries(grupos)
          .filter(([titulo]) => titulo !== 'Preço de cada plano')
          .map(([titulo, chaves]) => bloco(titulo, chaves)).join('')}
      </form>`;

    alvo.querySelector('#btn-salvar-config').onclick = async () => {
      const valores = UI.lerFormulario(alvo.querySelector('#form-config'));
      // as caixas do quadro viram uma lista por plano: mod_1_NFE -> plano1_modulos
      grade.planos.forEach((p) => {
        valores[`plano${p.nivel}_modulos`] = grade.modulos
          .filter((m) => valores[`mod_${p.nivel}_${m.codigo}`])
          .map((m) => m.codigo).join(',');
      });
      Object.keys(valores).forEach((k) => { if (k.startsWith('mod_')) delete valores[k]; });
      try {
        await Api.put('/api/admin/configuracoes', { valores });
        UI.sucesso('Configurações salvas.');
        Site.info = null;
        Assinaturas._grade = null;  // a grade mudou: a tela Gerenciar tem de reler
        Assinaturas.configuracoes();
      } catch (e) {
        UI.erro(e.message);
      }
    };
  },
};
