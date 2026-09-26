"""Dados iniciais: usuário administrador, empresa e plano de contas."""
from datetime import date

from sqlalchemy.orm import Session

from .models import Banco, ContaContabil, Empresa, Usuario
from .plano_contas import (
    criar_cadastros_contrato_padrao,
    criar_centros_custo_padrao,
    criar_operacoes_padrao,
    criar_plano_padrao,
)
from .security import hash_senha

ADMIN_EMAIL = "admin@financeiro.local"
ADMIN_SENHA = "admin123"


def garantir_classificacao(db: Session) -> int:
    """Toda empresa precisa ter ao menos uma categoria e uma marca.

    Sem isso, a exigência de classificar o produto viraria um beco sem saída nas
    empresas que já existiam antes desta versão: a pessoa abre o produto para
    editar, o sistema pede a categoria, e não há nenhuma para escolher. Roda a
    cada subida e não repete o que já está lá.
    """
    from .models import CategoriaProduto, Empresa, MarcaProduto
    from .plano_contas import criar_categorias_padrao, criar_marcas_padrao

    criadas = 0
    for (empresa_id,) in db.query(Empresa.id).all():
        tem_categoria = (db.query(CategoriaProduto)
                         .filter(CategoriaProduto.empresa_id == empresa_id).first())
        tem_marca = (db.query(MarcaProduto)
                     .filter(MarcaProduto.empresa_id == empresa_id).first())
        if not tem_categoria:
            criadas += criar_categorias_padrao(db, empresa_id)
        if not tem_marca:
            criadas += criar_marcas_padrao(db, empresa_id)
    if criadas:
        db.commit()
    return criadas


def criar_dados_iniciais(db: Session) -> str | None:
    from .assinaturas import garantir_configuracoes

    garantir_configuracoes(db)

    from .assinaturas import garantir_master
    garantir_master(db)

    garantir_classificacao(db)

    if db.query(Usuario).count():
        # garante que exista ao menos um administrador do sistema (perfil MASTER)
        if not db.query(Usuario).filter(Usuario.perfil == "MASTER").count():
            primeiro = db.query(Usuario).order_by(Usuario.id).first()
            if primeiro:
                primeiro.perfil = "MASTER"
        db.commit()
        return None

    db.add(
        Usuario(
            nome="Administrador do sistema",
            email=ADMIN_EMAIL,
            senha_hash=hash_senha(ADMIN_SENHA),
            perfil="MASTER",
        )
    )

    empresa = db.query(Empresa).first()
    if not empresa:
        empresa = Empresa(
            razao_social="Minha Empresa Ltda",
            nome_fantasia="Minha Empresa",
            regime_tributario="SIMPLES NACIONAL",
            cidade="São Paulo",
            uf="SP",
        )
        db.add(empresa)
        db.flush()
        criar_plano_padrao(db, empresa.id)
        criar_centros_custo_padrao(db, empresa.id)
        criar_operacoes_padrao(db, empresa.id)
        criar_cadastros_contrato_padrao(db, empresa.id)

        conta_caixa = (
            db.query(ContaContabil)
            .filter(ContaContabil.empresa_id == empresa.id, ContaContabil.codigo == "1.1.01.001")
            .first()
        )
        conta_banco = (
            db.query(ContaContabil)
            .filter(ContaContabil.empresa_id == empresa.id, ContaContabil.codigo == "1.1.01.002")
            .first()
        )
        db.add_all(
            [
                Banco(
                    empresa_id=empresa.id,
                    codigo="001",
                    nome="Caixa Interno",
                    tipo="CAIXA",
                    conta_contabil_id=conta_caixa.id if conta_caixa else None,
                    saldo_inicial=0,
                    data_saldo_inicial=date.today(),
                ),
                Banco(
                    empresa_id=empresa.id,
                    codigo="002",
                    nome="Banco Principal",
                    tipo="CORRENTE",
                    conta_contabil_id=conta_banco.id if conta_banco else None,
                    saldo_inicial=0,
                    data_saldo_inicial=date.today(),
                ),
            ]
        )

    db.commit()
    return f"usuário {ADMIN_EMAIL} / senha {ADMIN_SENHA}"
