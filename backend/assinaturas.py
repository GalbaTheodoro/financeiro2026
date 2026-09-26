"""Regras de assinatura, planos, configurações do sistema e Pix."""
import re
import unicodedata
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from . import descontos
from . import planos as catalogo
from .models import Assinatura, Configuracao
from .utils import adicionar_meses, dinheiro

# chave -> (valor padrão, descrição, pública no site)
CONFIGURACOES_PADRAO: dict[str, tuple[str, str, bool]] = {
    "nome_produto": ("AgroDock", "Nome exibido no site e no topo do sistema", True),
    "marca_subtitulo": (
        "Contratos e Gestão", "Frase curta ao lado do nome (aparece no logotipo)", True
    ),
    "slogan": (
        "Emita nota fiscal e cupom fiscal, venda na tela de balcão e controle o "
        "estoque — com os contratos de assessoria, o contas a pagar e a receber, "
        "o caixa, a DRE e o balancete no mesmo lugar.",
        "Frase de apoio na página inicial",
        True,
    ),
    "empresa_titular": ("", "Sua empresa / assessoria (aparece no rodapé do site)", True),
    "contato_whatsapp": ("", "WhatsApp de suporte exibido no site", True),
    "contato_email": ("", "E-mail de suporte exibido no site", True),
    "pix_chave": ("", "Chave Pix que recebe os pagamentos das assinaturas", True),
    "pix_titular": ("", "Nome do titular da chave Pix (como aparece no comprovante)", True),
    "pix_cidade": ("SAO PAULO", "Cidade do titular (usada no Pix copia e cola)", False),
    "pix_banco": ("", "Banco da chave Pix (informativo)", True),
    # o preço de cada plano em cada prazo mora em planos.py (oito chaves,
    # acrescentadas logo abaixo por configuracoes_de_preco)
    "plano_semestral_meses": ("6", "Duração do plano semestral em meses", True),
    "plano_anual_meses": ("12", "Duração do plano anual em meses", True),
    "horas_teste": ("48", "Horas de acesso liberado logo após o cadastro", True),
    "usuarios_incluidos": ("3", "Usuários já inclusos no valor da assinatura (por empresa)", True),
    "usuarios_por_pacote": ("5", "Usuários liberados por pacote extra", True),
    "desconto_pacote_percentual": (
        "65", "Desconto do pacote extra sobre o valor da assinatura (%)", True
    ),
    # ----------------------------------------------- consulta de CNPJ (governo)
    "cnpj_provedor": (
        "AUTO",
        "AUTO (usa a API do governo se houver credenciais), CONECTA_GOV, BRASILAPI ou DESATIVADO",
        False,
    ),
    "cnpj_endpoint": (
        "https://apigateway.conectagov.estaleiro.serpro.gov.br",
        "Endereço base da API do governo (produção)",
        False,
    ),
    "cnpj_tipo_consulta": (
        "basica",
        "Qual API usar: basica, qsa ou empresa",
        False,
    ),
    "cnpj_consumer_key": ("", "Consumer key do Conecta Gov / SERPRO", False),
    "cnpj_consumer_secret": ("", "Consumer secret do Conecta Gov / SERPRO", False),
    "cnpj_cpf_usuario": ("", "CPF do usuário autorizado (header x-cpf-usuario)", False),
    "cnpj_incluir_socios": ("1", "Buscar também o quadro de sócios (QSA): 1 sim, 0 não", False),
    # ------------------------------------------------------ consulta de CEP
    "cep_provedor": (
        "AUTO",
        "AUTO (Correios se houver contrato), CORREIOS, VIACEP, BRASILAPI ou DESATIVADO",
        False,
    ),
    "cep_endpoint": ("https://api.correios.com.br", "Endereço base da API dos Correios", False),
    "cep_usuario": ("", "Usuário do Meu Correios (contrato)", False),
    "cep_senha": ("", "Senha / código de acesso da API dos Correios", False),
    "cep_cartao_postagem": ("", "Número do cartão de postagem usado na autenticação", False),
    "cotacoes_ativas": ("1", "Mostrar a faixa de cotações do café no rodapé: 1 sim, 0 não", True),
    "cotacoes_minutos": ("10", "De quantos em quantos minutos buscar as cotações de novo", False),
    "mercado_minutos": ("30", "Painel Mercado do Café: de quantos em quantos minutos buscar histórico e preços por cidade", False),
    "noticias_minutos": ("20", "Painel Mercado do Café: de quantos em quantos minutos buscar notícias", False),
    "mercado_agnocafe": ("1", "Mostrar as cotações por cidade da AgnoCafé no painel: 1 sim, 0 não", False),
    "aviso_pagamento": (
        "Após o pagamento o acesso é liberado assim que confirmarmos o recebimento do Pix.",
        "Aviso exibido na tela de pagamento",
        True,
    ),
}

