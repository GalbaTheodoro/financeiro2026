"""Autenticação e perfil do usuário logado."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import situacao_da_conta, usuario_atual
from ..models import Usuario
from ..schemas import LoginIn, TrocarSenhaIn
from ..security import gerar_token, hash_senha, verificar_senha
from ..utils import serializar

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(dados: LoginIn, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.email == dados.email.strip().lower()).first()
    if not usuario or not verificar_senha(dados.senha, usuario.senha_hash):
        raise HTTPException(401, "E-mail ou senha inválidos")
    if not usuario.ativo:
        raise HTTPException(403, "Usuário inativo")
    return {
        "token": gerar_token(usuario.id, usuario.email),
        "usuario": serializar(usuario, exclude={"senha_hash"}),
        "assinatura": situacao_da_conta(db, usuario),
    }


@router.get("/me")
def me(usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    return {
        **serializar(usuario, exclude={"senha_hash"}),
        "assinatura": situacao_da_conta(db, usuario),
    }


@router.post("/trocar-senha")
def trocar_senha(
    dados: TrocarSenhaIn,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    if not verificar_senha(dados.senha_atual or "", usuario.senha_hash):
        raise HTTPException(400, "Senha atual incorreta")
    usuario.senha_hash = hash_senha(dados.senha_nova)
    db.commit()
    return {"ok": True}
