"""Área pública: informações do site, planos e cadastro de novos assinantes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import assinaturas as regras
from ..database import get_db
from ..deps import situacao_da_conta
from ..models import Empresa, Usuario
from ..plano_contas import (
    criar_cadastros_contrato_padrao,
    criar_centros_custo_padrao,
    criar_operacoes_padrao,
    criar_plano_padrao,
)
from ..schemas import CadastroPublicoIn
from ..security import gerar_token, hash_senha
from ..utils import serializar

router = APIRouter(prefix="/api/publico", tags=["publico"])


@router.get("/info")
def info(db: Session = Depends(get_db)):
    """Dados que o site precisa para se montar (sem login)."""
    conf = regras.configuracoes(db, apenas_publicas=True)
    return {
        "nome_produto": conf.get("nome_produto"),
        "marca_subtitulo": conf.get("marca_subtitulo"),
        "slogan": conf.get("slogan"),
        "empresa_titular": conf.get("empresa_titular"),
        "contato_whatsapp": conf.get("contato_whatsapp"),
        "contato_email": conf.get("contato_email"),
        "horas_teste": regras.horas_teste(db),
        "usuarios_incluidos": regras.usuarios_incluidos(db),
        "planos": regras.planos(db),
        "pix_configurado": bool(conf.get("pix_chave")),
    }


@router.post("/cadastro")
def cadastro(dados: CadastroPublicoIn, db: Session = Depends(get_db)):
    """Cria a conta do assinante e libera o período de teste."""
    email = dados.email.strip().lower()
    if not dados.nome.strip():
        raise HTTPException(400, "Informe seu nome")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "Informe um e-mail válido")
    if len(dados.senha or "") < 6:
        raise HTTPException(400, "A senha precisa ter pelo menos 6 caracteres")
    if db.query(Usuario).filter(Usuario.email == email).first():
        raise HTTPException(400, "Já existe uma conta com este e-mail. Faça login.")

    plano = regras.plano_por_codigo(db, dados.plano)

    usuario = Usuario(
        nome=dados.nome.strip(),
        email=email,
        senha_hash=hash_senha(dados.senha),
        perfil="ADMIN",
        telefone=dados.telefone,
        documento=dados.documento,
    )
    db.add(usuario)
    db.flush()

    empresa = Empresa(
        razao_social=(dados.empresa or dados.nome).strip(),
        nome_fantasia=(dados.empresa or dados.nome).strip(),
        cnpj=dados.documento,
        cidade=dados.cidade,
        uf=dados.uf,
        telefone=dados.telefone,
        email=email,
        responsavel=dados.nome.strip(),
        dono_id=usuario.id,
    )
    db.add(empresa)
    db.flush()

    usuario.empresa_id = empresa.id
    criar_plano_padrao(db, empresa.id)
    criar_centros_custo_padrao(db, empresa.id)
    criar_operacoes_padrao(db, empresa.id)
    criar_cadastros_contrato_padrao(db, empresa.id)

    assinatura = regras.criar_assinatura(db, usuario.id, empresa.id, plano["codigo"])
    db.commit()
    db.refresh(usuario)

    return {
        "token": gerar_token(usuario.id, usuario.email),
        "usuario": serializar(usuario, exclude={"senha_hash"}),
        "empresa": serializar(empresa),
        "assinatura": regras.situacao(db, assinatura),
        "pagamento": regras.dados_pagamento(db, assinatura),
        "mensagem": (
            f"Conta criada. Seu acesso está liberado por {regras.horas_teste(db)} horas para teste."
        ),
    }
