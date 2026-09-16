"""Assinatura do assinante e administração das contas (área MASTER)."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import assinaturas as regras
from ..database import get_db
from ..deps import (
    assinatura_do_usuario,
    contar_usuarios_conta,
    somente_master,
    usuario_atual,
)
from ..models import Assinatura, Empresa, Usuario
from ..schemas import (
    ConfiguracoesIn,
    EscolherPlanoIn,
    InformarPagamentoIn,
    PacotesUsuariosIn,
    StatusAssinaturaIn,
)
from ..utils import moeda_br, serializar

router = APIRouter(prefix="/api", tags=["assinatura"])


def _minha(db: Session, usuario: Usuario) -> Assinatura:
    assinatura = assinatura_do_usuario(db, usuario)
    if not assinatura:
        raise HTTPException(404, "Esta conta não possui assinatura vinculada")
    return assinatura


# --------------------------------------------------------------------------- #
# Assinante
# --------------------------------------------------------------------------- #
@router.get("/assinatura/minha")
def minha_assinatura(
    db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)
):
    """Situação da conta + dados de pagamento. Acessível mesmo com a conta bloqueada."""
    assinatura = assinatura_do_usuario(db, usuario)
    resposta = {
        "situacao": regras.situacao(db, assinatura),
        "planos": regras.planos(db),
        "usuario": serializar(usuario, exclude={"senha_hash"}),
    }
    usados = contar_usuarios_conta(db, usuario)
    resposta["usuarios"] = regras.resumo_usuarios(db, assinatura, usados)
    if assinatura:
        resposta["pagamento"] = regras.dados_pagamento(db, assinatura)
        resposta["assinatura"] = serializar(assinatura)
        if assinatura.pacotes_solicitados:
            resposta["pagamento_pacotes"] = regras.dados_pagamento(
                db,
                assinatura,
                valor=regras.valor_pacote(db, assinatura) * assinatura.pacotes_solicitados,
            )
    return resposta


@router.post("/assinatura/pacotes")
def solicitar_pacotes(
    dados: PacotesUsuariosIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    """O assinante pede pacotes de usuários extras; a liberação vem na confirmação."""
    assinatura = _minha(db, usuario)
    quantidade = max(1, int(dados.quantidade or 1))
    assinatura.pacotes_solicitados = (assinatura.pacotes_solicitados or 0) + quantidade
    db.commit()
    unitario = regras.valor_pacote(db, assinatura)
    total = round(unitario * assinatura.pacotes_solicitados, 2)
    por_pacote = regras.usuarios_por_pacote(db)
    return {
        "ok": True,
        "usuarios": regras.resumo_usuarios(db, assinatura, contar_usuarios_conta(db, usuario)),
        "pagamento": regras.dados_pagamento(db, assinatura, valor=total),
        "mensagem": (
            f"{quantidade} pacote(s) de +{por_pacote} usuários solicitado(s). "
            f"Pague {moeda_br(total)} por Pix e avise; a liberação acontece na confirmação."
        ),
    }


@router.post("/assinatura/pacotes/cancelar")
def cancelar_pacotes(
    db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)
):
    assinatura = _minha(db, usuario)
    assinatura.pacotes_solicitados = 0
    db.commit()
    return {"ok": True, "usuarios": regras.resumo_usuarios(
        db, assinatura, contar_usuarios_conta(db, usuario))}


@router.post("/assinatura/plano")
def escolher_plano(
    dados: EscolherPlanoIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    assinatura = _minha(db, usuario)
    if assinatura.status == "ATIVA":
        raise HTTPException(
            400, "A assinatura já está ativa. A troca de plano vale na próxima renovação."
        )
    plano = regras.plano_por_codigo(db, dados.plano)
    assinatura.plano = plano["codigo"]
    assinatura.valor = plano["valor"]
    db.commit()
    return {
        "situacao": regras.situacao(db, assinatura),
        "pagamento": regras.dados_pagamento(db, assinatura),
    }


@router.post("/assinatura/pagamento")
def informar_pagamento(
    dados: InformarPagamentoIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    """O assinante avisa que fez o Pix; a liberação depende da confirmação."""
    assinatura = _minha(db, usuario)
    assinatura.pagamento_informado_em = datetime.utcnow()
    assinatura.pagamento_observacao = (dados.observacao or "")[:300]
    if assinatura.status in ("TESTE", "EXPIRADA", "CANCELADA"):
        assinatura.status = "AGUARDANDO"
    db.commit()
    return {
        "ok": True,
        "situacao": regras.situacao(db, assinatura),
        "mensagem": "Pagamento informado. Assim que confirmarmos o recebimento do Pix "
                    "seu acesso é liberado.",
    }


# --------------------------------------------------------------------------- #
# Administração (MASTER)
# --------------------------------------------------------------------------- #
def _linha_assinatura(db: Session, a: Assinatura) -> dict:
    usuario = db.get(Usuario, a.usuario_id)
    empresa = db.get(Empresa, a.empresa_id) if a.empresa_id else None
    situacao = regras.situacao(db, a)
    return dict(
        serializar(a),
        usuario_nome=usuario.nome if usuario else "-",
        usuario_email=usuario.email if usuario else "-",
        usuario_telefone=usuario.telefone if usuario else "",
        empresa_nome=(empresa.nome_fantasia or empresa.razao_social) if empresa else "-",
        liberado=situacao.get("liberado"),
        situacao_titulo=situacao.get("titulo"),
        situacao_mensagem=situacao.get("mensagem"),
        limite_usuarios=regras.limite_usuarios(db, a),
        valor_pacote=regras.valor_pacote(db, a),
    )


@router.get("/admin/assinaturas")
def listar_assinaturas(
    status: str | None = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(somente_master),
):
    query = db.query(Assinatura)
    if status:
        query = query.filter(Assinatura.status == status)
    assinaturas = query.order_by(Assinatura.criado_em.desc()).all()
    linhas = [_linha_assinatura(db, a) for a in assinaturas]
    return {
        "linhas": linhas,
        "resumo": {
            "total": len(linhas),
            "ativas": sum(1 for l in linhas if l["status"] == "ATIVA"),
            "aguardando": sum(1 for l in linhas if l["status"] == "AGUARDANDO"),
            "em_teste": sum(1 for l in linhas if l["status"] == "TESTE"),
            "receita_ativa": round(
                sum(l["valor"] for l in linhas if l["status"] == "ATIVA"), 2
            ),
        },
    }


@router.post("/admin/assinaturas/{assinatura_id}/confirmar")
def confirmar(
    assinatura_id: int,
    dados: StatusAssinaturaIn | None = None,
    db: Session = Depends(get_db),
    master: Usuario = Depends(somente_master),
):
    """Confirma o recebimento do Pix e libera o acesso pelo prazo do plano."""
    assinatura = db.get(Assinatura, assinatura_id)
    if not assinatura:
        raise HTTPException(404, "Assinatura não encontrada")
    meses = dados.meses if dados and dados.meses else None
    if dados and dados.observacao:
        assinatura.observacao_admin = dados.observacao
    regras.confirmar_pagamento(db, assinatura, master.id, meses)
    db.commit()
    return _linha_assinatura(db, assinatura)


@router.post("/admin/assinaturas/{assinatura_id}/status")
def alterar_status(
    assinatura_id: int,
    dados: StatusAssinaturaIn,
    db: Session = Depends(get_db),
    _: Usuario = Depends(somente_master),
):
    assinatura = db.get(Assinatura, assinatura_id)
    if not assinatura:
        raise HTTPException(404, "Assinatura não encontrada")
    if dados.status not in ("TESTE", "AGUARDANDO", "ATIVA", "EXPIRADA", "CANCELADA"):
        raise HTTPException(400, "Situação inválida")
    assinatura.status = dados.status
    if dados.plano:
        plano = regras.plano_por_codigo(db, dados.plano)
        assinatura.plano = plano["codigo"]
        assinatura.valor = plano["valor"]
    if dados.observacao is not None:
        assinatura.observacao_admin = dados.observacao
    if dados.horas_teste is not None:
        from datetime import timedelta

        assinatura.teste_inicio = datetime.utcnow()
        assinatura.teste_fim = datetime.utcnow() + timedelta(hours=dados.horas_teste)
    db.commit()
    return _linha_assinatura(db, assinatura)


@router.post("/admin/assinaturas/{assinatura_id}/pacotes")
def confirmar_pacotes(
    assinatura_id: int,
    dados: PacotesUsuariosIn | None = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(somente_master),
):
    """Confirma o pagamento dos pacotes extras e libera os usuários."""
    assinatura = db.get(Assinatura, assinatura_id)
    if not assinatura:
        raise HTTPException(404, "Assinatura não encontrada")
    quantidade = (dados.quantidade if dados and dados.quantidade
                  else assinatura.pacotes_solicitados or 0)
    if quantidade <= 0:
        raise HTTPException(400, "Informe quantos pacotes confirmar.")
    assinatura.pacotes_usuarios = (assinatura.pacotes_usuarios or 0) + quantidade
    assinatura.pacotes_solicitados = max((assinatura.pacotes_solicitados or 0) - quantidade, 0)
    db.commit()
    return _linha_assinatura(db, assinatura)


@router.get("/admin/configuracoes")
def obter_configuracoes(db: Session = Depends(get_db), _: Usuario = Depends(somente_master)):
    return {
        "valores": regras.configuracoes(db),
        "descricoes": {c: d for c, (_v, d, _p) in regras.CONFIGURACOES_PADRAO.items()},
    }


@router.put("/admin/configuracoes")
def salvar_configuracoes(
    dados: ConfiguracoesIn,
    db: Session = Depends(get_db),
    _: Usuario = Depends(somente_master),
):
    regras.salvar_configuracoes(db, dados.valores)
    db.commit()
    return {"ok": True, "valores": regras.configuracoes(db)}
