"""Contratos de café: corretagem, compra e venda.

Três tipos, no mesmo cadastro:

* **CORRETAGEM** — a empresa só aproxima comprador e vendedor e cobra comissão dos
  dois lados. Gera as **contas a receber** das duas comissões.
* **COMPRA** — a empresa compra o café de um fornecedor. Gera a **conta a pagar** do
  fornecedor (valor da mercadoria) e, se houver agente, a conta a pagar da comissão dele.
* **VENDA** — a empresa vende o café para um cliente. Gera a **conta a receber** do
  cliente (valor da mercadoria) e, se houver agente, a conta a pagar da comissão dele.

Na compra o comprador é a própria empresa; na venda, o vendedor. Por isso um dos dois
campos fica em branco e a folha impressa mostra o nome da empresa naquele lado.
Todos os títulos saem classificados e contabilizados.
"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from .. import contabil
from ..icms import calcular_icms
from ..database import get_db
from ..deps import acesso_liberado, exigir_modulo, validar_empresa
from ..models import (
    Contrato,
    ContaContabil,
    Empresa,
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

# O menu deste módulo pode ser tirado de um plano (ou de um cliente) na área
# do administrador. Quem fecha a porta de verdade é a dependência abaixo:
# esconder o botão no menu não impede ninguém de chamar a rota pelo endereço.
router = APIRouter(prefix="/api/contratos", tags=["contratos"],
                   dependencies=[Depends(exigir_modulo("CONTRATOS"))])

CODIGO_CONTA_COMISSAO = "3.1.01.004"

TIPOS_CONTRATO = {
    "CORRETAGEM": "Corretagem (intermediação)",
    "COMPRA": "Compra de café",
    "VENDA": "Venda de café",
}

# conta contábil padrão de cada tipo: (parâmetro, código, nome, tipo, natureza, grupo do DRE)
CONTAS_PADRAO = {
    "comissao_recebida": ("conta_comissao", CODIGO_CONTA_COMISSAO,
                          "Receita de Corretagem e Comissoes", "RECEITA", "C", "RECEITA_BRUTA"),
    "venda": ("conta_venda_mercadoria", "3.1.01.001",
              "Receita de Venda de Mercadorias", "RECEITA", "C", "RECEITA_BRUTA"),
    "compra": ("conta_compra_mercadoria", "4.1.01.001",
               "Custo das Mercadorias Vendidas", "CUSTO", "D", "CUSTO"),
    "comissao_paga": ("conta_comissao_paga", "4.4.01.001",
                      "Comissoes sobre Vendas", "DESPESA", "D", "DESPESA_COMERCIAL"),
}


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
    if dados.agente_id:
        agente = db.get(Parceiro, dados.agente_id)
        if not agente or agente.empresa_id != contrato.empresa_id:
            raise HTTPException(400, "Selecione um agente válido.")
    # ICMS informativo: alíquota da tabela (UF vendedor x UF comprador) ou digitada
    for campo, valor in calcular_icms(
        db, contrato.empresa_id, contrato.vendedor_id, contrato.comprador_id,
        contrato.produto_id, contrato.valor_total, dados.icms_manual, dados.icms_percentual,
    ).items():
        setattr(contrato, campo, valor)


# --------------------------------------------------------------------------- #
# Cálculos
# --------------------------------------------------------------------------- #
def calcular(dados: ContratoIn) -> dict:
    """Valor negociado, comissões e comissão do agente.

    O percentual manda; o valor pode ser digitado quando foi combinado fechado."""
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
        "agente_valor": (comissao(dados.agente_percentual, dados.agente_valor)
                         if dados.agente_id else 0.0),
    }


def conta_padrao(db: Session, empresa_id: int, uso: str) -> int:
    """Conta contábil usada nos títulos do contrato; cria a padrão se faltar.

    uso: comissao_recebida (corretagem), venda, compra ou comissao_paga (agente)."""
    chave, codigo, nome, tipo, natureza, grupo = CONTAS_PADRAO[uso]
    conta_id = parametro_conta(db, empresa_id, chave)
    if conta_id and db.get(ContaContabil, conta_id):
        return conta_id

    conta = (
        db.query(ContaContabil)
        .filter(ContaContabil.empresa_id == empresa_id, ContaContabil.codigo == codigo)
        .first()
    )
    if not conta:
        pai = (
            db.query(ContaContabil)
            .filter(ContaContabil.empresa_id == empresa_id,
                    ContaContabil.codigo == codigo.rsplit(".", 2)[0])
            .first()
        )
        conta = ContaContabil(
            empresa_id=empresa_id,
            codigo=codigo,
            nome=nome,
            tipo=tipo,
            natureza=natureza,
            analitica=True,
            nivel=4,
            pai_id=pai.id if pai else None,
            grupo_dre=grupo,
        )
        db.add(conta)
        db.flush()

    from ..models import Parametro

    registro = (
        db.query(Parametro)
        .filter(Parametro.empresa_id == empresa_id, Parametro.chave == chave)
        .first()
    )
    if registro:
        registro.valor = str(conta.id)
    else:
        db.add(Parametro(empresa_id=empresa_id, chave=chave, valor=str(conta.id)))
    db.flush()
    return conta.id


def conta_comissao(db: Session, empresa_id: int) -> int:
    """Conta de receita das comissões de corretagem (compatibilidade)."""
    return conta_padrao(db, empresa_id, "comissao_recebida")


def conta_do_contrato(db: Session, contrato: Contrato) -> int:
    """Conta contábil da mercadoria/comissão principal, conforme o tipo."""
    uso = {"COMPRA": "compra", "VENDA": "venda"}.get(contrato.tipo, "comissao_recebida")
    return conta_padrao(db, contrato.empresa_id, uso)


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

# na compra o dinheiro sai, então os mesmos códigos aparecem com outro nome
STATUS_COMPRA = {
    "ABERTO": "Aberto",
    "FECHADO_A_RECEBER": "Fechado a Pagar",
    "RECEBIDO_PARCIAL": "Fechado Pago Parcial",
    "RECEBIDO_TOTAL": "Fechado Pago Total",
    "CANCELADO": "Cancelado",
}


def nome_status(tipo: str, status: str) -> str:
    tabela = STATUS_COMPRA if tipo == "COMPRA" else STATUS_CONTRATO
    return tabela.get(status, status)


def previsto_receber(c: Contrato) -> float:
    """Quanto o contrato traz para a empresa."""
    if c.tipo == "VENDA":
        return dinheiro(c.valor_total)
    if c.tipo == "COMPRA":
        return 0.0
    return round(dinheiro(c.comissao_comprador_valor) + dinheiro(c.comissao_vendedor_valor), 2)


def previsto_pagar(c: Contrato) -> float:
    """Quanto a empresa paga: o café comprado e a comissão do agente."""
    pagar = dinheiro(c.agente_valor)
    if c.tipo == "COMPRA":
        pagar += dinheiro(c.valor_total)
    return round(pagar, 2)


def valor_previsto(c: Contrato) -> float:
    """Quanto o contrato deve virar título (para saber se já foi tudo gerado)."""
    if c.tipo in ("COMPRA", "VENDA"):
        return round(dinheiro(c.valor_total) + dinheiro(c.agente_valor), 2)
    return round(dinheiro(c.comissao_comprador_valor) + dinheiro(c.comissao_vendedor_valor), 2)

# como cada status aparece na tela (classe da tag colorida)
TAG_STATUS = {
    "ABERTO": "tag-aberto",
    "FECHADO_A_RECEBER": "tag-a-receber",
    "RECEBIDO_PARCIAL": "tag-parcial",
    "RECEBIDO_TOTAL": "tag-pago",
    "CANCELADO": "tag-cancelado",
}


CAMPOS_LANCAMENTO = ("lancamento_comprador_id", "lancamento_vendedor_id",
                     "lancamento_mercadoria_id", "lancamento_agente_id")


def _lancamentos_do_contrato(db: Session, c: Contrato) -> list[Lancamento]:
    ids = [getattr(c, campo) for campo in CAMPOS_LANCAMENTO if getattr(c, campo)]
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
    comissao = valor_previsto(c)
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


def nome_da_empresa(db: Session, empresa_id: int) -> str:
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        return "Minha empresa"
    return empresa.nome_fantasia or empresa.razao_social


def contrato_dict(db: Session, c: Contrato, completo: bool = False) -> dict:
    total_comissao = round(
        dinheiro(c.comissao_comprador_valor) + dinheiro(c.comissao_vendedor_valor), 2
    )
    financeiro = sincronizar_status(db, c)   # o status acompanha as baixas
    minha = nome_da_empresa(db, c.empresa_id)
    compra, venda = c.tipo == "COMPRA", c.tipo == "VENDA"
    parceiro = c.vendedor if compra else c.comprador if venda else None
    dados = serializar(
        c,
        extras={
            "comprador_nome": c.comprador.nome if c.comprador else (minha if compra else "-"),
            "comprador_documento": c.comprador.cpf_cnpj if c.comprador else "",
            "vendedor_nome": c.vendedor.nome if c.vendedor else (minha if venda else "-"),
            "vendedor_documento": c.vendedor.cpf_cnpj if c.vendedor else "",
            "tipo_nome": TIPOS_CONTRATO.get(c.tipo, c.tipo),
            "empresa_nome": minha,
            "parceiro_nome": parceiro.nome if parceiro else None,
            "parceiro_papel": "Fornecedor" if compra else "Cliente" if venda else None,
            "agente_nome": c.agente.nome if c.agente else None,
            "valor_previsto": valor_previsto(c),
            "previsto_receber": previsto_receber(c),
            "previsto_pagar": previsto_pagar(c),
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
            "icms_regra": (
                f"{c.icms_uf_origem or '?'} → {c.icms_uf_destino or '?'}"
                if (c.icms_uf_origem or c.icms_uf_destino) else None
            ),
            "status_nome": nome_status(c.tipo, c.status),
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
        dados["titulo_mercadoria"] = _saldo_lancamento(db, c.lancamento_mercadoria_id)
        dados["titulo_agente"] = _saldo_lancamento(db, c.lancamento_agente_id)
    return dados


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
def tem_titulos(c: Contrato) -> bool:
    return any(getattr(c, campo) for campo in CAMPOS_LANCAMENTO)


def _validar_partes(db: Session, dados: ContratoIn, usuario: Usuario):
    """Confere as partes conforme o tipo do contrato.

    Compra: só o vendedor (o comprador é a empresa). Venda: só o comprador.
    Corretagem: os dois, e diferentes entre si."""
    validar_empresa(db, dados.empresa_id, usuario)
    if dados.tipo not in TIPOS_CONTRATO:
        raise HTTPException(400, "Escolha o tipo do contrato: corretagem, compra ou venda.")

    if dados.tipo == "COMPRA":
        obrigatorios = [("vendedor", dados.vendedor_id, "de quem você está comprando")]
        dados.comprador_id = None
    elif dados.tipo == "VENDA":
        obrigatorios = [("comprador", dados.comprador_id, "para quem você está vendendo")]
        dados.vendedor_id = None
    else:
        obrigatorios = [("comprador", dados.comprador_id, ""), ("vendedor", dados.vendedor_id, "")]
        if dados.comprador_id == dados.vendedor_id:
            raise HTTPException(400, "O comprador e o vendedor devem ser cadastros diferentes.")

    for campo, parceiro_id, ajuda in obrigatorios:
        parceiro = db.get(Parceiro, parceiro_id) if parceiro_id else None
        if not parceiro or parceiro.empresa_id != dados.empresa_id:
            extra = f" ({ajuda})" if ajuda else ""
            raise HTTPException(400, f"Selecione um {campo} válido{extra}.")

    if dados.agente_id and dados.agente_id in (dados.comprador_id, dados.vendedor_id):
        raise HTTPException(400, "O agente precisa ser um cadastro diferente das partes.")


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
        contrato.conta_contabil_id = conta_do_contrato(db, contrato)
    aplicar_cadastros(db, contrato, dados)
    db.add(contrato)
    db.commit()
    db.refresh(contrato)
    return contrato_dict(db, contrato, completo=True)


@router.get("")
def listar_contratos(
    empresa_id: int,
    tipo: str | None = None,
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
    if tipo:
        query = query.filter(Contrato.tipo == tipo)
    if parceiro_id:
        query = query.filter(
            or_(Contrato.comprador_id == parceiro_id, Contrato.vendedor_id == parceiro_id,
                Contrato.agente_id == parceiro_id)
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
            "comissao_agente": soma("agente_valor"),
            "a_receber_total": soma("previsto_receber"),
            "a_pagar_total": soma("previsto_pagar"),
            "por_status": {
                codigo: sum(1 for l in linhas if l["status"] == codigo)
                for codigo in STATUS_CONTRATO
            },
            "por_tipo": {
                codigo: sum(1 for l in linhas if l["tipo"] == codigo)
                for codigo in TIPOS_CONTRATO
            },
        },
        "status": [{"codigo": c, "nome": n} for c, n in STATUS_CONTRATO.items()],
        "tipos": [{"codigo": c, "nome": n} for c, n in TIPOS_CONTRATO.items()],
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

    def parte_empresa() -> dict:
        """A própria empresa como parte (compra: comprador; venda: vendedor)."""
        return {
            "nome": empresa.razao_social or empresa.nome_fantasia,
            "nome_fantasia": empresa.nome_fantasia,
            "pessoa": "J",
            "cpf_cnpj": empresa.cnpj,
            "rg_ie": empresa.inscricao_estadual,
            "endereco": endereco_linha(empresa),
            "telefone": empresa.telefone,
            "email": empresa.email,
            "e_minha_empresa": True,
            "formas": [],
        }

    unidade = db.get(Unidade, contrato.unidade_id) if contrato.unidade_id else None
    return {
        "contrato": contrato_dict(db, contrato, completo=True),
        "empresa": dict(
            serializar(empresa),
            endereco=endereco_linha(empresa),
        ),
        "comprador": parte_empresa() if contrato.tipo == "COMPRA" else parte(contrato.comprador),
        "vendedor": parte_empresa() if contrato.tipo == "VENDA" else parte(contrato.vendedor),
        "agente": parte(contrato.agente) if contrato.agente_id else None,
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
    if tem_titulos(contrato):
        raise HTTPException(
            400,
            "Este contrato já gerou títulos. Estorne-os antes de alterá-lo.",
        )
    _validar_partes(db, dados, usuario)
    calculado = calcular(dados)
    for campo, valor in dados.model_dump().items():
        if hasattr(contrato, campo) and campo not in ("empresa_id",):
            setattr(contrato, campo, valor)
    for campo, valor in calculado.items():
        setattr(contrato, campo, valor)
    if not contrato.conta_contabil_id:
        contrato.conta_contabil_id = conta_do_contrato(db, contrato)
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
    if tem_titulos(contrato):
        raise HTTPException(
            400, "Estorne os títulos gerados por este contrato antes de excluí-lo."
        )
    db.delete(contrato)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Geração das contas a receber
# --------------------------------------------------------------------------- #
def _criar_titulo(
    db: Session,
    contrato: Contrato,
    parceiro_id: int,
    valor: float,
    descricao: str,
    usuario: Usuario,
    tipo_titulo: str = "RECEBER",
    conta_contabil_id: int | None = None,
    vencimento: date | None = None,
    parcelas: int = 1,
    periodicidade: str = "MENSAL",
    intervalo_dias: int = 30,
) -> Lancamento:
    """Cria o título (a receber ou a pagar) do contrato, já contabilizado."""
    base = vencimento or contrato.data_pagamento or contrato.data or date.today()
    qtd = max(1, int(parcelas or 1))

    lanc = Lancamento(
        empresa_id=contrato.empresa_id,
        tipo=tipo_titulo,
        modo="MULTIPLO" if qtd > 1 else "SIMPLES",
        numero_documento=contrato.numero,
        parceiro_id=parceiro_id,
        descricao=descricao,
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
            conta_contabil_id=conta_contabil_id or contrato.conta_contabil_id
            or conta_do_contrato(db, contrato),
            centro_custo_id=contrato.centro_custo_id,
            operacao_id=contrato.operacao_id,
            descricao=descricao,
            valor=valor,
        )
    )

    valor_parcela = round(valor / qtd, 2)
    acumulado = 0.0
    for i in range(qtd):
        if periodicidade == "DIAS":
            dia = base + timedelta(days=int(intervalo_dias or 30) * i)
        else:
            dia = adicionar_meses(base, i)
        parcela = valor_parcela if i < qtd - 1 else round(valor - acumulado, 2)
        acumulado += parcela
        db.add(
            Parcela(
                lancamento_id=lanc.id,
                numero=i + 1,
                data_vencimento=dia,
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
    """Cria os títulos do contrato.

    Corretagem: contas a receber das comissões do comprador e do vendedor.
    Compra: conta a pagar do fornecedor e, se houver, a do agente.
    Venda: conta a receber do cliente e a conta a pagar do agente.
    """
    contrato = db.get(Contrato, contrato_id)
    if not contrato:
        raise HTTPException(404, "Contrato não encontrado")
    validar_empresa(db, contrato.empresa_id, usuario)
    opcoes = opcoes or GerarRecebiveisIn()

    if contrato.status == "CANCELADO":
        raise HTTPException(400, "Contrato cancelado não gera títulos.")

    criados = []

    def agente(vencimento_base):
        """Comissão do agente: sempre conta a pagar da empresa."""
        valor = dinheiro(contrato.agente_valor)
        if not (opcoes.gerar_agente and contrato.agente_id and valor > 0):
            return
        if contrato.lancamento_agente_id:
            raise HTTPException(400, "A comissão do agente já foi gerada.")
        lanc = _criar_titulo(
            db, contrato, contrato.agente_id, valor,
            f"Comissão do agente - contrato {contrato.numero}", usuario,
            tipo_titulo="PAGAR",
            conta_contabil_id=conta_padrao(db, contrato.empresa_id, "comissao_paga"),
            vencimento=opcoes.vencimento_agente or vencimento_base,
            parcelas=opcoes.num_parcelas_agente,
            periodicidade=opcoes.periodicidade, intervalo_dias=opcoes.intervalo_dias,
        )
        contrato.lancamento_agente_id = lanc.id
        criados.append({"lado": "agente", "tipo": "PAGAR", "lancamento_id": lanc.id, "valor": valor})

    if contrato.tipo in ("COMPRA", "VENDA"):
        compra = contrato.tipo == "COMPRA"
        valor = dinheiro(contrato.valor_total)
        if valor <= 0:
            raise HTTPException(400, "Informe o valor do contrato antes de gerar os títulos.")
        if opcoes.gerar_mercadoria:
            if contrato.lancamento_mercadoria_id:
                raise HTTPException(
                    400, "O título da mercadoria deste contrato já foi gerado.")
            parceiro_id = contrato.vendedor_id if compra else contrato.comprador_id
            if not parceiro_id:
                raise HTTPException(
                    400, "Contrato sem a outra parte: escolha o fornecedor ou o cliente.")
            lanc = _criar_titulo(
                db, contrato, parceiro_id, valor,
                f"{'Compra' if compra else 'Venda'} de {contrato.produto or 'café'} - "
                f"contrato {contrato.numero}",
                usuario,
                tipo_titulo="PAGAR" if compra else "RECEBER",
                conta_contabil_id=contrato.conta_contabil_id or conta_do_contrato(db, contrato),
                vencimento=opcoes.vencimento, parcelas=opcoes.num_parcelas,
                periodicidade=opcoes.periodicidade, intervalo_dias=opcoes.intervalo_dias,
            )
            contrato.lancamento_mercadoria_id = lanc.id
            criados.append({"lado": "mercadoria", "tipo": "PAGAR" if compra else "RECEBER",
                            "lancamento_id": lanc.id, "valor": valor})
        agente(opcoes.vencimento)
        if not criados:
            raise HTTPException(400, "Nada selecionado para gerar.")
    else:
        comissao_comprador = dinheiro(contrato.comissao_comprador_valor)
        comissao_vendedor = dinheiro(contrato.comissao_vendedor_valor)
        if not comissao_comprador and not comissao_vendedor and not dinheiro(contrato.agente_valor):
            raise HTTPException(
                400,
                "Informe a comissão do comprador e/ou do vendedor antes de gerar os recebíveis.",
            )
        if opcoes.gerar_comprador and comissao_comprador > 0:
            if contrato.lancamento_comprador_id:
                raise HTTPException(400, "A comissão do comprador já foi gerada.")
            lanc = _criar_titulo(
                db, contrato, contrato.comprador_id, comissao_comprador,
                f"Corretagem do comprador - contrato {contrato.numero}", usuario,
                vencimento=opcoes.vencimento, parcelas=opcoes.num_parcelas,
                periodicidade=opcoes.periodicidade, intervalo_dias=opcoes.intervalo_dias,
            )
            contrato.lancamento_comprador_id = lanc.id
            criados.append({"lado": "comprador", "tipo": "RECEBER", "lancamento_id": lanc.id,
                            "valor": comissao_comprador})

        if opcoes.gerar_vendedor and comissao_vendedor > 0:
            if contrato.lancamento_vendedor_id:
                raise HTTPException(400, "A comissão do vendedor já foi gerada.")
            lanc = _criar_titulo(
                db, contrato, contrato.vendedor_id, comissao_vendedor,
                f"Corretagem do vendedor - contrato {contrato.numero}", usuario,
                vencimento=opcoes.vencimento, parcelas=opcoes.num_parcelas,
                periodicidade=opcoes.periodicidade, intervalo_dias=opcoes.intervalo_dias,
            )
            contrato.lancamento_vendedor_id = lanc.id
            criados.append({"lado": "vendedor", "tipo": "RECEBER", "lancamento_id": lanc.id,
                            "valor": comissao_vendedor})
        agente(opcoes.vencimento)
        if not criados:
            raise HTTPException(400, "Nenhuma comissão selecionada para gerar.")

    db.flush()
    sincronizar_status(db, contrato)
    db.commit()
    db.refresh(contrato)
    a_receber = sum(1 for c in criados if c["tipo"] == "RECEBER")
    a_pagar = len(criados) - a_receber
    partes = []
    if a_receber:
        partes.append(f"{a_receber} conta(s) a receber")
    if a_pagar:
        partes.append(f"{a_pagar} conta(s) a pagar")
    return {
        "ok": True,
        "gerados": criados,
        "contrato": contrato_dict(db, contrato, completo=True),
        "mensagem": f"{' e '.join(partes)} gerada(s) a partir do contrato {contrato.numero}.",
    }


@router.post("/{contrato_id}/estornar-recebiveis")
def estornar_recebiveis(
    contrato_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)
):
    """Apaga os títulos gerados pelo contrato, desde que ainda não tenham baixa."""
    contrato = db.get(Contrato, contrato_id)
    if not contrato:
        raise HTTPException(404, "Contrato não encontrado")
    validar_empresa(db, contrato.empresa_id, usuario)

    removidos = 0
    for campo in CAMPOS_LANCAMENTO:
        lanc_id = getattr(contrato, campo)
        if not lanc_id:
            continue
        lanc = db.get(Lancamento, lanc_id)
        if lanc:
            if any(p.baixas for p in lanc.parcelas):
                raise HTTPException(
                    400,
                    f"O título '{lanc.descricao}' já tem baixa. Estorne a baixa antes de "
                    "cancelar os títulos do contrato.",
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
    if tem_titulos(contrato):
        raise HTTPException(400, "Estorne os títulos gerados antes de cancelar o contrato.")
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
