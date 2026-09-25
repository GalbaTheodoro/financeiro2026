"""Assinatura do assinante e administração das contas (área MASTER)."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import assinaturas as regras
from .. import descontos
from ..database import get_db
from ..deps import (
    assinatura_do_usuario,
    contar_usuarios_conta,
    somente_master,
    usuario_atual,
)
from ..models import Assinatura, CupomDesconto, Empresa, Usuario
from ..schemas import (
    AcessoEmpresaIn,
    AcessoUsuarioIn,
    ConfiguracoesIn,
    LimiteUsuariosIn,
    EscolherPlanoIn,
    InformarPagamentoIn,
    PacotesUsuariosIn,
    StatusAssinaturaIn,
    AcessosContaIn,
    CupomAssinanteIn,
    CupomDescontoIn,
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


@router.post("/assinatura/cupom")
def aplicar_cupom(
    dados: CupomAssinanteIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    """O assinante digita o cupom na tela de pagamento e vê o valor cair na hora.

    Não usa `acesso_liberado`: quem está na tela de pagamento normalmente está
    justamente com a conta bloqueada.
    """
    assinatura = _minha(db, usuario)
    if assinatura.status == "ATIVA":
        raise HTTPException(
            400, "Esta assinatura já está paga. O cupom vale na primeira cobrança.")
    if not descontos.normalizar(dados.codigo):
        descontos.remover(assinatura)
        db.commit()
        return {"ok": True, "mensagem": "Cupom retirado.",
                "pagamento": regras.dados_pagamento(db, assinatura)}
    try:
        cupom = descontos.aplicar(db, assinatura, dados.codigo)
    except descontos.CupomInvalido as erro:
        raise HTTPException(400, str(erro)) from None
    db.commit()
    pagamento = regras.dados_pagamento(db, assinatura)
    return {
        "ok": True,
        "pagamento": pagamento,
        "mensagem": (f"Cupom {cupom.codigo} aplicado: "
                     f"{moeda_br(pagamento['cupom_desconto'])} de desconto. "
                     f"O Pix já está com o valor novo."),
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
    # o cupom sem montar o QR Code: a lista tem muitas contas e o Pix não é
    # desenhado aqui, só o valor que vai ser cobrado
    cupom = descontos.desconto_da_assinatura(a, float(a.valor or 0))
    return dict(
        serializar(a),
        valor_cobranca=cupom["valor_pagar"],
        cupom=cupom["codigo"],
        cupom_desconto=cupom["desconto"],
        usuario_nome=usuario.nome if usuario else "-",
        usuario_email=usuario.email if usuario else "-",
        usuario_telefone=usuario.telefone if usuario else "",
        empresa_nome=(empresa.nome_fantasia or empresa.razao_social) if empresa else "-",
        liberado=situacao.get("liberado"),
        situacao_titulo=situacao.get("titulo"),
        situacao_mensagem=situacao.get("mensagem"),
        limite_usuarios=regras.limite_usuarios(db, a),
        valor_pacote=regras.valor_pacote(db, a),
        plano_nome=situacao.get("plano_nome"),
        plano_rotulo=situacao.get("plano_rotulo"),
        plano_periodo=situacao.get("plano_periodo"),
        modulos=situacao.get("modulos", []),
        modulos_do_plano=situacao.get("modulos_do_plano", []),
        modulos_extras=situacao.get("modulos_extras", []),
        modulos_bloqueados=situacao.get("modulos_bloqueados", []),
    )


@router.get("/admin/modulos")
def listar_modulos(db: Session = Depends(get_db), _: Usuario = Depends(somente_master)):
    """O catálogo de menus e a grade de cada plano — é o que a tela de configurações desenha."""
    from .. import planos as catalogo

    return {
        "modulos": [
            {"codigo": codigo, "nome": nome, "texto": texto,
             "rotas": list(catalogo.ROTAS.get(codigo, ()))}
            for codigo, (nome, texto) in catalogo.MODULOS.items()
        ],
        "planos": [
            {"nivel": p["nivel"], "nome": p["nome"],
             "chave": catalogo.chave_dos_modulos(p["nivel"]),
             "modulos": list(regras.modulos_do_nivel(db, p["nivel"])),
             "padrao": list(catalogo.modulos_do_nivel(p["nivel"]))}
            for p in catalogo.NIVEIS
        ],
    }


@router.post("/admin/assinaturas/{assinatura_id}/modulos")
def acessos_da_conta(assinatura_id: int, dados: AcessosContaIn,
                     db: Session = Depends(get_db),
                     _: Usuario = Depends(somente_master)):
    """Liga e desliga menus **desta conta**, fora do que o plano dá.

    É a negociação: o cliente fechou o Plano 1 mas ficou combinado dar a nota
    fiscal. O módulo entra como **extra** e ele passa a ver a tela — o plano e o
    valor cobrado continuam os mesmos. Tirar um menu que o plano dava é o
    caminho contrário, pelos **bloqueados**.
    """
    from .. import planos as catalogo

    assinatura = db.get(Assinatura, assinatura_id)
    if not assinatura:
        raise HTTPException(404, "Assinatura não encontrada")
    nivel, _periodo = catalogo.separar(assinatura.plano)
    do_plano = regras.modulos_do_nivel(db, nivel)

    extras = catalogo.separar_modulos(",".join(dados.extras or []))
    bloqueados = catalogo.separar_modulos(",".join(dados.bloqueados or []))
    repetido = [m for m in extras if m in bloqueados]
    if repetido:
        nomes = ", ".join(catalogo.MODULOS[m][0] for m in repetido)
        raise HTTPException(
            400, f"{nomes} está ao mesmo tempo liberado e bloqueado. Escolha um dos dois.")
    # extra que o plano já dá não é extra: não guarda, para a tela não mentir
    extras = tuple(m for m in extras if m not in do_plano)
    bloqueados = tuple(m for m in bloqueados if m in do_plano)

    assinatura.modulos_extras = catalogo.juntar_modulos(extras) or None
    assinatura.modulos_bloqueados = catalogo.juntar_modulos(bloqueados) or None
    if dados.observacao is not None:
        assinatura.observacao_admin = (dados.observacao or "").strip() or None
    db.commit()
    db.refresh(assinatura)
    liberados = regras.modulos_da_assinatura(db, assinatura)
    return {
        "ok": True,
        "linha": _linha_assinatura(db, assinatura),
        "mensagem": (
            f"Acesso combinado: a conta enxerga "
            f"{', '.join(catalogo.MODULOS[m][0] for m in liberados) or 'nenhum menu'}."
        ),
    }


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
        # a tela precisa dos planos para deixar o administrador trocar o de alguém
        "planos": regras.planos(db),
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
    if dados.status not in ("TESTE", "AGUARDANDO", "ATIVA", "EXPIRADA", "CANCELADA", "BLOQUEADA"):
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


# --------------------------------------------------------------------------- #
# Empresas e acessos (MASTER): liberar/bloquear por data e limite de usuários
# --------------------------------------------------------------------------- #
def _usuarios_da_conta(db: Session, a: Assinatura) -> list[Usuario]:
    """Dono da assinatura + usuários ligados às empresas dele."""
    empresas = [e.id for e in db.query(Empresa).filter(Empresa.dono_id == a.usuario_id).all()]
    if a.empresa_id and a.empresa_id not in empresas:
        empresas.append(a.empresa_id)
    query = db.query(Usuario).filter(
        (Usuario.id == a.usuario_id) | (Usuario.empresa_id.in_(empresas or [0]))
    )
    return query.order_by(Usuario.id).all()


def _linha_empresa(db: Session, a: Assinatura) -> dict:
    hoje = date.today()
    base = _linha_assinatura(db, a)
    empresas = db.query(Empresa).filter(Empresa.dono_id == a.usuario_id).order_by(Empresa.id).all()
    if not empresas and a.empresa_id:
        e = db.get(Empresa, a.empresa_id)
        empresas = [e] if e else []
    usuarios = _usuarios_da_conta(db, a)
    em_uso = sum(1 for u in usuarios if u.ativo and not u.bloqueado_admin and u.perfil != "MASTER")
    return dict(
        base,
        empresas=[{
            "id": e.id, "nome": e.nome_fantasia or e.razao_social, "cnpj": e.cnpj or "",
            "cidade": e.cidade or "", "uf": e.uf or "",
        } for e in empresas],
        cnpj=empresas[0].cnpj if empresas and empresas[0].cnpj else "",
        usuarios_em_uso=em_uso,
        limite_personalizado=bool(a.limite_usuarios),
        limite_padrao=regras.usuarios_incluidos(db)
        + (a.pacotes_usuarios or 0) * regras.usuarios_por_pacote(db),
        usuarios=[{
            "id": u.id, "nome": u.nome, "email": u.email, "perfil": u.perfil,
            "ativo": bool(u.ativo and not u.bloqueado_admin),
            "acesso_ate": u.acesso_ate.isoformat() if u.acesso_ate else None,
            "vencido": bool(u.acesso_ate and u.acesso_ate < hoje),
            "dono": u.id == a.usuario_id,
        } for u in usuarios],
    )


@router.get("/admin/empresas")
def listar_empresas(db: Session = Depends(get_db), _: Usuario = Depends(somente_master)):
    """Todas as empresas assinantes, com situação, prazo e usuários."""
    assinaturas = db.query(Assinatura).order_by(Assinatura.criado_em.desc()).all()
    # a empresa do próprio administrador do site não precisa de controle de acesso
    masters = {u.id for u in db.query(Usuario).filter(Usuario.perfil == "MASTER").all()}
    linhas = [_linha_empresa(db, a) for a in assinaturas if a.usuario_id not in masters]
    hoje = date.today()
    vencem = [l for l in linhas if l["liberado"] and l["data_fim"]
              and 0 <= (date.fromisoformat(l["data_fim"]) - hoje).days <= 15]
    return {
        "linhas": linhas,
        "resumo": {
            "total": len(linhas),
            "liberadas": sum(1 for l in linhas if l["liberado"]),
            "bloqueadas": sum(1 for l in linhas if not l["liberado"]),
            "vencem_15_dias": len(vencem),
            "usuarios": sum(l["usuarios_em_uso"] for l in linhas),
        },
        "usuarios_incluidos": regras.usuarios_incluidos(db),
    }


def _assinatura_ou_404(db: Session, assinatura_id: int) -> Assinatura:
    assinatura = db.get(Assinatura, assinatura_id)
    if not assinatura:
        raise HTTPException(404, "Empresa não encontrada")
    return assinatura


@router.post("/admin/empresas/{assinatura_id}/acesso")
def acesso_empresa(
    assinatura_id: int,
    dados: AcessoEmpresaIn,
    db: Session = Depends(get_db),
    master: Usuario = Depends(somente_master),
):
    """Libera a empresa até uma data (bloqueia sozinha depois) ou bloqueia agora."""
    assinatura = _assinatura_ou_404(db, assinatura_id)
    acao = (dados.acao or "").upper()
    if acao == "LIBERAR":
        if not dados.ate:
            raise HTTPException(400, "Informe até que dia o acesso fica liberado.")
        if dados.ate < date.today():
            raise HTTPException(400, "A data de liberação não pode ser anterior a hoje.")
        assinatura.status = "ATIVA"
        assinatura.data_inicio = assinatura.data_inicio or date.today()
        assinatura.data_fim = dados.ate
        assinatura.confirmado_em = datetime.utcnow()
        assinatura.confirmado_por_id = master.id
    elif acao == "BLOQUEAR":
        assinatura.status = "BLOQUEADA"
    else:
        raise HTTPException(400, "Ação inválida: use LIBERAR ou BLOQUEAR.")
    if dados.observacao is not None and dados.observacao.strip():
        assinatura.observacao_admin = dados.observacao.strip()
    db.commit()
    return _linha_empresa(db, assinatura)


@router.post("/admin/empresas/{assinatura_id}/limite")
def limite_empresa(
    assinatura_id: int,
    dados: LimiteUsuariosIn,
    db: Session = Depends(get_db),
    _: Usuario = Depends(somente_master),
):
    """Define quantos usuários a empresa pode ter (ex.: aumentou após pagamento)."""
    assinatura = _assinatura_ou_404(db, assinatura_id)
    limite = dados.limite or None
    if limite is not None and not 1 <= limite <= 500:
        raise HTTPException(400, "O limite precisa ficar entre 1 e 500 usuários.")
    assinatura.limite_usuarios = limite
    db.commit()
    return _linha_empresa(db, assinatura)


@router.post("/admin/usuarios/{usuario_id}/acesso")
def acesso_usuario(
    usuario_id: int,
    dados: AcessoUsuarioIn,
    db: Session = Depends(get_db),
    master: Usuario = Depends(somente_master),
):
    """Bloqueia/libera um usuário e define até quando ele pode entrar."""
    usuario = db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(404, "Usuário não encontrado")
    if usuario.perfil == "MASTER":
        raise HTTPException(400, "O administrador do site não pode ser bloqueado.")
    usuario.ativo = bool(dados.ativo)
    usuario.bloqueado_admin = not bool(dados.ativo)
    usuario.acesso_ate = dados.acesso_ate
    db.commit()
    return {
        "id": usuario.id, "nome": usuario.nome, "email": usuario.email,
        "ativo": usuario.ativo,
        "acesso_ate": usuario.acesso_ate.isoformat() if usuario.acesso_ate else None,
    }


# --------------------------------------------------------------------------- #
# Endereços da SEFAZ (MASTER)
# --------------------------------------------------------------------------- #
@router.get("/admin/sefaz")
def listar_enderecos_sefaz(modelo: str = "65", db: Session = Depends(get_db),
                           _: Usuario = Depends(somente_master)):
    """Um estado por linha, com os oito endereços e de onde veio cada um."""
    from .. import sefaz_enderecos as enderecos

    try:
        enderecos.conferir_modelo(modelo)
    except enderecos.EnderecoFaltando as erro:
        raise HTTPException(400, str(erro)) from None
    return {"modelo": modelo, "linhas": enderecos.quadro(db, modelo),
            "servicos": enderecos.SERVICOS}


@router.put("/admin/sefaz/{modelo}/{uf}")
def salvar_endereco_sefaz(modelo: str, uf: str, dados: dict,
                          db: Session = Depends(get_db),
                          _: Usuario = Depends(somente_master)):
    from .. import sefaz_enderecos as enderecos

    try:
        enderecos.salvar(db, modelo, uf, dados or {})
    except enderecos.EnderecoFaltando as erro:
        raise HTTPException(400, str(erro)) from None
    db.commit()
    return {"ok": True, "linhas": enderecos.quadro(db, modelo)}


@router.delete("/admin/sefaz/{modelo}/{uf}")
def restaurar_endereco_sefaz(modelo: str, uf: str, db: Session = Depends(get_db),
                             _: Usuario = Depends(somente_master)):
    """Volta o estado ao padrão de fábrica, apagando o que foi editado."""
    from .. import sefaz_enderecos as enderecos

    try:
        enderecos.conferir_modelo(modelo)
    except enderecos.EnderecoFaltando as erro:
        raise HTTPException(400, str(erro)) from None
    enderecos.voltar_ao_padrao(db, modelo, uf)
    db.commit()
    return {"ok": True, "linhas": enderecos.quadro(db, modelo)}


# --------------------------------------------------------------------------- #
# Cupons de desconto (MASTER)
# --------------------------------------------------------------------------- #
@router.get("/admin/cupons")
def listar_cupons(db: Session = Depends(get_db), _: Usuario = Depends(somente_master)):
    return {"linhas": descontos.listar(db)}


@router.post("/admin/cupons")
def criar_cupom(dados: CupomDescontoIn, db: Session = Depends(get_db),
                _: Usuario = Depends(somente_master)):
    try:
        cupom = descontos.criar(db, dados.codigo or "", dados.percentual,
                                dados.descricao,
                                True if dados.ativo is None else dados.ativo)
    except descontos.CupomInvalido as erro:
        raise HTTPException(400, str(erro)) from None
    db.commit()
    return descontos.serializar(cupom)


@router.put("/admin/cupons/{cupom_id}")
def editar_cupom(cupom_id: int, dados: CupomDescontoIn, db: Session = Depends(get_db),
                 _: Usuario = Depends(somente_master)):
    cupom = db.get(CupomDesconto, cupom_id)
    if not cupom:
        raise HTTPException(404, "Cupom não encontrado")
    try:
        descontos.editar(db, cupom, dados.codigo, dados.percentual,
                         dados.descricao, dados.ativo)
    except descontos.CupomInvalido as erro:
        raise HTTPException(400, str(erro)) from None
    db.commit()
    return descontos.serializar(cupom)


@router.delete("/admin/cupons/{cupom_id}")
def apagar_cupom(cupom_id: int, db: Session = Depends(get_db),
                 _: Usuario = Depends(somente_master)):
    """Apaga o cupom. Quem já aplicou não perde o desconto: a porcentagem fica
    copiada na assinatura, então o combinado com aquele cliente é respeitado."""
    cupom = db.get(CupomDesconto, cupom_id)
    if not cupom:
        raise HTTPException(404, "Cupom não encontrado")
    db.delete(cupom)
    db.commit()
    return {"ok": True}


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
