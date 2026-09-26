"""Cadastros: usuários, empresas, clientes/fornecedores, bancos,
centros de custo, operações, plano de contas e parâmetros contábeis."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import contabil, estoque
from ..database import get_db
from ..deps import (
    acesso_liberado,
    checar_limite_usuarios,
    contar_usuarios_conta,
    empresas_permitidas,
    somente_admin,
    somente_master,
    validar_empresa,
)
from ..models import (
    Baixa,
    Banco,
    CentroCusto,
    ContaContabil,
    Contrato,
    Empresa,
    FormaPagamentoParceiro,
    Lancamento,
    AliquotaIcms,
    ModalidadeContrato,
    LancamentoItem,
    MovimentoCaixa,
    Operacao,
    Parametro,
    Parceiro,
    Partida,
    Produto,
    CategoriaProduto,
    MarcaProduto,
    Unidade,
    Usuario,
)
from ..plano_contas import (
    PARAMETROS_PADRAO,
    criar_cadastros_contrato_padrao,
    criar_centros_custo_padrao,
    criar_operacoes_padrao,
    criar_plano_padrao,
)
from ..schemas import (
    BancoIn,
    CentroCustoIn,
    ContaContabilIn,
    EmpresaIn,
    FormaPagamentoIn,
    ModalidadeIn,
    OperacaoIn,
    ParametrosIn,
    ParceiroIn,
    ProdutoIn,
    CategoriaProdutoIn,
    MarcaProdutoIn,
    UnidadeIn,
    UsuarioIn,
)
from ..security import hash_senha
from ..utils import serializar, serializar_lista

router = APIRouter(prefix="/api", tags=["cadastros"], dependencies=[Depends(acesso_liberado)])


def _aplicar(obj, dados: dict, ignorar=()):
    for campo, valor in dados.items():
        if campo in ignorar:
            continue
        if hasattr(obj, campo):
            setattr(obj, campo, valor)
    return obj


def _em_uso(db: Session, model, **filtros) -> bool:
    return db.query(model).filter_by(**filtros).first() is not None


# --------------------------------------------------------------------------- #
# Usuários
# --------------------------------------------------------------------------- #
@router.get("/usuarios")
def listar_usuarios(
    db: Session = Depends(get_db), atual: Usuario = Depends(acesso_liberado)
):
    query = db.query(Usuario)
    permitidas = empresas_permitidas(db, atual)
    if permitidas is not None:  # assinante vê apenas os usuários da própria conta
        query = query.filter(
            or_(Usuario.id == atual.id, Usuario.empresa_id.in_(permitidas or [0]))
        )
    return serializar_lista(query.order_by(Usuario.nome).all(), exclude={"senha_hash"})


def _empresa_da_conta(db: Session, atual: Usuario) -> int | None:
    if atual.empresa_id:
        return atual.empresa_id
    permitidas = empresas_permitidas(db, atual)
    return next(iter(permitidas), None) if permitidas else None


@router.post("/usuarios")
def criar_usuario(
    dados: UsuarioIn,
    db: Session = Depends(get_db),
    atual: Usuario = Depends(somente_admin),
):
    email = dados.email.strip().lower()
    if db.query(Usuario).filter(Usuario.email == email).first():
        raise HTTPException(400, "Já existe um usuário com este e-mail")
    if not dados.senha:
        raise HTTPException(400, "Informe a senha do novo usuário")
    perfil = dados.perfil
    if perfil == "MASTER" and atual.perfil != "MASTER":
        raise HTTPException(403, "Somente o administrador do sistema cria usuários MASTER")
    if dados.ativo:
        checar_limite_usuarios(db, atual)
    usuario = Usuario(
        nome=dados.nome,
        email=email,
        senha_hash=hash_senha(dados.senha),
        perfil=perfil,
        telefone=dados.telefone,
        ativo=dados.ativo,
        empresa_id=_empresa_da_conta(db, atual) if atual.perfil != "MASTER" else None,
    )
    db.add(usuario)
    db.commit()
    return serializar(usuario, exclude={"senha_hash"})


@router.put("/usuarios/{usuario_id}")
def atualizar_usuario(
    usuario_id: int,
    dados: UsuarioIn,
    db: Session = Depends(get_db),
    atual: Usuario = Depends(somente_admin),
):
    usuario = db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(404, "Usuário não encontrado")
    permitidas = empresas_permitidas(db, atual)
    if permitidas is not None and usuario.id != atual.id and usuario.empresa_id not in permitidas:
        raise HTTPException(403, "Este usuário não pertence à sua conta")
    if dados.perfil == "MASTER" and atual.perfil != "MASTER":
        raise HTTPException(403, "Somente o administrador do sistema define o perfil MASTER")
    if usuario.bloqueado_admin and dados.ativo and atual.perfil != "MASTER":
        raise HTTPException(403, "Este usuário foi bloqueado pelo administrador do site. "
                                 "Fale com o suporte para liberar.")
    if dados.ativo and not usuario.ativo:
        checar_limite_usuarios(db, atual)
    usuario.nome = dados.nome
    usuario.email = dados.email.strip().lower()
    usuario.perfil = dados.perfil
    usuario.telefone = dados.telefone
    usuario.ativo = dados.ativo
    if dados.senha:
        usuario.senha_hash = hash_senha(dados.senha)
    db.commit()
    return serializar(usuario, exclude={"senha_hash"})


@router.delete("/usuarios/{usuario_id}")
def excluir_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(somente_admin),
):
    if usuario_id == admin.id:
        raise HTTPException(400, "Você não pode excluir o próprio usuário")
    usuario = db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(404, "Usuário não encontrado")
    usuario.ativo = False  # mantém histórico dos lançamentos
    db.commit()
    return {"ok": True, "mensagem": "Usuário desativado"}


# --------------------------------------------------------------------------- #
# Empresas
# --------------------------------------------------------------------------- #
@router.get("/empresas")
def listar_empresas(db: Session = Depends(get_db), atual: Usuario = Depends(acesso_liberado)):
    query = db.query(Empresa)
    permitidas = empresas_permitidas(db, atual)
    if permitidas is not None:
        query = query.filter(Empresa.id.in_(permitidas or [0]))
    return serializar_lista(query.order_by(Empresa.razao_social).all())


@router.post("/empresas")
def criar_empresa(
    dados: EmpresaIn, db: Session = Depends(get_db), atual: Usuario = Depends(acesso_liberado)
):
    empresa = Empresa()
    _aplicar(empresa, dados.model_dump(), ignorar=("criar_plano_padrao",))
    if atual.perfil != "MASTER":
        empresa.dono_id = atual.id
    db.add(empresa)
    db.flush()
    if not atual.empresa_id:
        atual.empresa_id = empresa.id
    if dados.criar_plano_padrao:
        criar_plano_padrao(db, empresa.id)
        criar_centros_custo_padrao(db, empresa.id)
        criar_operacoes_padrao(db, empresa.id)
        criar_cadastros_contrato_padrao(db, empresa.id)
    db.commit()
    return serializar(empresa)


@router.put("/empresas/{empresa_id}")
def atualizar_empresa(
    empresa_id: int,
    dados: EmpresaIn,
    db: Session = Depends(get_db),
    atual: Usuario = Depends(acesso_liberado),
):
    empresa = validar_empresa(db, empresa_id, atual)
    dono = empresa.dono_id
    _aplicar(empresa, dados.model_dump(), ignorar=("criar_plano_padrao",))
    empresa.dono_id = dono
    db.commit()
    return serializar(empresa)


@router.delete("/empresas/{empresa_id}")
def excluir_empresa(
    empresa_id: int, db: Session = Depends(get_db), atual: Usuario = Depends(somente_admin)
):
    empresa = validar_empresa(db, empresa_id, atual)
    if _em_uso(db, Lancamento, empresa_id=empresa_id):
        raise HTTPException(400, "Empresa possui lançamentos e não pode ser excluída. Inative-a.")
    for model in (Operacao, CentroCusto, Banco, Parceiro, Parametro, ContaContabil):
        db.query(model).filter(model.empresa_id == empresa_id).delete(synchronize_session=False)
    db.delete(empresa)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Clientes / Fornecedores
# --------------------------------------------------------------------------- #
@router.get("/parceiros")
def listar_parceiros(
    empresa_id: int,
    tipo: str | None = None,
    q: str | None = None,
    apenas_ativos: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Parceiro).filter(Parceiro.empresa_id == empresa_id)
    if tipo:
        query = query.filter(or_(Parceiro.tipo == tipo, Parceiro.tipo == "AMBOS"))
    if apenas_ativos:
        query = query.filter(Parceiro.ativo.is_(True))
    if q:
        termo = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Parceiro.nome.ilike(termo),
                Parceiro.nome_fantasia.ilike(termo),
                Parceiro.cpf_cnpj.ilike(termo),
            )
        )
    parceiros = query.order_by(Parceiro.nome).all()
    return [
        serializar(
            p,
            extras={
                "qtd_formas_pagamento": len([f for f in p.formas_pagamento if f.ativo]),
                "forma_principal": next(
                    (resumo_forma(f) for f in p.formas_pagamento if f.principal and f.ativo), ""
                ),
            },
        )
        for p in parceiros
    ]


@router.post("/parceiros")
def criar_parceiro(dados: ParceiroIn, db: Session = Depends(get_db)):
    validar_empresa(db, dados.empresa_id)
    parceiro = Parceiro()
    _aplicar(parceiro, dados.model_dump())
    db.add(parceiro)
    db.commit()
    return serializar(parceiro)


@router.put("/parceiros/{parceiro_id}")
def atualizar_parceiro(parceiro_id: int, dados: ParceiroIn, db: Session = Depends(get_db)):
    parceiro = db.get(Parceiro, parceiro_id)
    if not parceiro:
        raise HTTPException(404, "Cliente/fornecedor não encontrado")
    _aplicar(parceiro, dados.model_dump())
    db.commit()
    return serializar(parceiro)


@router.delete("/parceiros/{parceiro_id}")
def excluir_parceiro(parceiro_id: int, db: Session = Depends(get_db)):
    parceiro = db.get(Parceiro, parceiro_id)
    if not parceiro:
        raise HTTPException(404, "Cliente/fornecedor não encontrado")
    if _em_uso(db, Lancamento, parceiro_id=parceiro_id):
        raise HTTPException(400, "Existem lançamentos para este cadastro. Inative-o em vez de excluir.")
    db.delete(parceiro)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Formas de pagamento do cliente/fornecedor (onde pagar cada um)
# --------------------------------------------------------------------------- #
TIPOS_FORMA = {
    "PIX": "Pix",
    "DEPOSITO": "Depósito em conta",
    "TED": "TED / Transferência",
    "BOLETO": "Boleto",
    "DINHEIRO": "Dinheiro",
    "CARTAO": "Cartão",
    "OUTRO": "Outro",
}
TIPOS_PIX = {
    "CPF": "CPF", "CNPJ": "CNPJ", "EMAIL": "E-mail",
    "TELEFONE": "Telefone", "ALEATORIA": "Chave aleatória",
}


def resumo_forma(f: FormaPagamentoParceiro) -> str:
    """Texto curto que identifica a forma na tela."""
    if f.tipo == "PIX":
        rotulo = TIPOS_PIX.get(f.pix_tipo or "", "")
        return f"Pix{f' ({rotulo})' if rotulo else ''}: {f.pix_chave or '-'}"
    if f.tipo in ("DEPOSITO", "TED"):
        banco = " ".join(x for x in [f.banco_codigo, f.banco_nome] if x) or "Banco não informado"
        conta = {"POUPANCA": "Poupança", "PAGAMENTO": "C. pagamento"}.get(
            f.tipo_conta or "", "C/C"
        )
        partes = [banco]
        if f.agencia:
            partes.append(f"Ag {f.agencia}")
        if f.operacao:
            partes.append(f"Op {f.operacao}")
        if f.conta:
            partes.append(f"{conta} {f.conta}")
        return " · ".join(partes)
    return f.apelido or TIPOS_FORMA.get(f.tipo, f.tipo)


def texto_copia(f: FormaPagamentoParceiro) -> str:
    """Bloco pronto para copiar e mandar para quem vai pagar."""
    if f.tipo == "PIX":
        return f.pix_chave or ""
    if f.tipo in ("DEPOSITO", "TED"):
        linhas = [x for x in [
            " ".join(y for y in [f.banco_codigo, f.banco_nome] if y),
            f"Agência: {f.agencia}" if f.agencia else "",
            f"Operação: {f.operacao}" if f.operacao else "",
            f"Conta: {f.conta}" if f.conta else "",
            f"Titular: {f.titular}" if f.titular else "",
            f"CPF/CNPJ: {f.documento_titular}" if f.documento_titular else "",
        ] if x]
        return "\n".join(linhas)
    return f.observacao or resumo_forma(f)


def forma_dict(f: FormaPagamentoParceiro) -> dict:
    return serializar(
        f,
        extras={
            "tipo_nome": TIPOS_FORMA.get(f.tipo, f.tipo),
            "resumo": resumo_forma(f),
            "texto_copia": texto_copia(f),
        },
    )


def _validar_forma(dados: FormaPagamentoIn):
    if dados.tipo not in TIPOS_FORMA:
        raise HTTPException(400, "Tipo de forma de pagamento inválido")
    if dados.tipo == "PIX" and not (dados.pix_chave or "").strip():
        raise HTTPException(400, "Informe a chave Pix")
    if dados.tipo in ("DEPOSITO", "TED"):
        if not (dados.banco_nome or dados.banco_codigo):
            raise HTTPException(400, "Informe o banco")
        if not (dados.conta or "").strip():
            raise HTTPException(400, "Informe o número da conta")


def _garantir_principal(db: Session, parceiro_id: int, forma_id: int | None):
    """Só uma forma fica marcada como principal por parceiro."""
    formas = (
        db.query(FormaPagamentoParceiro)
        .filter(FormaPagamentoParceiro.parceiro_id == parceiro_id)
        .all()
    )
    for f in formas:
        f.principal = f.id == forma_id
    if forma_id is None:
        ativas = [f for f in formas if f.ativo]
        if ativas:
            ativas[0].principal = True


def _parceiro_da_conta(db: Session, parceiro_id: int, usuario: Usuario) -> Parceiro:
    parceiro = db.get(Parceiro, parceiro_id)
    if not parceiro:
        raise HTTPException(404, "Cliente/fornecedor não encontrado")
    validar_empresa(db, parceiro.empresa_id, usuario)
    return parceiro


@router.get("/parceiros/{parceiro_id}/formas-pagamento")
def listar_formas_pagamento(
    parceiro_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    parceiro = _parceiro_da_conta(db, parceiro_id, usuario)
    formas = (
        db.query(FormaPagamentoParceiro)
        .filter(FormaPagamentoParceiro.parceiro_id == parceiro_id)
        .order_by(
            FormaPagamentoParceiro.principal.desc(),
            FormaPagamentoParceiro.ativo.desc(),
            FormaPagamentoParceiro.id,
        )
        .all()
    )
    return {
        "parceiro": {"id": parceiro.id, "nome": parceiro.nome, "tipo": parceiro.tipo,
                     "cpf_cnpj": parceiro.cpf_cnpj},
        "tipos": [{"valor": v, "rotulo": r} for v, r in TIPOS_FORMA.items()],
        "tipos_pix": [{"valor": v, "rotulo": r} for v, r in TIPOS_PIX.items()],
        "formas": [forma_dict(f) for f in formas],
    }


@router.post("/parceiros/{parceiro_id}/formas-pagamento")
def criar_forma_pagamento(
    parceiro_id: int,
    dados: FormaPagamentoIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    parceiro = _parceiro_da_conta(db, parceiro_id, usuario)
    _validar_forma(dados)
    forma = FormaPagamentoParceiro(parceiro_id=parceiro.id, empresa_id=parceiro.empresa_id)
    _aplicar(forma, dados.model_dump())
    if not forma.titular:
        forma.titular = parceiro.nome
    if not forma.documento_titular:
        forma.documento_titular = parceiro.cpf_cnpj
    db.add(forma)
    db.flush()
    primeira = (
        db.query(FormaPagamentoParceiro)
        .filter(FormaPagamentoParceiro.parceiro_id == parceiro.id)
        .count()
        == 1
    )
    if dados.principal or primeira:
        _garantir_principal(db, parceiro.id, forma.id)
    db.commit()
    return forma_dict(forma)


@router.put("/formas-pagamento/{forma_id}")
def atualizar_forma_pagamento(
    forma_id: int,
    dados: FormaPagamentoIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    forma = db.get(FormaPagamentoParceiro, forma_id)
    if not forma:
        raise HTTPException(404, "Forma de pagamento não encontrada")
    validar_empresa(db, forma.empresa_id, usuario)
    _validar_forma(dados)
    _aplicar(forma, dados.model_dump())
    db.flush()
    if dados.principal:
        _garantir_principal(db, forma.parceiro_id, forma.id)
    elif not forma.ativo and forma.principal:
        _garantir_principal(db, forma.parceiro_id, None)
    db.commit()
    return forma_dict(forma)


@router.post("/formas-pagamento/{forma_id}/principal")
def definir_forma_principal(
    forma_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    forma = db.get(FormaPagamentoParceiro, forma_id)
    if not forma:
        raise HTTPException(404, "Forma de pagamento não encontrada")
    validar_empresa(db, forma.empresa_id, usuario)
    if not forma.ativo:
        raise HTTPException(400, "Ative a forma de pagamento antes de torná-la principal.")
    _garantir_principal(db, forma.parceiro_id, forma.id)
    db.commit()
    return forma_dict(forma)


@router.delete("/formas-pagamento/{forma_id}")
def excluir_forma_pagamento(
    forma_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    forma = db.get(FormaPagamentoParceiro, forma_id)
    if not forma:
        raise HTTPException(404, "Forma de pagamento não encontrada")
    validar_empresa(db, forma.empresa_id, usuario)
    if _em_uso(db, Baixa, forma_parceiro_id=forma_id):
        raise HTTPException(
            400,
            "Esta forma já foi usada em pagamentos registrados. Desative-a em vez de excluir.",
        )
    parceiro_id, era_principal = forma.parceiro_id, forma.principal
    db.delete(forma)
    db.flush()
    if era_principal:
        _garantir_principal(db, parceiro_id, None)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Bancos / contas de caixa
# --------------------------------------------------------------------------- #
def _banco_dict(db: Session, banco: Banco) -> dict:
    conta = banco.conta_contabil
    return serializar(
        banco,
        extras={
            "conta_contabil_nome": f"{conta.codigo} - {conta.nome}" if conta else None,
        },
    )


@router.get("/bancos")
def listar_bancos(empresa_id: int, apenas_ativos: bool = False, db: Session = Depends(get_db)):
    query = db.query(Banco).filter(Banco.empresa_id == empresa_id)
    if apenas_ativos:
        query = query.filter(Banco.ativo.is_(True))
    return [_banco_dict(db, b) for b in query.order_by(Banco.nome).all()]


@router.post("/bancos")
def criar_banco(dados: BancoIn, db: Session = Depends(get_db)):
    validar_empresa(db, dados.empresa_id)
    banco = Banco()
    _aplicar(banco, dados.model_dump())
    db.add(banco)
    db.flush()
    contabil.contabilizar_saldo_inicial_banco(db, banco)
    db.commit()
    return _banco_dict(db, banco)


@router.put("/bancos/{banco_id}")
def atualizar_banco(banco_id: int, dados: BancoIn, db: Session = Depends(get_db)):
    banco = db.get(Banco, banco_id)
    if not banco:
        raise HTTPException(404, "Conta bancária não encontrada")
    _aplicar(banco, dados.model_dump())
    db.flush()
    contabil.contabilizar_saldo_inicial_banco(db, banco)
    db.commit()
    return _banco_dict(db, banco)


@router.delete("/bancos/{banco_id}")
def excluir_banco(banco_id: int, db: Session = Depends(get_db)):
    banco = db.get(Banco, banco_id)
    if not banco:
        raise HTTPException(404, "Conta bancária não encontrada")
    if _em_uso(db, MovimentoCaixa, banco_id=banco_id):
        raise HTTPException(400, "Esta conta possui movimentos. Inative-a em vez de excluir.")
    contabil.estornar(db, "ABERTURA_BANCO", banco.id)
    db.delete(banco)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Unidades, modalidades e produtos (usados nos contratos)
# --------------------------------------------------------------------------- #
def _crud_simples(nome_rota: str, model, schema, rotulo: str, extras=None, validar=None):
    """Monta os quatro endpoints de um cadastro simples por empresa.

    `validar(db, registro)` roda antes de gravar, na criação e na edição, para as
    regras que são só daquele cadastro.
    """

    def listar(
        empresa_id: int,
        apenas_ativos: bool = False,
        categoria_id: int | None = None,
        marca_id: int | None = None,
        db: Session = Depends(get_db),
        _: Usuario = Depends(acesso_liberado),
    ):
        query = db.query(model).filter(model.empresa_id == empresa_id)
        if apenas_ativos:
            query = query.filter(model.ativo.is_(True))
        # os dois filtros só existem onde faz sentido (produtos); nos outros
        # cadastros o parâmetro é ignorado
        if categoria_id and hasattr(model, "categoria_id"):
            query = query.filter(model.categoria_id == categoria_id)
        if marca_id and hasattr(model, "marca_id"):
            query = query.filter(model.marca_id == marca_id)
        registros = query.order_by(model.codigo).all()
        return [serializar(r, extras=extras(r) if extras else None) for r in registros]

    def criar(dados: schema, db: Session = Depends(get_db),
              usuario: Usuario = Depends(acesso_liberado)):
        validar_empresa(db, dados.empresa_id, usuario)
        codigo = (dados.codigo or "").strip()
        if not codigo:
            raise HTTPException(400, "Informe o código")
        if (
            db.query(model)
            .filter(model.empresa_id == dados.empresa_id, model.codigo == codigo)
            .first()
        ):
            raise HTTPException(400, f"Já existe {rotulo} com o código {codigo}")
        registro = model()
        _aplicar(registro, dados.model_dump())
        registro.codigo = codigo
        if validar:
            validar(db, registro)
        db.add(registro)
        db.commit()
        return serializar(registro, extras=extras(registro) if extras else None)

    def atualizar(registro_id: int, dados: schema, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(acesso_liberado)):
        registro = db.get(model, registro_id)
        if not registro:
            raise HTTPException(404, f"{rotulo.capitalize()} não encontrado")
        validar_empresa(db, registro.empresa_id, usuario)
        _aplicar(registro, dados.model_dump(), ignorar=("empresa_id",))
        if validar:
            validar(db, registro)
        db.commit()
        return serializar(registro, extras=extras(registro) if extras else None)

    def excluir(registro_id: int, db: Session = Depends(get_db),
                usuario: Usuario = Depends(acesso_liberado)):
        registro = db.get(model, registro_id)
        if not registro:
            raise HTTPException(404, f"{rotulo.capitalize()} não encontrado")
        validar_empresa(db, registro.empresa_id, usuario)
        campo = {"unidades": "unidade_id", "modalidades": "modalidade_id",
                 "produtos": "produto_id"}.get(nome_rota)
        if campo and db.query(Contrato).filter(getattr(Contrato, campo) == registro_id).first():
            raise HTTPException(
                400, f"Existem contratos usando {rotulo}. Inative em vez de excluir."
            )
        # categoria e marca são obrigatórias no produto: apagar uma em uso deixaria
        # produto sem classificação, que é justamente o que não se quer
        for classificacao, coluna, aviso in (
            (CategoriaProduto, Produto.categoria_id, "esta categoria"),
            (MarcaProduto, Produto.marca_id, "esta marca"),
        ):
            if model is classificacao and db.query(Produto).filter(coluna == registro_id).first():
                raise HTTPException(
                    400, f"Existem produtos classificados com {aviso}. Troque a "
                         "classificação deles ou inative em vez de excluir.")
        if model is Produto and db.query(AliquotaIcms).filter(AliquotaIcms.produto_id == registro_id).first():
            raise HTTPException(400, "Existem alíquotas de ICMS usando este produto. Inative-o ou apague as alíquotas.")
        if model is Unidade and db.query(Produto).filter(Produto.unidade_id == registro_id).first():
            raise HTTPException(400, "Existem produtos usando esta unidade. Inative-a.")
        db.delete(registro)
        db.commit()
        return {"ok": True}

    router.add_api_route(f"/{nome_rota}", listar, methods=["GET"])
    router.add_api_route(f"/{nome_rota}", criar, methods=["POST"])
    router.add_api_route(f"/{nome_rota}/{{registro_id}}", atualizar, methods=["PUT"])
    router.add_api_route(f"/{nome_rota}/{{registro_id}}", excluir, methods=["DELETE"])


def _conferir_classificacao(db: Session, produto: Produto) -> None:
    """Todo produto salvo pela tela sai classificado — e com classificação da própria conta.

    A coluna aceita vazio (produto antigo e produto criado pela importação de XML
    continuam válidos), então quem exige é aqui, na porta por onde a pessoa salva.
    Conferir a empresa não é preciosismo: sem isso daria para classificar um produto
    com a categoria de outro assinante mandando o id na mão.
    """
    for campo, classificacao, rotulo in (
        ("categoria_id", CategoriaProduto, "a categoria"),
        ("marca_id", MarcaProduto, "a marca"),
    ):
        valor = getattr(produto, campo, None)
        if not valor:
            raise HTTPException(
                400, f"Escolha {rotulo} do produto. Se ainda não tem a que precisa, "
                     "cadastre em Cadastros > "
                     f"{'Categorias' if campo == 'categoria_id' else 'Marcas'}.")
        registro = db.get(classificacao, valor)
        if registro is None or registro.empresa_id != produto.empresa_id:
            raise HTTPException(400, f"{rotulo.capitalize()} escolhida não é desta empresa.")


_crud_simples("categorias-produto", CategoriaProduto, CategoriaProdutoIn, "uma categoria")
_crud_simples("marcas-produto", MarcaProduto, MarcaProdutoIn, "uma marca")
_crud_simples("unidades", Unidade, UnidadeIn, "uma unidade")
_crud_simples("modalidades", ModalidadeContrato, ModalidadeIn, "uma modalidade")
_crud_simples(
    "produtos", Produto, ProdutoIn, "um produto",
    extras=lambda p: {
        "unidade_nome": f"{p.unidade.codigo} - {p.unidade.nome}" if p.unidade else None,
        "categoria_nome": p.categoria.nome if p.categoria else None,
        "marca_nome": p.marca.nome if p.marca else None,
        "peso_conversao": p.unidade.peso_conversao if p.unidade else 0,
        # saldo e custo médio são só leitura: quem os move é o motor de estoque
        "estoque": estoque.ficha_produto(p) if p.controla_estoque else None,
    },
    validar=_conferir_classificacao,
)


@router.post("/cadastros-contrato/padrao")
def gerar_cadastros_contrato_padrao(
    empresa_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)
):
    """Cria unidades, modalidades e produtos padrão que ainda não existirem."""
    validar_empresa(db, empresa_id, usuario)
    resultado = criar_cadastros_contrato_padrao(db, empresa_id)
    db.commit()
    return resultado


# --------------------------------------------------------------------------- #
# Centros de custo
# --------------------------------------------------------------------------- #
@router.get("/centros-custo")
def listar_centros_custo(
    empresa_id: int, apenas_ativos: bool = False, db: Session = Depends(get_db)
):
    query = db.query(CentroCusto).filter(CentroCusto.empresa_id == empresa_id)
    if apenas_ativos:
        query = query.filter(CentroCusto.ativo.is_(True))
    return serializar_lista(query.order_by(CentroCusto.codigo).all())


@router.post("/centros-custo")
def criar_centro_custo(dados: CentroCustoIn, db: Session = Depends(get_db)):
    validar_empresa(db, dados.empresa_id)
    if (
        db.query(CentroCusto)
        .filter(CentroCusto.empresa_id == dados.empresa_id, CentroCusto.codigo == dados.codigo)
        .first()
    ):
        raise HTTPException(400, "Já existe um centro de custo com este código")
    cc = CentroCusto()
    _aplicar(cc, dados.model_dump())
    db.add(cc)
    db.commit()
    return serializar(cc)


@router.put("/centros-custo/{cc_id}")
def atualizar_centro_custo(cc_id: int, dados: CentroCustoIn, db: Session = Depends(get_db)):
    cc = db.get(CentroCusto, cc_id)
    if not cc:
        raise HTTPException(404, "Centro de custo não encontrado")
    _aplicar(cc, dados.model_dump())
    db.commit()
    return serializar(cc)


@router.delete("/centros-custo/{cc_id}")
def excluir_centro_custo(cc_id: int, db: Session = Depends(get_db)):
    cc = db.get(CentroCusto, cc_id)
    if not cc:
        raise HTTPException(404, "Centro de custo não encontrado")
    if _em_uso(db, LancamentoItem, centro_custo_id=cc_id) or _em_uso(
        db, MovimentoCaixa, centro_custo_id=cc_id
    ):
        raise HTTPException(400, "Centro de custo já utilizado em movimentos. Inative-o.")
    db.delete(cc)
    db.commit()
    return {"ok": True}


@router.post("/centros-custo/padrao")
def gerar_centros_padrao(empresa_id: int, db: Session = Depends(get_db)):
    validar_empresa(db, empresa_id)
    qtd = criar_centros_custo_padrao(db, empresa_id)
    db.commit()
    return {"criados": qtd}


# --------------------------------------------------------------------------- #
# Operações
# --------------------------------------------------------------------------- #
def _operacao_dict(op: Operacao) -> dict:
    return serializar(
        op,
        extras={
            "conta_contabil_nome": (
                f"{op.conta_contabil.codigo} - {op.conta_contabil.nome}"
                if op.conta_contabil
                else None
            ),
            "centro_custo_nome": op.centro_custo.nome if op.centro_custo else None,
        },
    )


@router.get("/operacoes")
def listar_operacoes(
    empresa_id: int,
    natureza: str | None = None,
    apenas_ativos: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Operacao).filter(Operacao.empresa_id == empresa_id)
    if natureza:
        query = query.filter(or_(Operacao.natureza == natureza, Operacao.natureza == "AMBAS"))
    if apenas_ativos:
        query = query.filter(Operacao.ativo.is_(True))
    return [_operacao_dict(o) for o in query.order_by(Operacao.codigo).all()]


@router.post("/operacoes")
def criar_operacao(dados: OperacaoIn, db: Session = Depends(get_db)):
    validar_empresa(db, dados.empresa_id)
    if (
        db.query(Operacao)
        .filter(Operacao.empresa_id == dados.empresa_id, Operacao.codigo == dados.codigo)
        .first()
    ):
        raise HTTPException(400, "Já existe uma operação com este código")
    op = Operacao()
    _aplicar(op, dados.model_dump())
    db.add(op)
    db.commit()
    return _operacao_dict(op)


@router.put("/operacoes/{operacao_id}")
def atualizar_operacao(operacao_id: int, dados: OperacaoIn, db: Session = Depends(get_db)):
    op = db.get(Operacao, operacao_id)
    if not op:
        raise HTTPException(404, "Operação não encontrada")
    _aplicar(op, dados.model_dump())
    db.commit()
    return _operacao_dict(op)


@router.delete("/operacoes/{operacao_id}")
def excluir_operacao(operacao_id: int, db: Session = Depends(get_db)):
    op = db.get(Operacao, operacao_id)
    if not op:
        raise HTTPException(404, "Operação não encontrada")
    if _em_uso(db, Lancamento, operacao_id=operacao_id) or _em_uso(
        db, MovimentoCaixa, operacao_id=operacao_id
    ):
        raise HTTPException(400, "Operação já utilizada em movimentos. Inative-a.")
    db.delete(op)
    db.commit()
    return {"ok": True}


@router.post("/operacoes/padrao")
def gerar_operacoes_padrao(empresa_id: int, db: Session = Depends(get_db)):
    validar_empresa(db, empresa_id)
    qtd = criar_operacoes_padrao(db, empresa_id)
    db.commit()
    return {"criadas": qtd}


# --------------------------------------------------------------------------- #
# Plano de contas
# --------------------------------------------------------------------------- #
@router.get("/contas-contabeis")
def listar_contas(
    empresa_id: int,
    analitica: bool | None = None,
    tipo: str | None = None,
    apenas_ativos: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(ContaContabil).filter(ContaContabil.empresa_id == empresa_id)
    if analitica is not None:
        query = query.filter(ContaContabil.analitica.is_(analitica))
    if tipo:
        query = query.filter(ContaContabil.tipo == tipo)
    if apenas_ativos:
        query = query.filter(ContaContabil.ativo.is_(True))
    return serializar_lista(query.order_by(ContaContabil.codigo).all())


@router.post("/contas-contabeis")
def criar_conta(dados: ContaContabilIn, db: Session = Depends(get_db)):
    validar_empresa(db, dados.empresa_id)
    if (
        db.query(ContaContabil)
        .filter(
            ContaContabil.empresa_id == dados.empresa_id, ContaContabil.codigo == dados.codigo
        )
        .first()
    ):
        raise HTTPException(400, "Já existe uma conta contábil com este código")
    conta = ContaContabil(nivel=dados.codigo.count(".") + 1)
    _aplicar(conta, dados.model_dump())
    conta.nivel = dados.codigo.count(".") + 1
    if conta.pai_id is None:
        pai_codigo = ".".join(dados.codigo.split(".")[:-1])
        while pai_codigo:
            pai = (
                db.query(ContaContabil)
                .filter(
                    ContaContabil.empresa_id == dados.empresa_id,
                    ContaContabil.codigo == pai_codigo,
                )
                .first()
            )
            if pai:
                conta.pai_id = pai.id
                break
            pai_codigo = ".".join(pai_codigo.split(".")[:-1])
    db.add(conta)
    db.flush()
    contabil.contabilizar_saldo_inicial_conta(db, conta)
    db.commit()
    return serializar(conta)


@router.put("/contas-contabeis/{conta_id}")
def atualizar_conta(conta_id: int, dados: ContaContabilIn, db: Session = Depends(get_db)):
    conta = db.get(ContaContabil, conta_id)
    if not conta:
        raise HTTPException(404, "Conta contábil não encontrada")
    _aplicar(conta, dados.model_dump())
    conta.nivel = conta.codigo.count(".") + 1
    db.flush()
    contabil.contabilizar_saldo_inicial_conta(db, conta)
    db.commit()
    return serializar(conta)


@router.delete("/contas-contabeis/{conta_id}")
def excluir_conta(conta_id: int, db: Session = Depends(get_db)):
    conta = db.get(ContaContabil, conta_id)
    if not conta:
        raise HTTPException(404, "Conta contábil não encontrada")
    usada = (
        db.query(Partida)
        .filter(
            or_(Partida.conta_debito_id == conta_id, Partida.conta_credito_id == conta_id),
            Partida.origem != "ABERTURA_CONTA",
        )
        .first()
    )
    if usada:
        raise HTTPException(400, "Conta já possui movimento contábil. Inative-a em vez de excluir.")
    if db.query(ContaContabil).filter(ContaContabil.pai_id == conta_id).first():
        raise HTTPException(400, "Existem contas filhas vinculadas a esta conta.")
    contabil.estornar(db, "ABERTURA_CONTA", conta.id)
    db.delete(conta)
    db.commit()
    return {"ok": True}


@router.post("/contas-contabeis/plano-padrao")
def gerar_plano_padrao(empresa_id: int, db: Session = Depends(get_db)):
    validar_empresa(db, empresa_id)
    qtd = criar_plano_padrao(db, empresa_id)
    db.commit()
    return {"criadas": qtd}


# --------------------------------------------------------------------------- #
# Parâmetros contábeis
# --------------------------------------------------------------------------- #
@router.get("/parametros")
def listar_parametros(empresa_id: int, db: Session = Depends(get_db)):
    atuais = {
        p.chave: int(p.valor) if p.valor and p.valor.isdigit() else None
        for p in db.query(Parametro).filter(Parametro.empresa_id == empresa_id).all()
    }
    return {
        "empresa_id": empresa_id,
        "valores": {chave: atuais.get(chave) for chave in PARAMETROS_PADRAO},
        "descricoes": {
            "conta_clientes": "Contrapartida dos títulos a receber (Clientes a Receber)",
            "conta_fornecedores": "Contrapartida dos títulos a pagar (Fornecedores a Pagar)",
            "conta_caixa_padrao": "Conta contábil padrão para contas do tipo Caixa",
            "conta_banco_padrao": "Conta contábil padrão para contas bancárias",
            "conta_juros_recebidos": "Juros e multas recebidos de clientes",
            "conta_descontos_obtidos": "Descontos obtidos de fornecedores",
            "conta_juros_pagos": "Juros pagos a fornecedores",
            "conta_multas_pagas": "Multas e encargos pagos",
            "conta_descontos_concedidos": "Descontos concedidos a clientes",
            "conta_saldo_abertura": "Contrapartida dos saldos iniciais",
            "conta_resultado_acumulado": "Lucros ou prejuízos acumulados",
        },
    }


@router.put("/parametros")
def salvar_parametros(dados: ParametrosIn, db: Session = Depends(get_db)):
    validar_empresa(db, dados.empresa_id)
    atuais = {
        p.chave: p
        for p in db.query(Parametro).filter(Parametro.empresa_id == dados.empresa_id).all()
    }
    for chave, valor in dados.valores.items():
        if chave not in PARAMETROS_PADRAO:
            continue
        texto = str(valor) if valor else None
        if chave in atuais:
            atuais[chave].valor = texto
        else:
            db.add(Parametro(empresa_id=dados.empresa_id, chave=chave, valor=texto))
    db.commit()
    return listar_parametros(dados.empresa_id, db)