# Os oito preços (quatro planos x dois prazos) e a grade de menus de cada plano
# entram aqui vindos de planos.py, para o catálogo ficar num lugar só.
CONFIGURACOES_PADRAO.update(catalogo.configuracoes_de_preco())
CONFIGURACOES_PADRAO.update(catalogo.configuracoes_de_modulos())


# --------------------------------------------------------------------------- #
# Configurações
# --------------------------------------------------------------------------- #
# Textos que já foram padrão em versões anteriores. Se a configuração ainda estiver
# com um deles, o sistema troca pelo texto novo — quem escreveu o próprio texto
# nunca é mexido.
TEXTOS_ANTIGOS: dict[str, tuple[str, ...]] = {
    "nome_produto": ("Sistema Financeiro",),
    "slogan": (
        "Contas a pagar e a receber, caixa, DRE e balancete — com lançamento simples "
        "para o dia a dia e lançamento múltiplo com rateio e parcelamento.",
        "Lance o contrato, cobre a corretagem dos dois lados e acompanhe cada negócio "
        "até o dinheiro entrar — com contas a pagar e a receber, caixa, DRE e "
        "balancete por trás.",
    ),
}


def garantir_configuracoes(db: Session) -> int:
    registros = {c.chave: c for c in db.query(Configuracao).all()}
    criadas = 0
    for chave, (valor, descricao, publica) in CONFIGURACOES_PADRAO.items():
        atual = registros.get(chave)
        if atual is None:
            db.add(Configuracao(chave=chave, valor=valor, descricao=descricao, publica=publica))
            criadas += 1
            continue
        if (atual.valor or "").strip() in TEXTOS_ANTIGOS.get(chave, ()):
            atual.valor = valor          # texto padrão antigo: atualiza para o novo
    # Uma vez só: o limite padrão passou de 5 para 3 usuários por empresa (set/2026).
    # Quem já tinha trocado o valor à mão (qualquer coisa diferente de 5) é respeitado.
    marca = "_limite_usuarios_3"
    if marca not in registros:
        incluidos = registros.get("usuarios_incluidos")
        if incluidos is not None and (incluidos.valor or "").strip() == "5":
            incluidos.valor = "3"
            incluidos.descricao = CONFIGURACOES_PADRAO["usuarios_incluidos"][1]
        db.add(Configuracao(chave=marca, valor="1", descricao="marca interna", publica=False))
        criadas += 1
    # Uma vez só: o preço deixou de ser "semestral e anual" e passou a ser um por
    # plano (set/2026). As duas chaves antigas saem da tela para ninguém editar um
    # valor que já não é usado por nada.
    marca_planos = "_precos_por_plano"
    if marca_planos not in registros:
        for antiga in ("plano_semestral_valor", "plano_anual_valor"):
            if antiga in registros:
                db.delete(registros[antiga])
        db.add(Configuracao(chave=marca_planos, valor="1", descricao="marca interna",
                            publica=False))
        criadas += 1
    if criadas:
        db.flush()
    return criadas


def configuracoes(db: Session, apenas_publicas: bool = False) -> dict:
    query = db.query(Configuracao)
    if apenas_publicas:
        query = query.filter(Configuracao.publica.is_(True))
    # chaves começando com "_" são marcas internas (não aparecem na tela)
    dados = {c.chave: (c.valor or "") for c in query.all() if not c.chave.startswith("_")}
    for chave, (padrao, _d, publica) in CONFIGURACOES_PADRAO.items():
        if apenas_publicas and not publica:
            continue
        dados.setdefault(chave, padrao)
    return dados


def config(db: Session, chave: str, padrao: str = "") -> str:
    registro = db.query(Configuracao).filter(Configuracao.chave == chave).first()
    if registro and registro.valor not in (None, ""):
        return registro.valor
    return CONFIGURACOES_PADRAO.get(chave, (padrao, "", False))[0] or padrao


