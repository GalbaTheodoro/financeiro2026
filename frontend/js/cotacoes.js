/* Faixa de cotações do café (NY, Londres, B3) e moedas, passando no rodapé.
   Aparece no site e dentro do sistema. Busca /api/publico/cotacoes a cada 5 minutos;
   o servidor guarda as cotações e só consulta as fontes de 10 em 10 minutos. */
const Cotacoes = {
  INTERVALO: 5 * 60 * 1000,
  dados: null,

  iniciar() {
    if (document.getElementById('faixa-cotacoes')) return;
    const faixa = document.createElement('div');
    faixa.id = 'faixa-cotacoes';
    faixa.className = 'faixa-cotacoes oculto';
    faixa.setAttribute('role', 'marquee');
    faixa.setAttribute('aria-label', 'Cotações do café e das moedas');
    faixa.innerHTML = '<div class="faixa-trilho"><div class="faixa-conteudo"></div></div>';
    document.body.appendChild(faixa);
    Cotacoes.atualizar();
    setInterval(Cotacoes.atualizar, Cotacoes.INTERVALO);
    let espera;
    window.addEventListener('resize', () => {
      clearTimeout(espera);
      espera = setTimeout(() => Cotacoes.desenhar(), 250);
    });
  },

  async atualizar() {
    try {
      const resposta = await fetch('/api/publico/cotacoes');
      if (!resposta.ok) throw new Error(resposta.status);
      const dados = await resposta.json();
      if (!dados.ativo || !dados.grupos || !dados.grupos.length) {
        Cotacoes.esconder();
        return;
      }
      Cotacoes.dados = dados;
      Cotacoes.desenhar();
    } catch {
      if (!Cotacoes.dados) Cotacoes.esconder();  // sem nada para mostrar
    }
  },

  esconder() {
    document.getElementById('faixa-cotacoes')?.classList.add('oculto');
    document.body.classList.remove('com-cotacoes');
  },

  numero(valor, casas) {
    return Number(valor).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
  },

  casas(grupo, item) {
    if (grupo.chave === 'londres') return 0;
    if (grupo.chave === 'moedas') return item.contrato === 'DXY' ? 2 : 4;
    return 2;
  },

  item(grupo, i) {
    const casas = Cotacoes.casas(grupo, i);
    const v = Number(i.variacao || 0);
    const classe = v > 0 ? 'sobe' : v < 0 ? 'desce' : 'igual';
    const seta = v > 0 ? '▲' : v < 0 ? '▼' : '■';
    const casasVar = i.tipo_variacao === 'pontos' && grupo.chave === 'londres' ? 0 : casas;
    const variacao = `${v > 0 ? '+' : ''}${Cotacoes.numero(v, i.tipo_variacao === '%' ? 2 : casasVar)}${i.tipo_variacao === '%' ? '%' : ''}`;
    return `<span class="faixa-item"><span class="faixa-contrato">${UI.escapar(i.contrato)}</span>
      <b>${Cotacoes.numero(i.cotacao, casas)}</b>
      <span class="faixa-var ${classe}">${seta} ${variacao}</span></span>`;
  },

  bloco(g) {
    return `<span class="faixa-grupo">
      <span class="faixa-titulo">${UI.escapar(g.titulo)}${g.unidade ? ` <small>${UI.escapar(g.unidade)}</small>` : ''}</span>
      ${g.itens.map((i) => Cotacoes.item(g, i)).join('')}
      <span class="faixa-ref">${UI.escapar(g.atrasado ? 'último valor disponível' : (g.referencia || ''))}</span>
    </span>`;
  },

  desenhar() {
    const dados = Cotacoes.dados;
    const faixa = document.getElementById('faixa-cotacoes');
    if (!dados || !faixa) return;
    let hora = '';
    if (dados.atualizado_em) {
      hora = new Date(dados.atualizado_em).toLocaleString('pt-BR', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
      });
    }
    const fontes = [...new Set(dados.grupos.map((g) => g.fonte))].join(' · ');
    const uma = `${dados.grupos.map(Cotacoes.bloco).join('')}
      <span class="faixa-grupo faixa-rodape">Atualizado ${UI.escapar(hora)} · Fontes: ${UI.escapar(fontes)}</span>`;
    const conteudo = faixa.querySelector('.faixa-conteudo');
    conteudo.innerHTML = `<span class="faixa-copia">${uma}</span><span class="faixa-copia" aria-hidden="true">${uma}</span>`;
    faixa.classList.remove('oculto');
    document.body.classList.add('com-cotacoes');
    // velocidade constante (~70 px por segundo), qualquer que seja o tamanho do texto
    const largura = conteudo.querySelector('.faixa-copia').scrollWidth;
    conteudo.style.animationDuration = `${Math.max(20, Math.round(largura / 70))}s`;
  },
};

document.addEventListener('DOMContentLoaded', Cotacoes.iniciar);
