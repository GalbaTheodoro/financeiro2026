"""Dependências compartilhadas: autenticação, assinatura e isolamento de contas."""
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from . import assinaturas as regras
from . import planos as catalogo
from .database import get_db
from .models import Assinatura, Empresa, Usuario
from .security import ler_token
from .utils import moeda_br

# 402 = conta sem assinatura válida (o front redireciona para a tela de pagamento)
HTTP_ASSINATURA = status.HTTP_402_PAYMENT_REQUIRED
# 423 = usuário bloqueado pelo administrador ou com a data de acesso vencida
HTTP_USUARIO_BLOQUEADO = 423


def usuario_atual(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Usuario:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Não autenticado")
    payload = ler_token(authorization.split(" ", 1)[1].strip())
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada, faça login novamente")
    usuario = db.get(Usuario, payload["sub"])
    if not usuario:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário inválido ou inativo")
    if not usuario.ativo or usuario.bloqueado_admin:
        raise HTTPException(HTTP_USUARIO_BLOQUEADO,
                            "Seu usuário está bloqueado. Fale com o administrador.")
    vencido = regras.acesso_do_usuario_vencido(usuario)
    if vencido:
        raise HTTPException(HTTP_USUARIO_BLOQUEADO, vencido)
    return usuario


def somente_admin(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
    if usuario.perfil not in ("ADMIN", "MASTER"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas administradores podem fazer isso")
    return usuario


def somente_master(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
    if usuario.perfil != "MASTER":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Área exclusiva do administrador do sistema"
        )
    return usuario


# --------------------------------------------------------------------------- #
# Assinatura
# --------------------------------------------------------------------------- #
def assinatura_do_usuario(db: Session, usuario: Usuario) -> Assinatura | None:
    """A assinatura da conta. Usuários MASTER e usuários internos não têm."""
    if usuario.perfil == "MASTER":
        return None
    assinatura = (
        db.query(Assinatura).filter(Assinatura.usuario_id == usuario.id).first()
    )
    if assinatura:
        return assinatura
    # usuário criado dentro de uma conta assinante herda a assinatura do dono
    if usuario.empresa_id:
        empresa = db.get(Empresa, usuario.empresa_id)
        if empresa and empresa.dono_id:
            return (
                db.query(Assinatura).filter(Assinatura.usuario_id == empresa.dono_id).first()
            )
    return None


def situacao_da_conta(db: Session, usuario: Usuario) -> dict:
    return regras.situacao(db, assinatura_do_usuario(db, usuario))


def contar_usuarios_conta(db: Session, usuario: Usuario) -> int:
    """Usuários ativos que consomem as licenças da conta."""
    permitidas = empresas_permitidas(db, usuario)
    if permitidas is None:
        return db.query(Usuario).filter(Usuario.ativo.is_(True)).count()
    return (
        db.query(Usuario)
        .filter(Usuario.ativo.is_(True), Usuario.empresa_id.in_(permitidas or [0]))
        .count()
    )


def checar_limite_usuarios(db: Session, usuario: Usuario):
    """Barra a criação/ativação de usuário acima do contratado."""
    assinatura = assinatura_do_usuario(db, usuario)
    if assinatura is None:  # conta interna (MASTER) não tem limite
        return
    limite = regras.limite_usuarios(db, assinatura)
    usados = contar_usuarios_conta(db, usuario)
    if usados >= limite:
        por_pacote = regras.usuarios_por_pacote(db)
        valor = regras.valor_pacote(db, assinatura)
        raise HTTPException(
            400,
            f"Seu plano permite {limite} usuário(s) e você já tem {usados}. "
            f"Contrate um pacote de +{por_pacote} usuários por {moeda_br(valor)} "
            "em Minha Assinatura.",
        )


# --------------------------------------------------------------------------- #
# Isolamento entre contas
# --------------------------------------------------------------------------- #
def empresas_permitidas(db: Session, usuario: Usuario) -> set[int] | None:
    """Ids de empresa que o usuário pode acessar. None = todas (MASTER)."""
    if usuario.perfil == "MASTER":
        return None
    ids = {
        e.id for e in db.query(Empresa.id).filter(Empresa.dono_id == usuario.id).all()
    }
    ids = {linha[0] if isinstance(linha, tuple) else linha for linha in ids}
    if usuario.empresa_id:
        ids.add(usuario.empresa_id)
    return ids


def validar_empresa(db: Session, empresa_id: int, usuario: Usuario | None = None) -> Empresa:
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(404, "Empresa não encontrada")
    if usuario is not None:
        permitidas = empresas_permitidas(db, usuario)
        if permitidas is not None and empresa.id not in permitidas:
            raise HTTPException(403, "Esta empresa não pertence à sua conta")
    return empresa


async def acesso_liberado(
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> Usuario:
    """Bloqueia a conta sem assinatura válida e impede acesso a empresas de terceiros.

    A verificação da empresa é feita aqui, num ponto único: tanto no `empresa_id`
    da query quanto no corpo JSON das requisições de gravação.
    """
    situacao = situacao_da_conta(db, usuario)
    if not situacao.get("liberado"):
        raise HTTPException(HTTP_ASSINATURA, situacao.get("mensagem") or "Assinatura inativa")

    permitidas = empresas_permitidas(db, usuario)
    if permitidas is None:  # MASTER acessa tudo
        return usuario

    def conferir(valor):
        try:
            empresa_id = int(valor)
        except (TypeError, ValueError):
            return
        if empresa_id not in permitidas:
            raise HTTPException(403, "Esta empresa não pertence à sua conta")

    conferir(request.query_params.get("empresa_id"))

    if request.method in ("POST", "PUT", "PATCH"):
        tipo = request.headers.get("content-type", "")
        if tipo.startswith("application/json"):
            try:
                corpo = await request.json()
            except Exception:
                corpo = None
            if isinstance(corpo, dict) and corpo.get("empresa_id") is not None:
                conferir(corpo.get("empresa_id"))
    return usuario


# --------------------------------------------------------------------------- #
# O que o plano da conta libera
# --------------------------------------------------------------------------- #
def modulos_da_conta(db: Session, usuario: Usuario) -> tuple[str, ...]:
    """Os módulos que essa conta enxerga.

    Sai do plano dela, com as exceções que o administrador do site combinou —
    ver ``assinaturas.modulos_da_assinatura``. Conta interna (MASTER) e conta
    sem assinatura vinculada usam tudo: quem não tem assinatura é a operação do
    próprio sistema, não um assinante.
    """
    if usuario.perfil == "MASTER":
        return tuple(catalogo.todos_os_modulos())
    return regras.modulos_da_assinatura(db, assinatura_do_usuario(db, usuario))


def exigir_modulo(modulo: str):
    """Dependência que fecha a porta do que o plano não inclui.

    Esconder o botão no menu é conforto, não segurança: quem souber o endereço
    chama a rota do mesmo jeito. Por isso a barreira de verdade é esta, e a
    frase já diz em que plano está o que a pessoa procurou.
    """

    async def dependencia(
        usuario: Usuario = Depends(acesso_liberado),
        db: Session = Depends(get_db),
    ) -> Usuario:
        if modulo not in modulos_da_conta(db, usuario):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                regras.frase_de_bloqueio(db, modulo))
        return usuario

    return dependencia