def salvar_configuracoes(db: Session, valores: dict) -> None:
    atuais = {c.chave: c for c in db.query(Configuracao).all()}
    for chave, valor in valores.items():
        if chave not in CONFIGURACOES_PADRAO:
            continue
        texto = "" if valor is None else str(valor).strip()
        if chave in atuais:
            atuais[chave].valor = texto
        else:
            padrao, descricao, publica = CONFIGURACOES_PADRAO[chave]
            db.add(Configuracao(chave=chave, valor=texto, descricao=descricao, publica=publica))
    db.flush()


# --------------------------------------------------------------------------- #
# Planos
# --------------------------------------------------------------------------- #
def _numero(texto: str, padrao: float) -> float:
    try:
        return float(str(texto).replace(",", "."))
    except (TypeError, ValueError):
        return padrao


def _meses(db: Session) -> dict[str, int]:
    return {
        "SEMESTRAL": int(_numero(config(db, "plano_semestral_meses"), 6)),
        "ANUAL": int(_numero(config(db, "plano_anual_meses"), 12)),
    }


def _preco(db: Session, nivel: int, periodo: str, padrao: float) -> float:
    return _numero(config(db, catalogo.chave_do_valor(nivel, periodo)), padrao)


def _prazo(db: Session, nivel: int, periodo: str, padrao: float, meses: dict) -> dict:
    """Um prazo de um plano: código, valor, meses e quanto dá por mês."""
    quantos = max(meses.get(periodo.upper(), 6), 1)
    valor = _preco(db, nivel, periodo, padrao)
    return {
        "codigo": catalogo.codigo(nivel, periodo),
        "periodo": periodo.upper(),
        "rotulo": catalogo.PERIODOS[periodo.upper()],
        "valor": dinheiro(valor),
        "meses": quantos,
        "valor_mes": round(valor / quantos, 2),
    }


# --------------------------------------------------------------------------- #
# Que menus cada plano libera — e as exceções combinadas com cada cliente
# --------------------------------------------------------------------------- #
def modulos_do_nivel(db: Session, nivel: int) -> tuple[str, ...]:
    """A grade de menus do plano, como o administrador do site montou.

    Lê a configuração direto da linha (e não pelo ``config()``) de propósito:
    plano **sem nenhum menu** é uma escolha possível, e o ``config()`` trocaria
    o vazio pelo padrão de fábrica.
    """
    chave = catalogo.chave_dos_modulos(nivel)
    registro = db.query(Configuracao).filter(Configuracao.chave == chave).first()
    if registro is not None and registro.valor is not None:
        return catalogo.separar_modulos(registro.valor)
    return catalogo.modulos_do_nivel(nivel)


def modulos_da_assinatura(db: Session, assinatura: Assinatura | None) -> tuple[str, ...]:
    """O que a conta enxerga: o plano dela, mais o que foi combinado, menos o que foi tirado.

    É aqui que mora o "fechou o Plano 1 mas eu dei a nota fiscal": o módulo
    entra em ``modulos_extras`` e a conta passa a ver a tela, **sem trocar de
    plano** — o valor cobrado continua o do plano.
    """
    if assinatura is None:
        return tuple(catalogo.todos_os_modulos())
    nivel, _ = catalogo.separar(assinatura.plano)
    do_plano = list(modulos_do_nivel(db, nivel))
    for extra in catalogo.separar_modulos(assinatura.modulos_extras):
        if extra not in do_plano:
            do_plano.append(extra)
    bloqueados = catalogo.separar_modulos(assinatura.modulos_bloqueados)
    liberados = [m for m in do_plano if m not in bloqueados]
    # devolve na ordem do catálogo, para a tela não dançar
    return tuple(m for m in catalogo.MODULOS if m in liberados)


def planos_com_modulo(db: Session, modulo: str) -> list[str]:
    """Os nomes dos planos que hoje incluem esse módulo."""
    return [p["nome"] for p in catalogo.NIVEIS
            if modulo in modulos_do_nivel(db, p["nivel"])]


def frase_de_bloqueio(db: Session, modulo: str) -> str:
    """O que a tela mostra quando a conta pede uma coisa que não contratou."""
    nome = catalogo.MODULOS.get(modulo, (modulo, ""))[0]
    quais = planos_com_modulo(db, modulo)
    if not quais:
        return (f"{nome} não está disponível em nenhum plano no momento. "
                "Fale com o suporte.")
    lista = quais[0] if len(quais) == 1 else f"{', '.join(quais[:-1])} e {quais[-1]}"
    return (f"{nome} não faz parte do seu plano. Está no {lista}. "
            "Para mudar, vá em Minha Assinatura.")


