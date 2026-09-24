"""Configuração de e-mail da empresa e envio de teste.

Rotas
-----
GET    /api/email/config      como está configurado (nunca devolve a senha)
PUT    /api/email/config      salva a configuração
POST   /api/email/teste       manda um e-mail de teste para conferir os dados

O envio da nota fiscal em si mora no router de emissão (`/api/nfe/...`), junto
com a transmissão — é lá que estão a nota, o XML e o cliente.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import correio
from ..database import get_db
from ..deps import acesso_liberado, validar_empresa
from ..models import ConfigEmail, Empresa, Usuario

router = APIRouter(prefix="/api/email", tags=["email"])

SEGURANCAS = ("TLS", "SSL", "NENHUMA")


class ConfigEmailIn(BaseModel):
    empresa_id: int
    servidor: str | None = None
    porta: int | None = 587
    seguranca: str | None = "TLS"
    usuario: str | None = None
    # em branco = mantém a senha que já está guardada
    senha: str | None = None
    remetente_nome: str | None = None
    remetente_email: str | None = None
    responder_para: str | None = None
    email_contador: str | None = None
    copia_empresa: bool = True
    enviar_ao_autorizar: bool = True
    assunto: str | None = None
    texto: str | None = None
    ativo: bool = True


class TesteIn(BaseModel):
    empresa_id: int
    para: str | None = None


def config_da_empresa(db: Session, empresa_id: int) -> ConfigEmail | None:
    return db.query(ConfigEmail).filter(ConfigEmail.empresa_id == empresa_id).first()


def _ficha(config: ConfigEmail | None, empresa: Empresa) -> dict:
    """O que a tela recebe. **A senha nunca sai daqui** — só o aviso de que existe."""
    if config is None:
        return {
            "configurado": False,
            "tem_senha": False,
            "porta": 587,
            "seguranca": "TLS",
            "copia_empresa": True,
            "enviar_ao_autorizar": True,
            "remetente_nome": empresa.razao_social,
            "remetente_email": empresa.email,
            "assunto": correio.ASSUNTO_PADRAO,
            "texto": correio.TEXTO_PADRAO,
            "ativo": True,
            "email_empresa": empresa.email,
            "sugestoes": correio.SUGESTOES,
        }
    return {
        "configurado": bool((config.servidor or "").strip()),
        "tem_senha": bool(config.senha),
        "servidor": config.servidor,
        "porta": config.porta,
        "seguranca": config.seguranca,
        "usuario": config.usuario,
        "remetente_nome": config.remetente_nome,
        "remetente_email": config.remetente_email,
        "responder_para": config.responder_para,
        "email_contador": config.email_contador,
        "copia_empresa": config.copia_empresa,
        "enviar_ao_autorizar": config.enviar_ao_autorizar,
        "assunto": config.assunto or correio.ASSUNTO_PADRAO,
        "texto": config.texto or correio.TEXTO_PADRAO,
        "ativo": config.ativo,
        "ultimo_envio_em": config.ultimo_envio_em,
        "ultimo_erro": config.ultimo_erro,
        "email_empresa": empresa.email,
        "sugestoes": correio.SUGESTOES,
    }


@router.get("/config")
def ler_config(empresa_id: int, db: Session = Depends(get_db),
               usuario: Usuario = Depends(acesso_liberado)):
    empresa = validar_empresa(db, empresa_id, usuario)
    return _ficha(config_da_empresa(db, empresa_id), empresa)


@router.put("/config")
def salvar_config(dados: ConfigEmailIn, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(acesso_liberado)):
    empresa = validar_empresa(db, dados.empresa_id, usuario)
    seguranca = (dados.seguranca or "TLS").strip().upper()
    if seguranca not in SEGURANCAS:
        raise HTTPException(400, "A segurança é TLS, SSL ou NENHUMA.")
    porta = int(dados.porta or 587)
    if not 1 <= porta <= 65535:
        raise HTTPException(400, "A porta vai de 1 a 65535 (587 para TLS, 465 para SSL).")
    for campo, rotulo in (("remetente_email", "e-mail do remetente"),
                          ("responder_para", "e-mail de resposta"),
                          ("email_contador", "e-mail do contador")):
        valor = (getattr(dados, campo) or "").strip()
        if valor and not correio.endereco_valido(valor):
            raise HTTPException(400, f"O {rotulo} não parece um endereço válido: {valor}")

    config = config_da_empresa(db, dados.empresa_id)
    if config is None:
        config = ConfigEmail(empresa_id=dados.empresa_id)
        db.add(config)
    config.servidor = (dados.servidor or "").strip() or None
    config.porta = porta
    config.seguranca = seguranca
    config.usuario = (dados.usuario or "").strip() or None
    # senha em branco não apaga a que já existe: a tela nunca recebe a senha de
    # volta, então mandar vazio quer dizer "não mexi neste campo"
    if dados.senha:
        config.senha = correio.cifrar(dados.senha)
    config.remetente_nome = (dados.remetente_nome or "").strip() or empresa.razao_social
    config.remetente_email = (dados.remetente_email or "").strip() or None
    config.responder_para = (dados.responder_para or "").strip() or None
    config.email_contador = (dados.email_contador or "").strip() or None
    config.copia_empresa = bool(dados.copia_empresa)
    config.enviar_ao_autorizar = bool(dados.enviar_ao_autorizar)
    config.assunto = (dados.assunto or "").strip() or None
    config.texto = (dados.texto or "").strip() or None
    config.ativo = bool(dados.ativo)
    config.atualizado_em = datetime.utcnow()
    db.commit()
    db.refresh(config)
    return _ficha(config, empresa)


@router.post("/teste")
def enviar_teste(dados: TesteIn, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(acesso_liberado)):
    """Manda um e-mail curto para conferir servidor, porta, usuário e senha."""
    empresa = validar_empresa(db, dados.empresa_id, usuario)
    config = config_da_empresa(db, dados.empresa_id)
    if config is None or not (config.servidor or "").strip():
        raise HTTPException(400, "Salve a configuração de e-mail antes de testar.")
    destino = (dados.para or "").strip() or (config.remetente_email or "").strip()
    if not correio.endereco_valido(destino):
        raise HTTPException(400, "Diga para qual endereço mandar o teste.")
    try:
        enviado = correio.enviar(
            config, [destino],
            f"Teste de envio - {empresa.razao_social}",
            "Este é um e-mail de teste do AgroDock.\n\n"
            "Se você recebeu esta mensagem, o envio de notas fiscais por e-mail está "
            "funcionando: as notas autorizadas vão sair desta mesma conta, com o XML e "
            "a DANFE em PDF anexados.\n\n"
            f"{empresa.razao_social}")
    except correio.ErroEmail as erro:
        config.ultimo_erro = str(erro)[:300]
        db.commit()
        raise HTTPException(400, str(erro)) from None
    config.ultimo_envio_em = datetime.utcnow()
    config.ultimo_erro = None
    db.commit()
    return {"ok": True, "mensagem": f"E-mail de teste enviado para {destino}.",
            "envio": enviado}
