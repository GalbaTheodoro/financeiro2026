/* Componentes e utilitários de interface. */
const UI = {
  /* ------------------------------------------------------------ formatação */
  moeda(v, mostrarZero = true) {
    const n = Number(v || 0);
    if (!n && !mostrarZero) return '';
    return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  },
  numero(v, casas = 2) {
    return Number(v || 0).toLocaleString('pt-BR', {
      minimumFractionDigits: casas, maximumFractionDigits: casas,
    });
  },
  data(iso) {
    if (!iso) return '';
    const [a, m, d] = String(iso).slice(0, 10).split('-');
    return `${d}/${m}/${a}`;
  },
  hoje() {
    return new Date().toISOString().slice(0, 10);
  },
  primeiroDiaMes() {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10);
  },
  ultimoDiaMes() {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth() + 1, 0).toISOString().slice(0, 10);
  },
  escapar(t) {
    return String(t ?? '').replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  },
  classeValor(v) {
    return Number(v) < 0 ? 'negativo' : Number(v) > 0 ? 'positivo' : 'neutro';
  },
  tagStatus(status, vencida) {
    if (vencida && ['ABERTO', 'PARCIAL'].includes(status)) {
      return '<span class="tag tag-vencido">Vencido</span>';
    }
    const rotulos = {
      ABERTO: 'Aberto', PARCIAL: 'Parcial', PAGO: 'Pago',
      QUITADO: 'Quitado', CANCELADO: 'Cancelado',
    };
    return `<span class="tag tag-${String(status).toLowerCase()}">${rotulos[status] || status}</span>`;
  },

  /* ----------------------------------------------------------------- avisos */
  aviso(mensagem, tipo = 'info') {
    const caixa = document.createElement('div');
    caixa.className = `aviso ${tipo}`;
    caixa.textContent = mensagem;
    document.getElementById('avisos').appendChild(caixa);
    setTimeout(() => caixa.remove(), tipo === 'erro' ? 7000 : 3800);
  },
  sucesso(m) { UI.aviso(m, 'sucesso'); },
  erro(m) { UI.aviso(m, 'erro'); },

  /* ------------------------------------------------------------------ modal */
  /* Enquanto tem coisa digitada e não salva, a janela não fecha sozinha:
     clique fora e tecla Esc são ignorados e o "x" pergunta antes. */
  _sujo: false,          // mexeu em algum campo depois de abrir/salvar
  _aoSalvar: null,       // o que o "Salvar e sair" deve chamar

  abrirModal({ titulo, corpo, botoes = [], largo = false, aoSalvar = null }) {
    UI.tirarPerguntaSaida();
    document.getElementById('modal-titulo').textContent = titulo;
    const areaCorpo = document.getElementById('modal-corpo');
    areaCorpo.innerHTML = '';
    if (typeof corpo === 'string') areaCorpo.innerHTML = corpo;
    else areaCorpo.appendChild(corpo);

    UI._sujo = false;
    UI._aoSalvar = aoSalvar;
    const sujar = () => { UI._sujo = true; };
    areaCorpo.oninput = sujar;
    areaCorpo.onchange = sujar;

    UI.trocarBotoes(botoes, areaCorpo);
    document.getElementById('modal').classList.toggle('largo', largo);
    document.getElementById('modal-fundo').classList.remove('oculto');
    const primeiro = areaCorpo.querySelector('input,select,textarea');
    if (primeiro) setTimeout(() => primeiro.focus(), 60);
    return areaCorpo;
  },

  /** Chamar depois de gravar: a janela volta a poder ser fechada sem aviso. */
  modalSalvo() { UI._sujo = false; },

  /** Tem formulário aberto com alteração ainda não gravada? */
  modalComEdicao() {
    const fundo = document.getElementById('modal-fundo');
    if (!fundo || fundo.classList.contains('oculto')) return false;
    return UI._sujo;
  },

  /** O "x" e o Esc passam por aqui: se tem coisa não salva, pergunta antes. */
  tentarFecharModal() {
    if (!UI.modalComEdicao()) return UI.fecharModal();
    return UI.perguntarSaida();
  },

  tirarPerguntaSaida() {
    document.getElementById('pergunta-saida')?.remove();
  },

  /** Painel por cima do formulário — o que está digitado continua intacto atrás. */
  perguntarSaida() {
    if (document.getElementById('pergunta-saida')) return;
    const caixa = document.createElement('div');
    caixa.id = 'pergunta-saida';
    caixa.className = 'pergunta-saida';
    caixa.innerHTML = `
      <div class="pergunta-saida-caixa">
        <h4>Você alterou dados e ainda não salvou.</h4>
        <p class="mini">Se sair agora, o que foi digitado se perde.</p>
        <div class="pergunta-saida-botoes">
          <button type="button" class="btn btn-primario" id="saida-continuar">Continuar editando</button>
          ${UI._aoSalvar ? '<button type="button" class="btn" id="saida-salvar">Salvar e sair</button>' : ''}
          <button type="button" class="btn btn-perigo" id="saida-descartar">Sair sem salvar</button>
        </div>
      </div>`;
    document.getElementById('modal').appendChild(caixa);
    caixa.querySelector('#saida-continuar').onclick = () => UI.tirarPerguntaSaida();
    const salvar = caixa.querySelector('#saida-salvar');
    if (salvar) {
      salvar.onclick = async () => {
        UI.tirarPerguntaSaida();
        const acao = UI._aoSalvar;
        if (acao) await acao();
      };
    }
    caixa.querySelector('#saida-descartar').onclick = () => {
      UI.tirarPerguntaSaida();
      UI.fecharModal();
    };
  },
  /** Redesenha os botões do rodapé do modal — usado pelo formulário em etapas. */
  trocarBotoes(botoes, areaCorpo) {
    const rodape = document.getElementById('modal-rodape');
    const corpo = areaCorpo || document.getElementById('modal-corpo');
    rodape.innerHTML = '';
    (botoes || []).forEach((b) => {
      const botao = document.createElement('button');
      botao.className = `btn ${b.classe || ''}`;
      botao.textContent = b.rotulo;
      botao.onclick = () => b.acao(corpo);
      rodape.appendChild(botao);
    });
  },

  fecharModal() {
    UI.tirarPerguntaSaida();
    UI._sujo = false;
    UI._aoSalvar = null;
    document.getElementById('modal-fundo').classList.add('oculto');
  },
  async confirmar(mensagem, rotulo = 'Confirmar') {
    return new Promise((resolve) => {
      UI.abrirModal({
        titulo: 'Confirmação',
        corpo: `<p style="margin:0">${UI.escapar(mensagem)}</p>`,
        botoes: [
          { rotulo: 'Cancelar', acao: () => { UI.fecharModal(); resolve(false); } },
          { rotulo, classe: 'btn-perigo', acao: () => { UI.fecharModal(); resolve(true); } },
        ],
      });
    });
  },

  /* ---------------------------------------------------------------- widgets */
  select(nome, opcoes, valor, extras = {}) {
    const vazio = extras.vazio === undefined ? 'Selecione...' : extras.vazio;
    const itens = opcoes
      .map((o) => `<option value="${UI.escapar(o.valor)}" ${String(o.valor) === String(valor) ? 'selected' : ''}>${UI.escapar(o.rotulo)}</option>`)
      .join('');
    return `<select name="${nome}" ${extras.obrigatorio ? 'required' : ''} ${extras.attr || ''}>
      ${vazio === false ? '' : `<option value="">${UI.escapar(vazio)}</option>`}${itens}</select>`;
  },
  opcoesContas(tipos) {
    return Api.contasAnaliticas(tipos).map((c) => ({ valor: c.id, rotulo: `${c.codigo} — ${c.nome}` }));
  },
  opcoesCentros() {
    return Api.centrosAtivos().map((c) => ({ valor: c.id, rotulo: `${c.codigo} — ${c.nome}` }));
  },
  opcoesBancos() {
    return Api.bancosAtivos().map((b) => ({ valor: b.id, rotulo: b.nome }));
  },
  opcoesOperacoes(natureza) {
    return Api.operacoesAtivas(natureza).map((o) => ({ valor: o.id, rotulo: `${o.codigo} — ${o.nome}` }));
  },
  opcoesParceiros(tipo) {
    return Api.parceirosPorTipo(tipo).map((p) => ({ valor: p.id, rotulo: p.nome }));
  },

  campo(rotulo, conteudo, dica) {
    return `<label class="campo">${UI.escapar(rotulo)}${dica ? `<span class="dica">${UI.escapar(dica)}</span>` : ''}${conteudo}</label>`;
  },

  /* ---------------------------------------------------------------- tabelas */
  tabela({ colunas, linhas, rodape, vazio = 'Nenhum registro encontrado.', aoClicar }) {
    if (!linhas.length) return `<div class="vazio">${UI.escapar(vazio)}</div>`;
    const cabecalho = colunas
      .map((c) => `<th class="${c.classe || ''}">${UI.escapar(c.titulo)}</th>`)
      .join('');
    const corpo = linhas
      .map((linha, i) => {
        const celulas = colunas
          .map((c) => `<td class="${c.classe || ''}" data-rotulo="${UI.escapar(c.titulo)}">${c.valor(linha, i)}</td>`)
          .join('');
        return `<tr ${aoClicar ? `data-indice="${i}" style="cursor:pointer"` : ''}>${celulas}</tr>`;
      })
      .join('');
    const pe = rodape
      ? `<tfoot><tr>${colunas.map((c) => `<td class="${c.classe || ''}">${rodape[c.chave] ?? ''}</td>`).join('')}</tr></tfoot>`
      : '';
    return `<div class="tabela-wrap tabela-cartoes"><table><thead><tr>${cabecalho}</tr></thead><tbody>${corpo}</tbody>${pe}</table></div>`;
  },

  /* -------------------------------------------------------- exportar / imprimir */
  exportarCSV(nomeArquivo, cabecalhos, linhas) {
    const escapar = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const conteudo = [cabecalhos.map(escapar).join(';')]
      .concat(linhas.map((l) => l.map(escapar).join(';')))
      .join('\r\n');
    const blob = new Blob(['﻿' + conteudo], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${nomeArquivo}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  },
  exportarTabela(nomeArquivo, seletor) {
    const tabela = document.querySelector(seletor);
    if (!tabela) return UI.erro('Nada para exportar.');
    const linhas = [...tabela.querySelectorAll('tr')].map((tr) =>
      [...tr.querySelectorAll('th,td')].map((c) => c.innerText.trim()));
    UI.exportarCSV(nomeArquivo, linhas[0], linhas.slice(1));
  },
  imprimir() { window.print(); },

  /* ----------------------------------------------------------------- gráfico */
  graficoBarras(dados, { max } = {}) {
    const teto = max || Math.max(1, ...dados.flatMap((d) => [d.entradas, d.saidas]));
    const colunas = dados
      .map((d) => `
        <div class="grafico-col">
          <div class="grafico-barra">
            <div style="background:var(--verde);height:${(d.entradas / teto) * 100}%" title="Entradas: ${UI.moeda(d.entradas)}"></div>
            <div style="background:var(--vermelho);height:${(d.saidas / teto) * 100}%" title="Saídas: ${UI.moeda(d.saidas)}"></div>
          </div>
          <div class="grafico-rotulo">${UI.escapar(d.periodo)}</div>
        </div>`)
      .join('');
    return `<div class="grafico-barras">${colunas}</div>
      <div class="legenda"><span class="ent">Entradas</span><span class="sai">Saídas</span></div>`;
  },

  /* -------------------------------------------------------------- formulário */
  lerFormulario(elemento) {
    const dados = {};
    elemento.querySelectorAll('input,select,textarea').forEach((campo) => {
      if (!campo.name) return;
      if (campo.type === 'checkbox') dados[campo.name] = campo.checked;
      else if (campo.type === 'number') dados[campo.name] = campo.value === '' ? null : Number(campo.value);
      else dados[campo.name] = campo.value === '' ? null : campo.value;
    });
    return dados;
  },
};
