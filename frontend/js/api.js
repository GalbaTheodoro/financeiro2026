/* Comunicação com a API e estado da aplicação. */
const Estado = {
  token: localStorage.getItem('fin_token') || null,
  usuario: null,
  empresaId: Number(localStorage.getItem('fin_empresa')) || null,
  empresas: [],
  cache: {},
};

async function requisicao(metodo, caminho, dados) {
  const opcoes = { method: metodo, headers: { 'Content-Type': 'application/json' } };
  if (Estado.token) opcoes.headers.Authorization = `Bearer ${Estado.token}`;
  if (dados !== undefined) opcoes.body = JSON.stringify(dados);

  const resposta = await fetch(caminho, opcoes);
  if (resposta.status === 401) {
    Api.sair();
    throw new Error('Sessão expirada. Faça login novamente.');
  }
  const texto = await resposta.text();
  let corpo = {};
  try { corpo = texto ? JSON.parse(texto) : {}; } catch { corpo = { detail: texto.slice(0, 300) }; }
  if (resposta.status === 423) {
    // usuário bloqueado pelo administrador ou com a data de acesso vencida
    const mensagem = corpo.detail || 'Seu acesso está bloqueado.';
    if (Estado.token) {
      Api.sair();
      setTimeout(() => UI.erro(mensagem), 400);
    }
    throw new Error(mensagem);
  }
  if (resposta.status === 402) {
    // conta sem assinatura válida: leva para a tela de pagamento
    const mensagem = corpo.detail || 'Assinatura inativa.';
    if (typeof Assinaturas !== 'undefined') Assinaturas.bloquear(mensagem);
    throw new Error(mensagem);
  }
  if (!resposta.ok) {
    const detalhe = corpo.detail;
    const mensagem = Array.isArray(detalhe)
      ? detalhe.map((d) => d.msg || JSON.stringify(d)).join('; ')
      : detalhe || 'Erro inesperado';
    throw new Error(mensagem);
  }
  return corpo;
}

function comParametros(caminho, params = {}) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([chave, valor]) => {
    if (valor !== null && valor !== undefined && valor !== '') q.append(chave, valor);
  });
  const query = q.toString();
  return query ? `${caminho}?${query}` : caminho;
}

const Api = {
  get: (caminho, params) => requisicao('GET', comParametros(caminho, params)),
  post: (caminho, dados) => requisicao('POST', caminho, dados),
  postQuery: (caminho, params) => requisicao('POST', comParametros(caminho, params)),
  put: (caminho, dados) => requisicao('PUT', caminho, dados),
  del: (caminho) => requisicao('DELETE', caminho),

  async login(email, senha) {
    const r = await requisicao('POST', '/api/auth/login', { email, senha });
    Estado.token = r.token;
    Estado.usuario = r.usuario;
    localStorage.setItem('fin_token', r.token);
    return r;
  },

  sair() {
    Estado.token = null;
    Estado.usuario = null;
    Estado.cache = {};
    localStorage.removeItem('fin_token');
    document.getElementById('app').classList.add('oculto');
    document.getElementById('tela-pagamento').classList.add('oculto');
    if (typeof Site !== 'undefined') Site.abrir();
  },

  ehMaster() {
    return Estado.usuario && Estado.usuario.perfil === 'MASTER';
  },

  /* Caches por empresa — recarregados ao trocar de empresa ou salvar cadastros. */
  async carregarCache(forcar = false) {
    const eid = Estado.empresaId;
    if (!eid) return;
    if (!forcar && Estado.cache.empresaId === eid) return;
    const [contas, centros, operacoes, bancos, parceiros,
      unidades, modalidades, produtos, usuarios, icms,
      categorias, marcas] = await Promise.all([
      Api.get('/api/contas-contabeis', { empresa_id: eid }),
      Api.get('/api/centros-custo', { empresa_id: eid }),
      Api.get('/api/operacoes', { empresa_id: eid }),
      Api.get('/api/bancos', { empresa_id: eid }),
      Api.get('/api/parceiros', { empresa_id: eid }),
      Api.get('/api/unidades', { empresa_id: eid }),
      Api.get('/api/modalidades', { empresa_id: eid }),
      Api.get('/api/produtos', { empresa_id: eid }),
      Api.get('/api/usuarios').catch(() => []),
      Api.get('/api/icms', { empresa_id: eid }).catch(() => []),
      Api.get('/api/categorias-produto', { empresa_id: eid }).catch(() => []),
      Api.get('/api/marcas-produto', { empresa_id: eid }).catch(() => []),
    ]);
    Estado.cache = {
      empresaId: eid, contas, centros, operacoes, bancos, parceiros,
      unidades, modalidades, produtos, usuarios, icms, categorias, marcas,
    };
  },

  contasAnaliticas(tipos) {
    const lista = (Estado.cache.contas || []).filter((c) => c.analitica && c.ativo);
    return tipos ? lista.filter((c) => tipos.includes(c.tipo)) : lista;
  },
  bancosAtivos() {
    return (Estado.cache.bancos || []).filter((b) => b.ativo);
  },
  centrosAtivos() {
    return (Estado.cache.centros || []).filter((c) => c.ativo);
  },
  operacoesAtivas(natureza) {
    return (Estado.cache.operacoes || []).filter(
      (o) => o.ativo && (!natureza || o.natureza === natureza || o.natureza === 'AMBAS'),
    );
  },
  parceirosPorTipo(tipo) {
    return (Estado.cache.parceiros || []).filter(
      (p) => p.ativo && (!tipo || p.tipo === tipo || p.tipo === 'AMBOS'),
    );
  },
  unidadesAtivas() {
    return (Estado.cache.unidades || []).filter((u) => u.ativo);
  },
  modalidadesAtivas() {
    return (Estado.cache.modalidades || []).filter((m) => m.ativo);
  },
  categoriasAtivas() {
    return (Estado.cache.categorias || []).filter((c) => c.ativo);
  },
  marcasAtivas() {
    return (Estado.cache.marcas || []).filter((m) => m.ativo);
  },
  /* Alíquota de ICMS que o contrato usa: linha do produto > linha geral do par de UFs.
     Espelha backend/icms.py (buscar_aliquota). */
  aliquotaIcms(ufOrigem, ufDestino, produtoId) {
    const origem = String(ufOrigem || '').trim().toUpperCase();
    const destino = String(ufDestino || '').trim().toUpperCase();
    if (!origem || !destino) return null;
    const linhas = (Estado.cache.icms || []).filter((l) => l.ativo
      && l.uf_origem === origem && l.uf_destino === destino);
    return (produtoId && linhas.find((l) => String(l.produto_id) === String(produtoId)))
      || linhas.find((l) => !l.produto_id) || null;
  },
  produtosAtivos() {
    return (Estado.cache.produtos || []).filter((p) => p.ativo);
  },
  /* Usuários da conta — usados como representante nos contratos. */
  representantes() {
    return (Estado.cache.usuarios || []).filter((u) => u.ativo);
  },
};