def planos(db: Session) -> list[dict]:
    """Os quatro planos, cada um com os seus dois prazos e o que libera.

    É daqui que saem a página inicial, a tela de escolha do plano e a lista de
    módulos que o menu usa para esconder o que a conta não contratou.
    """
    meses = _meses(db)
    saida = []
    for plano in catalogo.NIVEIS:
        nivel = plano["nivel"]
        modulos = modulos_do_nivel(db, nivel)
        semestral = _prazo(db, nivel, "SEMESTRAL", plano["semestral"], meses)
        anual = _prazo(db, nivel, "ANUAL", plano["anual"], meses)
        economia = round(
            semestral["valor"] * (anual["meses"] / max(semestral["meses"], 1))
            - anual["valor"], 2)
        saida.append({
            "nivel": nivel,
            "nome": plano["nome"],
            "para": plano["para"],
            "modulos": [{"codigo": m, "nome": catalogo.MODULOS[m][0],
                         "texto": catalogo.MODULOS[m][1]} for m in modulos],
            "extras": [m for m in modulos if m not in catalogo.BASE],
            "prazos": [semestral, anual],
            "semestral": semestral,
            "anual": anual,
            "economia": max(economia, 0),
            # o plano completo é o destacado na página inicial
            "destaque": nivel == 4,
        })
    return saida


def plano_por_codigo(db: Session, codigo: str) -> dict:
    """O plano de um código como ``P3_ANUAL`` — ou dos códigos antigos.

    Devolve tudo achatado (nível, período, valor, meses, módulos), que é o que
    quem grava a assinatura precisa.
    """
    nivel, periodo = catalogo.separar(codigo)
    lista = planos(db)
    # separar() sempre devolve um nível que existe; o primeiro é só a rede
    plano = next((p for p in lista if p["nivel"] == nivel), lista[0])
    prazo = plano["anual"] if periodo == "ANUAL" else plano["semestral"]
    return {
        **prazo,
        "nivel": plano["nivel"],
        "nome": plano["nome"],
        "nome_completo": f'{plano["nome"]} {prazo["rotulo"].lower()}',
        "modulos": [m["codigo"] for m in plano["modulos"]],
        "descricao": (f'{plano["nome"]}: acesso por {prazo["meses"]} meses, '
                      "pagamento único via Pix."),
    }


def horas_teste(db: Session) -> int:
    return int(_numero(config(db, "horas_teste"), 48))


# --------------------------------------------------------------------------- #
# Usuários inclusos e pacotes extras
# --------------------------------------------------------------------------- #
def usuarios_incluidos(db: Session) -> int:
    return int(_numero(config(db, "usuarios_incluidos"), 5))


def usuarios_por_pacote(db: Session) -> int:
    return max(1, int(_numero(config(db, "usuarios_por_pacote"), 5)))


def desconto_pacote(db: Session) -> float:
    return _numero(config(db, "desconto_pacote_percentual"), 65)


def valor_pacote(db: Session, assinatura: Assinatura | None) -> float:
    """Pacote extra custa o valor do plano menos o desconto configurado."""
    plano = plano_por_codigo(db, assinatura.plano if assinatura else "SEMESTRAL")
    return dinheiro(plano["valor"] * (1 - desconto_pacote(db) / 100))


def limite_usuarios(db: Session, assinatura: Assinatura | None) -> int:
    """Quantos usuários a conta pode ter.

    Se o administrador do site definiu um número para a empresa, vale esse número;
    senão, usuários inclusos no plano + pacotes confirmados.
    """
    if assinatura is None:
        return 0  # conta interna: sem limite (tratado por quem chama)
    if assinatura.limite_usuarios:
        return int(assinatura.limite_usuarios)
    return usuarios_incluidos(db) + (assinatura.pacotes_usuarios or 0) * usuarios_por_pacote(db)


