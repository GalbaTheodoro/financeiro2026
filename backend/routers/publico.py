"""Área pública: informações do site, planos e cadastro de novos assinantes."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from .. import assinaturas as regras
from .. import cotacoes as fontes_cotacoes
from .. import descontos
from .. import mercado
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


@router.get("/cotacoes")
def cotacoes(resposta: Response, db: Session = Depends(get_db)):
    """Cotações do café (NY, Londres, B3) e moedas para a faixa do rodapé."""
    if regras.config(db, "cotacoes_ativas", "1").strip() in ("0", "nao", "não", "false"):
        return {"ativo": False, "grupos": []}
    try:
        minutos = int(float(regras.config(db, "cotacoes_minutos", "10")))
    except ValueError:
        minutos = 10
    dados = fontes_cotacoes.obter(db, minutos)
    # o navegador pode reaproveitar por 1 minuto; o servidor guarda por mais tempo
    resposta.headers["Cache-Control"] = "public, max-age=60"
    return {"ativo": True, **dados}


def _minutos(db: Session, chave: str, padrao: int) -> int:
    try:
        return int(float(regras.config(db, chave, str(padrao))))
    except ValueError:
        return padrao


def _painel_ligado(db: Session) -> None:
    if regras.config(db, "cotacoes_ativas", "1").strip() in ("0", "nao", "não", "false"):
        raise HTTPException(404, "O painel de mercado está desligado.")


def _data(texto: str | None, campo: str) -> date | None:
    if not texto:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError as erro:
        raise HTTPException(422, f"Data inválida em '{campo}': use AAAA-MM-DD.") from erro


@router.get("/mercado/resumo")
def mercado_resumo(resposta: Response, db: Session = Depends(get_db)):
    """Último fechamento de cada série (bolsas, Cepea, Ptax, preços por cidade)."""
    _painel_ligado(db)
    agnocafe = regras.config(db, "mercado_agnocafe", "1").strip() not in ("0", "nao", "não", "false")
    meta = mercado.garantir_atualizado(db, _minutos(db, "mercado_minutos", 30), agnocafe)
    dados = mercado.resumo(db, meta)
    if not agnocafe:
        dados["grupos"] = [g for g in dados["grupos"] if g["chave"] != "agnocafe"]
    resposta.headers["Cache-Control"] = "public, max-age=120"
    return dados


@router.get("/mercado/historico")
def mercado_historico(
    resposta: Response,
    grupo: str | None = Query(None, max_length=30),
    item: str | None = Query(None, max_length=140),
    cidade: str | None = Query(None, max_length=80),
    de: str | None = None,
    ate: str | None = None,
    db: Session = Depends(get_db),
):
    """Histórico diário filtrado por série, item/contrato, cidade e período."""
    _painel_ligado(db)
    inicio, fim = _data(de, "de"), _data(ate, "ate")
    if not (grupo or item or cidade):
        raise HTTPException(422, "Escolha uma série ou uma cidade.")
    if grupo == "agnocafe" and regras.config(db, "mercado_agnocafe", "1").strip() in ("0", "nao", "não", "false"):
        return {"linhas": []}
    if not inicio and not fim:
        inicio = mercado.hoje_brasil() - timedelta(days=90)
    linhas = mercado.historico(db, grupo, item, cidade, inicio, fim)
    if regras.config(db, "mercado_agnocafe", "1").strip() in ("0", "nao", "não", "false"):
        linhas = [linha for linha in linhas if linha["grupo"] != "agnocafe"]
    resposta.headers["Cache-Control"] = "public, max-age=120"
    return {"linhas": linhas}


@router.get("/mercado/noticias")
def mercado_noticias(
    resposta: Response,
    cultura: str = Query("", max_length=40),
    regiao: str = Query("", max_length=60),
    busca: str = Query("", max_length=80),
    de: str | None = None,
    ate: str | None = None,
    db: Session = Depends(get_db),
):
    """Notícias do café e do agro, com filtro por cultura, região, texto e período."""
    _painel_ligado(db)
    dados = mercado.obter_noticias(db, _minutos(db, "noticias_minutos", 20))
    todas = dados.get("itens", [])
    itens = mercado.filtrar_noticias(todas, cultura, regiao, busca, _data(de, "de"), _data(ate, "ate"))
    resposta.headers["Cache-Control"] = "public, max-age=120"
    return {"atualizado_em": dados.get("atualizado_em"), "fontes": dados.get("fontes", {}),
            "total": len(todas), "itens": itens[:200],
            "culturas": [c for c, _ in mercado.CULTURAS] + ["Geral"],
            "regioes": [r for r, _ in mercado.REGIOES]}


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
    # o cupom digitado no cadastro. Código errado não derruba a conta recém-criada:
    # a conta entra, o aviso vai junto e a pessoa tenta de novo na tela de pagamento.
    aviso_cupom = ""
    if dados.cupom:
        try:
            cupom = descontos.aplicar(db, assinatura, dados.cupom)
            aviso_cupom = (f" Cupom {cupom.codigo} aplicado: "
                           f"{float(cupom.percentual):.0f}% de desconto na primeira cobrança.")
        except descontos.CupomInvalido as erro:
            aviso_cupom = f" {erro}"
    db.commit()
    db.refresh(usuario)

    return {
        "token": gerar_token(usuario.id, usuario.email),
        "usuario": serializar(usuario, exclude={"senha_hash"}),
        "empresa": serializar(empresa),
        "assinatura": regras.situacao(db, assinatura),
        "pagamento": regras.dados_pagamento(db, assinatura),
        "mensagem": (
            f"Conta criada. Seu acesso está liberado por {regras.horas_teste(db)} horas "
            f"para teste.{aviso_cupom}"
        ),
    }


@router.get("/cupom")
def conferir_cupom(codigo: str = Query(...), db: Session = Depends(get_db)):
    """Confere o cupom antes do cadastro, para a pessoa ver o desconto na hora.

    Não diz *quanto* é o desconto em reais: o plano ainda não foi escolhido de
    verdade. Diz a porcentagem, e a tela faz a conta.
    """
    try:
        cupom = descontos.validar(db, codigo)
    except descontos.CupomInvalido as erro:
        raise HTTPException(400, str(erro)) from None
    return {"codigo": cupom.codigo, "percentual": float(cupom.percentual or 0),
            "descricao": cupom.descricao or ""}
