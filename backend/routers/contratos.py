"""Contratos de intermediação (corretagem).

Registra o negócio entre comprador e vendedor — quantidade, preço, valor — e a
corretagem cobrada de cada lado. A partir do contrato o sistema gera as contas
a receber das comissões, já classificadas e contabilizadas.
"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from .. import contabil
from ..database import get_db
from ..deps import acesso_liberado, validar_empresa
from ..models import (
    Contrato,
    ContaContabil,
    Lancamento,
    LancamentoItem,
    ModalidadeContrato,
    Parcela,
    Parceiro,
    Produto,
    Unidade,
    Usuario,
)
from ..plano_contas import parametro_conta
from .cadastros import resumo_forma
from ..schemas import ContratoIn, GerarRecebiveisIn
from ..utils import (
    adicionar_meses,
    dinheiro,
    endereco_linha,
    parse_data,
    serializar,
)

router = APIRouter(prefix="/api/contratos", tags=["contratos"])

CODIGO_CONTA_COMISSAO = "3.1.01.004"


def proximo_numero(db: Session, empresa_id: int) -> str:
    """Próximo número livre da empresa, no formato 00000001."""
    numeros = [
        c.numero for c in db.query(Contrato.numero).filter(Contrato.empresa_id == empresa_id).all()
    ]
    maior = 0
    for numero in numeros:
        texto = "".join(ch for ch in str(numero) if ch.isdigit())
        if texto:
            maior = max(maior, int(texto))
    return f"{maior + 1:08d}"


def aplicar_cadastros(db: Session, contrato: Contrato, dados: ContratoIn):
    """Copia nome/unidade dos cadastros escolhidos e calcula o peso total."""
    if dados.produto_id:
        produto = db.get(Produto, dados.produto_id)
        if not produto or produto.empresa_id != contrato.empresa_id:
            raise HTTPException(400, "Produto inválido")
        contrato.produto = produto.nome
        if produto.embalagem and not dados.embalagem:
            contrato.embalagem = produto.embalagem
        if produto.unidade_id and not dados.unidade_id:
            contrato.unidade_id = produto.unidade_id
    if dados.modalidade_id:
        modalidade = db.get(ModalidadeContrato, dados.modalidade_id)
        if not modalidade or modalidade.empresa_id != contrato.empresa_id:
            raise HTTPException(400, "Modalidade inválida")
        contrato.modalidade = modalidade.nome
    if contrato.unidade_id:
        unidade = db.get(Unidade, contrato.unidade_id)
        if not unidade or unidade.empresa_id != contrato.empresa_id:
            raise HTTPException(400, "Unidade inválida")
        contrato.unidade = unidade.codigo
        contrato.peso_total = round(
            float(contrato.quantidade or 0) * float(unidade.peso_conversao or 0), 3
        )
    else:
        contrato.peso_total = 0
    if dados.representante_id:
        representante = db.get(Usuario, dados.representante_id)
        if not representante:
            raise HTTPException(400, "Representante inválido")


# --------------------------------------------------------------------------- #
# Cálculos
# --------------------------------------------------------------------------- #
def calcular(dados: ContratoIn) -> dict:
    """Valor negociado e comissões. O percentual manda; o valor pode ser digitado."""
    quantidade = float(dados.quantidade or 0)
    preco = float(dados.preco_unitario or 0)
    diferencial = float(dados.diferencial or 0)
    total = dados.valor_total
    if total in (None, 0):
        total = quantidade * (preco + diferencial)
    total = dinheiro(total)

    def comissao(percentual, valor):
        if valor not in (None, ""):
            return dinheiro(valor)
        return dinheiro(total * float(percentual or 0) / 100)

    return {
        "valor_total": total,
        "comissao_comprador_valor": comissao(
            dados.comissao_comprador_percentual, dados.comissao_comprador_valor
        ),
        "comissao_vendedor_valor": comissao(
            dados.comissao_vendedor_percentual, dados.comissao_vendedor_valor
        ),
    }


def conta_comissao(db: Session, empresa_id: int) -> int:
    """Conta de receita usada nas comissões; cria a padrão se ainda não existir."""
    conta_id = parametro_conta(db, empresa_id, "conta_comissao")
    if conta_id and db.get(ContaContabil, conta_id):
        return conta_id

    conta = (
        db.query(ContaContabil)
        .filter(
            ContaContabil.empresa_id == empresa_id,
            ContaContabil.codigo == CODIGO_CONTA_COMISSAO,
        )
        .first()
    )
    if not conta:
        pai = (
            db.query(ContaContabil)
            .filter(ContaContabil.empresa_id == empresa_id, ContaContabil.codigo == "3.1")
            .first()
        )
        conta = ContaContabil(
            empresa_id=empresa_id,
            codigo=CODIGO_CONTA_COMISSAO,
            nome="Receita de Corretagem e Comissoes",
            tipo="RECEITA",
            natureza="C",
            analitica=True,
            nivel=4,
            pai_id=pai.id if pai else None,
            grupo_dre="RECEITA_BRUTA",
        )
        db.add(conta)
        db.flush()

    from ..models import Parametro

    registro = (
        db.query(Parametro)
        .filter(Parametro.empresa_id == empresa_id, Parametro.chave == "conta_comissao")
        .first()
    )
    if registro:
        registro.valor = str(conta.id)
    else:
        db.add(Parametro(empresa_id=empresa_id, chave="conta_comissao", valor=str(conta.id)))
    db.flush()
    return conta.id


# --------------------------------------------------------------------------- #
# Situação do contrato
#
# O status acompanha o dinheiro: assim que as comissões viram contas a receber o
# contrato está "Fechado a Receber", e conforme as baixas entram ele caminha para
# "Recebido Parcial" e "Recebido Total". Só o cancelamento é manual.
# --------------------------------------------------------------------------- #
STATUS_CONTRATO = {
    "ABERTO": "Aberto",
    "FECHADO_A_RECEBER": "Fechado a Receber",
    "RECEBIDO_PARCIAL": "Fechado Recebido Parcial",
    "RECEBIDO_TOTAL": "Fechado Recebido Total",
    "CANCELADO": "Cancelado",
}

# como cada status aparece na tela (classe da tag colorida)
TAG_STATUS = {
    "ABERTO": "tag-aberto",
    "FECHADO_A_RECEBER": "tag-a-receber",
    "RECEBIDO_PARCIAL": "tag-parcial",
    "RECEBIDO_TOTAL": "tag-pago",
    "CANCELADO": "tag-cancelado",
}


def _lancamentos_do_contrato(db: Session, c: Contrato) -> list[Lancamento]:
    ids = [i for i in (c.lancamento_comprador_id, c.lancamento_vendedor_id) if i]
    return [lanc for lanc in (db.get(Lancamento, i) for i in ids) if lanc]


def situacao_financeira(db: Session, c: Contrato) -> dict:
    """Quanto do contrato virou título, quanto já entrou e quanto falta receber."""
    hoje = date.today()
    gerado = baixado = vencido = 0.0
    parcelas = pagas = 0
    vencimentos: list[date] = []
    atrasos: list[date] = []

    for lanc in _lancamentos_do_contrato(db, c):
        gerado += dinheiro(lanc.valor_total)
        for p in lanc.parcelas:
            parcelas += 1
            pago = dinheiro(p.valor_baixado)
            baixado += pago
            if p.status == "PAGO":
                pagas += 1
            else:
                saldo_parcela = round(dinheiro(p.valor) - pago, 2)
                vencimentos.append(p.data_vencimento)
                if p.data_vencimento < hoje and saldo_parcela > 0:
                    vencido += saldo_parcela
                    atrasos.append(p.data_vencimento)

    gerado = round(gerado, 2)
    baixado = round(baixado, 2)
    comissao = round(
        dinheiro(c.comissao_comprador_valor) + dinheiro(c.comissao_vendedor_valor), 2
    )
    return {
        "gerado": gerado,
        "a_gerar": round(max(comissao - gerado, 0), 2),
        "recebido": baixado,
        "saldo": round(gerado - baixado, 2),
        "vencido": round(vencido, 2),
        "parcelas": parcelas,
        "parcelas_pagas": pagas,
        "proximo_vencimento": min(vencimentos).isoformat() if vencimentos else None,
        "dias_atraso": (hoje - min(atrasos)).days if atrasos else 0,
        "recebido_percentual": round(baixado / gerado * 100, 2) if gerado else 0.0,
    }


def calcular_status(c: Contrato, financeiro: dict) -> str:
    """Status derivado do que já foi gerado e recebido. Cancelado não se mexe."""
    if c.status == "CANCELADO":
        return "CANCELADO"
    if not financeiro["gerado"]:
        return "ABERTO"
    if financeiro["recebido"] <= 0:
        return "FECHADO_A_RECEBER"
    if financeiro["saldo"] > 0.009:
        return "RECEBIDO_PARCIAL"
    return "RECEBIDO_TOTAL"


def sincronizar_status(db: Session, c: Contrato, financeiro: dict | None = None) -> dict:
    """Recalcula e grava o status. Também converte o antigo FATURADO."""
    financeiro = financeiro or situacao_financeira(db, c)
    novo = calcular_status(c, financeiro)
    if c.status != novo:
        c.status = novo
    return financeiro


def _saldo_lancamento(db: Session, lancamento_id: int | None) -> dict | None:
    if not lancamento_id:
        return None
    lanc = db.get(Lancamento, lancamento_id)
    if not lanc:
        return None
    baixado = sum(float(p.valor_baixado or 0) for p in lanc.parcelas)
    return {
        "id": lanc.id,
        "descricao": lanc.descricao,
        "valor": dinheiro(lanc.valor_total),
        "baixado": dinheiro(baixado),
        "saldo": round(dinheiro(lanc.valor_total) - baixado, 2),
        "status": lanc.status,
        "qtd_parcelas": len(lanc.parcelas),
        "proximo_vencimento": min(
            (p.data_vencimento.isoformat() for p in lanc.parcelas
             if p.status in ("ABERTO", "PARCIAL")),
            default=None,
        ),
    }


def contrato_dict(db: Session, c: Contrato, completo: bool = False) -> dict:
    total_comissao = round(
        dinheiro(c.comissao_comprador_valor) + dinheiro(c.comissao_vendedor_valor), 2
    )
    financeiro = sincronizar_status(db, c)   # o status acompanha as baixas
    dados = serializar(
        c,
        extras={
            "comprador_nome": c.comprador.nome if c.comprador else "-",
            "comprador_documento": c.comprador.cpf_cnpj if c.comprador else "",
            "vendedor_nome": c.vendedor.nome if c.vendedor else "-",
            "vendedor_documento": c.vendedor.cpf_cnpj if c.vendedor else "",
            "conta_contabil_nome": (
                f"{c.conta_contabil.codigo} - {c.conta_contabil.nome}" if c.conta_contabil else None
            ),
            "representante_nome": c.representante.nome if c.representante else None,
            "produto_nome": c.produto_ref.nome if c.produto_ref else c.produto,
            "modalidade_nome": c.modalidade_ref.nome if c.modalidade_ref else c.modalidade,
            "unidade_nome": (
                f"{c.unidade_ref.codigo} - {c.unidade_ref.nome}" if c.unidade_ref else c.unidade
            ),
            "centro_custo_nome": c.centro_custo.nome if c.centro_custo else None,
            "operacao_nome": c.operacao.nome if c.operacao else None,
            "comissao_total": total_comissao,
            "percentual_total": round(
                (total_comissao / dinheiro(c.valor_total) * 100) if c.valor_total else 0, 4
            ),
            "status_nome": STATUS_CONTRATO.get(c.status, c.status),
            "status_tag": TAG_STATUS.get(c.status, ""),
            "financeiro": financeiro,
            # atalhos usados na lista e no relatório
            "comissao_recebida": financeiro["recebido"],
            "comissao_a_receber": round(financeiro["saldo"] + financeiro["a_gerar"], 2),
            "comissao_vencida": financeiro["vencido"],
        },
    )
    if completo:
        dados["recebivel_comprador"] = _saldo_lancamento(db, c.lancamento_comprador_id)
        dados["recebivel_vendedor"] = _saldo_lancamento(db, c.lancamento_vendedor_id)
    return dados


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
def _validar_partes(db: Session, dados: ContratoIn, usuario: Usuario):
    validar_empresa(db, dados.empresa_id, usuario)
    if dados.comprador_id == dados.vendedor_id:
        raise HTTPException(400, "O comprador e o vendedor devem ser cadastros diferentes.")
    for campo, parceiro_id in (("comprador", dados.comprador_id), ("vendedor", dados.vendedor_id)):
        parceiro = db.get(Parceiro, parceiro_id)
        if not parceiro or parceiro.empresa_id != dados.empresa_id:
            raise HTTPException(400, f"Selecione um {campo} válido.")


@router.post("")
def criar_contrato(
    dados: ContratoIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    _validar_partes(db, dados, usuario)
    numero = (dados.numero or "").strip() or proximo_numero(db, dados.empresa_id)
    if (
        db.query(Contrato)
        .filter(Contrato.empresa_id == dados.empresa_id, Contrato.numero == numero)
        .first()
    ):
        raise HTTPException(400, f"Já existe um contrato com o número {numero}.")

    calculado = calcular(dados)
    if calculado["valor_total"] <= 0:
        raise HTTPException(400, "Informe a quantidade e o preço, ou o valor total do contrato.")

    contrato = Contrato(usuario_id=usuario.id)
    for campo, valor in dados.model_dump().items():
        if hasattr(contrato, campo):
            setattr(contrato, campo, valor)
    contrato.numero = numero
    contrato.data = dados.data or date.today()
    for campo, valor in calculado.items():
        setattr(contrato, campo, valor)
    if not contrato.conta_contabil_id:
        contrato.conta_contabil_id = conta_comissao(db, dados.empresa_id)
    aplicar_cadastros(db, contrato, dados)
    db.add(contrato)
    db.commit()
    db.refresh(contrato)
    return contrato_dict(db, contrato, completo=True)


@router.get("")
def listar_contratos(
    empresa_id: int,
    status: str | None = None,
    parceiro_id: int | None = None,
    de: str | None = None,
    ate: str | None = None,
    q: str | None = None,
    limite: int = 500,
    db: Session = Depends(get_db),
    _: Usuario = Depends(acesso_liberado),
):
    query = (
        db.query(Contrato)
        .options(joinedload(Contrato.comprador), joinedload(Contrato.vendedor))
        .filter(Contrato.empresa_id == empresa_id)
    )
    if parceiro_id:
        query = query.filter(
            or_(Contrato.comprador_id == parceiro_id, Contrato.vendedor_id == parceiro_id)
        )
    if de:
        query = query.filter(Contrato.data >= parse_data(de))
    if ate:
        query = query.filter(Contrato.data <= parse_data(ate))
    if q:
        termo = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Contrato.numero.ilike(termo),
                Contrato.numero_compra.ilike(termo),
                Contrato.numero_venda.ilike(termo),
                Contrato.produto.ilike(termo),
            )
        )
    contratos = query.order_by(Contrato.data.desc(), Contrato.id.desc()).limit(limite).all()
    linhas = [contrato_dict(db, c) for c in contratos]
    db.commit()   # grava os status recalculados

    # o filtro de status é aplicado depois do recálculo, senão um contrato que
    # mudou de situação sairia na consulta errada
    if status:
        linhas = [l for l in linhas if l["status"] == status]

    def soma(campo):
        return round(sum(l[campo] for l in linhas), 2)

    return {
        "linhas": linhas,
        "totais": {
            "quantidade": len(linhas),
            "valor_negociado": soma("valor_total"),
            "comissao_comprador": soma("comissao_comprador_valor"),
            "comissao_vendedor": soma("comissao_vendedor_valor"),
            "comissao_total": soma("comissao_total"),
            "comissao_recebida": soma("comissao_recebida"),
            "comissao_a_receber": soma("comissao_a_receber"),
            "comissao_vencida": soma("comissao_vencida"),
            "por_status": {
                codigo: sum(1 for l in linhas if l["status"] == codigo)
                for codigo in STATUS_CONTRATO
            },
        },
        "status": [{"codigo": c, "nome": n} for c, n in STATUS_CONTRATO.items()],
    }


@router.get("/proximo-numero")
def obter_proximo_numero(
    empresa_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)
):
    """Número sugerido para o próximo contrato da empresa."""
    validar_empresa(db, empresa_id, usuario)
    return {"numero": proximo_numero(db, empresa_id)}


@router.get("/{contrato_id}")
def obter_contrato(
    contrato_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)
):
    contrato = db.get(Contrato, contrato_id)
    if not contrato:
        raise HTTPException(404, "Contrato não encontrado")
    validar_empresa(db, contrato.empresa_id, usuario)
    return contrato_dict(db, contrato, completo=True)


@router.get("/{contrato_id}/impressao")
def dados_impressao(
    contrato_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)
):
    """Tudo o que a folha impressa do contrato precisa, num pacote só."""
    contrato = db.get(Contrato, contrato_id)
    if not contrato:
        raise HTTPException(404, "Contrato não encontrado")
    empresa = validar_empresa(db, contrato.empresa_id, usuario)

    def parte(parceiro: Parceiro | None) -> dict:
        if not parceiro:
            return {"nome": "-", "formas": []}
        return dict(
            serializar(parceiro, exclude={"observacao"}),
            endereco=endereco_linha(parceiro),
            formas=[
                {"apelido": f.apelido, "tipo": f.tipo, "resumo": resumo_forma(f),
                 "principal": bool(f.principal)}
                for f in parceiro.formas_pagamento if f.ativo
            ],
        )

    unidade = db.get(Unidade, contrato.unidade_id) if contrato.unidade_id else None
    return {
        "contrato": contrato_dict(db, contrato, completo=True),
        "empresa": dict(
            serializar(empresa),
            endereco=endereco_linha(empresa),
        ),
        "comprador": parte(contrato.comprador),
        "vendedor": parte(contrato.vendedor),
        "unidade": serializar(unidade) if unidade else None,
        "emitido_em": datetime.now().isoformat(timespec="minutes"),
    }


@router.put("/{contrato_id}")
def atualizar_contrato(
    contrato_id: int,
    dados: ContratoIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    contrato = db.get(Contrato, contrato_id)
    if not contrato:
        raise HTTPException(404, "Contrato não encontrado")
    validar_empresa(db, contrato.empresa_id, usuario)
    if contrato.lancamento_comprador_id or contrato.lancamento_vendedor_id:
        raise HTTPException(
            400,
            "Este contrato já gerou contas a receber. Estorne os recebíveis antes de alterá-lo.",
        )
    _validar_partes(db, dados, usuario)
    calculado = calcular(dados)
    for campo, valor in dados.model_dump().items():
        if hasattr(contrato, campo) and campo not in ("empresa_id",):
            setattr(contrato, campo, valor)
    for campo, valor in calculado.items():
        setattr(contrato, campo, valor)
    if not contrato.conta_contabil_id:
        contrato.conta_contabil_id = conta_comissao(db, contrato.empresa_id)
    aplicar_cadastros(db, contrato, dados)
    db.commit()
    return contrato_dict(db, contrato, completo=True)


@router.delete("/{contrato_id}")
def excluir_contrato(
    contrato_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)
):
    contrato = db.get(Contrato, contrato_id)
    if not contrato:
        raise HTTPException(404, "Contrato não encontrado")
    validar_empresa(db, contrato.empresa_id, usuario)
    if contrato.lancamento_comprador_id or contrato.lancamento_vendedor_id:
        raise HTTPException(
            400, "Estorne as contas a receber geradas antes de excluir o contrato."
        )
    db.delete(contrato)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Geração das contas a receber
# --------------------------------------------------------------------------- #
def _criar_recebivel(
    db: Session,
    contrato: Contrato,
    parceiro_id: int,
    valor: float,
    lado: str,
    opcoes: GerarRecebiveisIn,
    usuario: Usuario,
) -> Lancamento:
    base = opcoes.vencimento or contrato.data_pagamento or contrato.data or date.today()
    qtd = max(1, int(opcoes.num_parcelas or 1))

    lanc = Lancamento(
        empresa_id=contrato.empresa_id,
        tipo="RECEBER",
        modo="MULTIPLO" if qtd > 1 else "SIMPLES",
        numero_documento=contrato.numero,
        parceiro_id=parceiro_id,
        descricao=f"Corretagem {lado} - contrato {contrato.numero}",
        data_emissao=contrato.data or date.today(),
        data_competencia=contrato.data or date.today(),
        valor_total=valor,
        operacao_id=contrato.operacao_id,
        observacao=(
            f"{contrato.produto or ''} · {contrato.quantidade:,.2f} {contrato.unidade or ''} · "
            f"valor negociado {contrato.valor_total:,.2f}"
        ).strip(" ·"),
        usuario_id=usuario.id,
    )
    db.add(lanc)
    db.flush()

    db.add(
        LancamentoItem(
            lancamento_id=lanc.id,
            conta_contabil_id=contrato.conta_contabil_id or conta_comissao(db, contrato.empresa_id),
            centro_custo_id=contrato.centro_custo_id,
            operacao_id=contrato.operacao_id,
            descricao=f"Corretagem {lado} - contrato {contrato.numero}",
            valor=valor,
        )
    )

    valor_parcela = round(valor / qtd, 2)
    acumulado = 0.0
    for i in range(qtd):
        if opcoes.periodicidade == "DIAS":
            vencimento = base + timedelta(days=int(opcoes.intervalo_dias or 30) * i)
        else:
            vencimento = adicionar_meses(base, i)
        parcela = valor_parcela if i < qtd - 1 else round(valor - acumulado, 2)
        acumulado += parcela
        db.add(
            Parcela(
                lancamento_id=lanc.id,
                numero=i + 1,
                data_vencimento=vencimento,
                valor=parcela,
            )
        )
    db.flush()
    db.refresh(lanc)
    contabil.contabilizar_lancamento(db, lanc)
    return lanc


@router.post("/{contrato_id}/gerar-recebiveis")
def gerar_recebiveis(
    contrato_id: int,
    opcoes: GerarRecebiveisIn | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    """Cria as contas a receber das comissões do comprador e do vendedor."""
    contrato = db.get(Contrato, contrato_id)
    if not contrato:
        raise HTTPException(404, "Contrato não encontrado")
    validar_empresa(db, contrato.empresa_id, usuario)
    opcoes = opcoes or GerarRecebiveisIn()

    if contrato.status == "CANCELADO":
        raise HTTPException(400, "Contrato cancelado não gera contas a receber.")

    comissao_comprador = dinheiro(contrato.comissao_comprador_valor)
    comissao_vendedor = dinheiro(contrato.comissao_vendedor_valor)
    if not comissao_comprador and not comissao_vendedor:
        raise HTTPException(
            400, "Informe a comissão do comprador e/ou do vendedor antes de gerar os recebíveis."
        )

    criados = []
    if opcoes.gerar_comprador and comissao_comprador > 0:
        if contrato.lancamento_comprador_id:
            raise HTTPException(400, "A comissão do comprador já foi gerada.")
        lanc = _criar_recebivel(
            db, contrato, contrato.comprador_id, comissao_comprador, "do comprador", opcoes, usuario
        )
        contrato.lancamento_comprador_id = lanc.id
        criados.append({"lado": "comprador", "lancamento_id": lanc.id, "valor": comissao_comprador})

    if opcoes.gerar_vendedor and comissao_vendedor > 0:
        if contrato.lancamento_vendedor_id:
            raise HTTPException(400, "A comissão do vendedor já foi gerada.")
        lanc = _criar_recebivel(
            db, contrato, contrato.vendedor_id, comissao_vendedor, "do vendedor", opcoes, usuario
        )
        contrato.lancamento_vendedor_id = lanc.id
        criados.append({"lado": "vendedor", "lancamento_id": lanc.id, "valor": comissao_vendedor})

    if not criados:
        raise HTTPException(400, "Nenhuma comissão selecionada para gerar.")

    db.flush()
    sincronizar_status(db, contrato)
    db.commit()
    db.refresh(contrato)
    return {
        "ok": True,
        "gerados": criados,
        "contrato": contrato_dict(db, contrato, completo=True),
        "mensagem": f"{len(criados)} conta(s) a receber gerada(s) a partir do contrato "
                    f"{contrato.numero}.",
    }


@router.post("/{contrato_id}/estornar-recebiveis")
def estornar_recebiveis(
    contrato_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)
):
    """Apaga as contas a receber geradas, desde que ainda não tenham baixa."""
    contrato = db.get(Contrato, contrato_id)
    if not contrato:
        raise HTTPException(404, "Contrato não encontrado")
    validar_empresa(db, contrato.empresa_id, usuario)

    removidos = 0
    for campo in ("lancamento_comprador_id", "lancamento_vendedor_id"):
        lanc_id = getattr(contrato, campo)
        if not lanc_id:
            continue
        lanc = db.get(Lancamento, lanc_id)
        if lanc:
            if any(p.baixas for p in lanc.parcelas):
                raise HTTPException(
                    400,
                    f"O título '{lanc.descricao}' já tem baixa. Estorne a baixa antes de "
                    "cancelar os recebíveis do contrato.",
                )
            contabil.estornar(db, "LANCAMENTO", lanc.id)
            db.delete(lanc)
            removidos += 1
        setattr(contrato, campo, None)

    contrato.status = "ABERTO"
    db.commit()
    db.refresh(contrato)
    return {
        "ok": True,
        "removidos": removidos,
        "contrato": contrato_dict(db, contrato, completo=True),
    }


@router.post("/{contrato_id}/cancelar")
def cancelar_contrato(
    contrato_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)
):
    contrato = db.get(Contrato, contrato_id)
    if not contrato:
        raise HTTPException(404, "Contrato não encontrado")
    validar_empresa(db, contrato.empresa_id, usuario)
    if contrato.lancamento_comprador_id or contrato.lancamento_vendedor_id:
        raise HTTPException(400, "Estorne as contas a receber antes de cancelar o contrato.")
    contrato.status = "CANCELADO"
    db.commit()
    return contrato_dict(db, contrato, completo=True)


@router.post("/{contrato_id}/reabrir")
def reabrir_contrato(
    contrato_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)
):
    """Volta um contrato cancelado para aberto."""
    contrato = db.get(Contrato, contrato_id)
    if not contrato:
        raise HTTPException(404, "Contrato não encontrado")
    validar_empresa(db, contrato.empresa_id, usuario)
    if contrato.status != "CANCELADO":
        raise HTTPException(400, "Só um contrato cancelado pode ser reaberto.")
    contrato.status = "ABERTO"
    sincronizar_status(db, contrato)
    db.commit()
    return contrato_dict(db, contrato, completo=True)