def resumo_usuarios(db: Session, assinatura: Assinatura | None, usados: int) -> dict:
    """Bloco mostrado na tela da assinatura."""
    if assinatura is None:
        return {"ilimitado": True, "usados": usados}
    incluidos = usuarios_incluidos(db)
    por_pacote = usuarios_por_pacote(db)
    limite = limite_usuarios(db, assinatura)
    unitario = valor_pacote(db, assinatura)
    return {
        "ilimitado": False,
        "usados": usados,
        "limite": limite,
        "disponiveis": max(limite - usados, 0),
        "incluidos": incluidos,
        "por_pacote": por_pacote,
        "pacotes": assinatura.pacotes_usuarios or 0,
        "pacotes_solicitados": assinatura.pacotes_solicitados or 0,
        "desconto_percentual": desconto_pacote(db),
        "valor_pacote": unitario,
        "valor_por_usuario": dinheiro(unitario / por_pacote),
        "plano_valor": dinheiro(assinatura.valor),
    }


# --------------------------------------------------------------------------- #
# Administrador do site (MASTER) e acesso por data dos usuários
# --------------------------------------------------------------------------- #
def email_master() -> str:
    """E-mail que é sempre o administrador do site (variável FIN_MASTER_EMAIL)."""
    import os

    return (os.getenv("FIN_MASTER_EMAIL") or "galbatheo@gmail.com").strip().lower()


def garantir_master(db: Session, usuario=None) -> bool:
    """Deixa o usuário do e-mail do dono como MASTER. Devolve True se mudou algo.

    Quando o dono passa a ser o administrador, o login de fábrica
    admin@financeiro.local — cuja senha admin123 está no manual — é desligado se
    ainda estiver com a senha de fábrica.
    """
    from .models import Usuario
    from .security import verificar_senha

    email = email_master()
    if usuario is None:
        usuario = db.query(Usuario).filter(Usuario.email == email).first()
    if usuario is None or (usuario.email or "").lower() != email:
        return False
    mudou = False
    if usuario.perfil != "MASTER" or not usuario.ativo or usuario.acesso_ate \
            or usuario.bloqueado_admin:
        usuario.perfil = "MASTER"
        usuario.ativo = True
        usuario.acesso_ate = None
        usuario.bloqueado_admin = False
        mudou = True
    fabrica = db.query(Usuario).filter(Usuario.email == "admin@financeiro.local").first()
    if fabrica and fabrica.id != usuario.id and fabrica.ativo \
            and verificar_senha("admin123", fabrica.senha_hash):
        fabrica.ativo = False
        mudou = True
    if mudou:
        db.flush()
    return mudou


def acesso_do_usuario_vencido(usuario) -> str | None:
    """Mensagem de bloqueio se a data de acesso do usuário já passou."""
    if usuario.perfil == "MASTER" or not usuario.acesso_ate:
        return None
    if usuario.acesso_ate < date.today():
        return (f"Seu acesso terminou em {usuario.acesso_ate.strftime('%d/%m/%Y')}. "
                "Fale com o administrador para liberar.")
    return None


# --------------------------------------------------------------------------- #
# Ciclo de vida da assinatura
# --------------------------------------------------------------------------- #
def criar_assinatura(db: Session, usuario_id: int, empresa_id: int, codigo_plano: str) -> Assinatura:
    plano = plano_por_codigo(db, codigo_plano)
    agora = datetime.utcnow()
    assinatura = Assinatura(
        usuario_id=usuario_id,
        empresa_id=empresa_id,
        plano=plano["codigo"],
        valor=plano["valor"],
        status="TESTE",
        teste_inicio=agora,
        teste_fim=agora + timedelta(hours=horas_teste(db)),
        pix_identificador=f"FIN{usuario_id:05d}",
    )
    db.add(assinatura)
    db.flush()
    return assinatura


def situacao(db: Session, assinatura: Assinatura | None) -> dict:
    """Diz se a conta pode usar o sistema e por quê."""
    if assinatura is None:
        # conta interna (MASTER): usa tudo
        return {"liberado": True, "status": "INTERNA", "motivo": "", "titulo": "Conta interna",
                "modulos": catalogo.todos_os_modulos(),
                "rotas": catalogo.rotas_dos_modulos(catalogo.todos_os_modulos())}

    agora = datetime.utcnow()
    hoje = date.today()
    escolhido = plano_por_codigo(db, assinatura.plano)
    modulos = modulos_da_assinatura(db, assinatura)
    dados = {
        "assinatura_id": assinatura.id,
        "plano": assinatura.plano,
        "plano_nome": escolhido["nome"],
        "plano_nivel": escolhido["nivel"],
        "plano_periodo": escolhido["periodo"],
        "plano_rotulo": escolhido["nome_completo"],
        # é daqui que o menu sabe o que mostrar — já com as exceções da conta
        "modulos": list(modulos),
        "rotas": catalogo.rotas_dos_modulos(modulos),
        "modulos_do_plano": escolhido["modulos"],
        "modulos_extras": list(catalogo.separar_modulos(assinatura.modulos_extras)),
        "modulos_bloqueados": list(catalogo.separar_modulos(assinatura.modulos_bloqueados)),
        "valor": dinheiro(assinatura.valor),
        "status": assinatura.status,
        "teste_fim": assinatura.teste_fim.isoformat(timespec="seconds") if assinatura.teste_fim else None,
        "data_fim": assinatura.data_fim.isoformat() if assinatura.data_fim else None,
        "pagamento_informado_em": (
            assinatura.pagamento_informado_em.isoformat(timespec="seconds")
            if assinatura.pagamento_informado_em
            else None
        ),
    }

    if assinatura.status == "ATIVA":
        if assinatura.data_fim and assinatura.data_fim < hoje:
            dados.update(
                liberado=False, motivo="ASSINATURA_VENCIDA", titulo="Assinatura vencida",
                mensagem="Sua assinatura venceu. Renove pelo Pix para voltar a usar o sistema.",
            )
        else:
            restantes = (assinatura.data_fim - hoje).days if assinatura.data_fim else None
            dados.update(
                liberado=True, motivo="", titulo="Assinatura ativa",
                dias_restantes=restantes,
                mensagem=f"Assinatura ativa até {assinatura.data_fim.strftime('%d/%m/%Y')}."
                if assinatura.data_fim else "Assinatura ativa.",
            )
        return dados

    if assinatura.status in ("TESTE", "AGUARDANDO"):
        em_teste = assinatura.teste_fim and agora < assinatura.teste_fim
        if em_teste:
            faltam = assinatura.teste_fim - agora
            horas = int(faltam.total_seconds() // 3600)
            minutos = int((faltam.total_seconds() % 3600) // 60)
            dados.update(
                liberado=True, motivo="EM_TESTE", titulo="Período de teste",
                horas_restantes=horas, minutos_restantes=minutos,
                mensagem=(
                    f"Teste liberado por mais {horas}h{minutos:02d}min. "
                    + (
                        "Recebemos o aviso do seu Pix — assim que confirmarmos o recebimento a conta é liberada."
                        if assinatura.status == "AGUARDANDO"
                        else "Faça o Pix do plano escolhido para continuar usando depois desse prazo."
                    )
                ),
            )
        elif assinatura.status == "AGUARDANDO":
            dados.update(
                liberado=False, motivo="AGUARDANDO_CONFIRMACAO",
                titulo="Aguardando confirmação do pagamento",
                mensagem="Seu pagamento foi informado e está em conferência. "
                         "A liberação acontece assim que o Pix for confirmado.",
            )
        else:
            dados.update(
                liberado=False, motivo="TESTE_EXPIRADO", titulo="Período de teste encerrado",
                mensagem="As 48 horas de teste terminaram. Faça o Pix do plano escolhido "
                         "para liberar o acesso completo.",
            )
        return dados

    if assinatura.status == "BLOQUEADA":
        dados.update(
            liberado=False, motivo="BLOQUEADA", titulo="Acesso bloqueado",
            mensagem="O acesso desta empresa está bloqueado. Fale com o suporte para liberar.",
        )
        return dados

    if assinatura.status == "CANCELADA":
        dados.update(
            liberado=False, motivo="CANCELADA", titulo="Assinatura cancelada",
            mensagem="Esta assinatura foi cancelada. Fale com o suporte para reativar.",
        )
        return dados

    dados.update(
        liberado=False, motivo="EXPIRADA", titulo="Assinatura expirada",
        mensagem="Renove sua assinatura pelo Pix para voltar a usar o sistema.",
    )
    return dados


def confirmar_pagamento(
    db: Session, assinatura: Assinatura, confirmado_por_id: int, meses: int | None = None
) -> Assinatura:
    plano = plano_por_codigo(db, assinatura.plano)
    duracao = meses or plano["meses"]
    hoje = date.today()
    # renovação: soma a partir do vencimento atual, se ainda estiver em dia
    inicio = hoje
    if assinatura.status == "ATIVA" and assinatura.data_fim and assinatura.data_fim >= hoje:
        inicio = assinatura.data_fim
    assinatura.status = "ATIVA"
    assinatura.data_inicio = assinatura.data_inicio or hoje
    assinatura.data_fim = adicionar_meses(inicio, duracao)
    assinatura.confirmado_em = datetime.utcnow()
    assinatura.confirmado_por_id = confirmado_por_id
    # o cupom vale na primeira cobrança: é aqui que ele é gasto e sai da conta,
    # para a renovação voltar ao preço cheio
    descontos.consumir(db, assinatura, plano["valor"])
    db.flush()
    return assinatura


# --------------------------------------------------------------------------- #
# Pix — payload "copia e cola" (padrão EMV do Banco Central) e QR Code
# --------------------------------------------------------------------------- #
def _campo(identificador: str, valor: str) -> str:
    return f"{identificador}{len(valor):02d}{valor}"


def _texto_simples(texto: str, limite: int) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ASCII", "ignore").decode()
    limpo = re.sub(r"[^A-Za-z0-9 ]", "", sem_acento).strip().upper()
    return limpo[:limite] or "NAO INFORMADO"[:limite]


def _crc16(payload: str) -> str:
    crc = 0xFFFF
    for byte in payload.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def pix_copia_e_cola(
    chave: str, nome: str, cidade: str, valor: float, identificador: str = "***"
) -> str:
    """Monta o código Pix copia e cola a partir da chave configurada."""
    if not chave:
        return ""
    conta = _campo("00", "BR.GOV.BCB.PIX") + _campo("01", chave.strip())
    payload = (
        _campo("00", "01")
        + _campo("26", conta)
        + _campo("52", "0000")
        + _campo("53", "986")
        + (_campo("54", f"{float(valor):.2f}") if valor else "")
        + _campo("58", "BR")
        + _campo("59", _texto_simples(nome, 25))
        + _campo("60", _texto_simples(cidade, 15))
        + _campo("62", _campo("05", _texto_simples(identificador, 25) if identificador else "***"))
        + "6304"
    )
    return payload + _crc16(payload)


def pix_qrcode_svg(payload: str) -> str:
    """Devolve o QR Code em SVG (string). Vazio se a biblioteca não estiver instalada."""
    if not payload:
        return ""
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:  # pragma: no cover
        return ""
    imagem = qrcode.make(
        payload, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2
    )
    import io

    buffer = io.BytesIO()
    imagem.save(buffer)
    svg = buffer.getvalue().decode("utf-8")
    # remove a declaração XML: o SVG é inserido direto no HTML da página
    return re.sub(r"^<\?xml[^>]*\?>\s*", "", svg)


def dados_pagamento(db: Session, assinatura: Assinatura, valor: float | None = None) -> dict:
    """Dados do Pix. `valor` permite cobrar algo diferente do plano (pacotes extras).

    O cupom de desconto entra **só na cobrança do plano**: quando vem um `valor`
    por fora, é pacote de usuários, e pacote não tem desconto. Como o copia e
    cola e o QR Code são montados com `cobranca`, o desconto já sai nos dois.
    """
    plano = plano_por_codigo(db, assinatura.plano)
    if valor:
        cobranca = dinheiro(valor)
        cupom = descontos.desconto_da_assinatura(None, cobranca)
    else:
        cupom = descontos.desconto_da_assinatura(assinatura, plano["valor"])
        cobranca = cupom["valor_pagar"]
    chave = config(db, "pix_chave")
    titular = config(db, "pix_titular") or config(db, "empresa_titular")
    cidade = config(db, "pix_cidade")
    payload = pix_copia_e_cola(
        chave, titular, cidade, cobranca, assinatura.pix_identificador or "***"
    )
    return {
        "plano": plano,
        "valor_cobranca": cobranca,
        "valor_cheio": cupom["valor_cheio"],
        "cupom": cupom["codigo"],
        "cupom_percentual": cupom["percentual"],
        "cupom_desconto": cupom["desconto"],
        "pix_chave": chave,
        "pix_titular": titular,
        "pix_banco": config(db, "pix_banco"),
        "identificador": assinatura.pix_identificador,
        "copia_e_cola": payload,
        "qrcode_svg": pix_qrcode_svg(payload),
        "aviso": config(db, "aviso_pagamento"),
        "contato_whatsapp": config(db, "contato_whatsapp"),
        "contato_email": config(db, "contato_email"),
        "configurado": bool(chave),
    }
