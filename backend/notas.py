"""Regras das notas fiscais: importar o XML, faturar e desfaturar.

Separado das rotas porque duas telas usam as mesmas regras: o **DF-e** (caixa de
entrada do que a SEFAZ entrega) e as **Notas Fiscais** (a tela de gestão, onde a
nota vira dinheiro no financeiro).

Faturar x desfaturar
--------------------
**Faturar** é transformar a nota em título: uma conta a **pagar** quando a nota é
de entrada (alguém emitiu contra o CNPJ da empresa) ou a **receber** quando é de
saída (a própria empresa emitiu). As parcelas saem das duplicatas da nota; se a
nota não tiver duplicata, sai uma parcela só.

**Desfaturar** desfaz isso **só no AgroDock**: apaga o título gerado, estorna as
partidas contábeis e libera a nota para ser faturada de novo. Não mexe na SEFAZ —
cancelar a nota lá é outro ato, feito pelo emitente.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import contabil, dfe as motor
from .models import (
    Empresa,
    Lancamento,
    LancamentoItem,
    Nota,
    NotaItem,
    NotaPagamento,
    Parcela,
    Parceiro,
    Produto,
    Unidade,
    Usuario,
)
from .utils import dinheiro, parse_data

# tamanho de cada campo fiscal do produto, para não estourar a coluna
TAMANHO_FISCAL = {
    "ncm": 10, "cest": 9, "cfop_padrao": 5, "unidade_comercial": 6,
    "unidade_tributavel": 6, "gtin": 14, "gtin_tributavel": 14, "cst_icms": 3,
}


# --------------------------------------------------------------------------- #
# De quem é a nota
# --------------------------------------------------------------------------- #
def cnpj_da_empresa(db: Session, empresa_id: int) -> str:
    empresa = db.get(Empresa, empresa_id)
    return motor.so_numeros(empresa.cnpj) if empresa else ""


def sentido(nota: Nota, cnpj_empresa: str) -> str:
    """Entrada ou saída **do ponto de vista da empresa**.

    A tag tpNF do XML é do ponto de vista de quem emitiu: uma venda do fornecedor
    (tpNF = 1, saída) é uma entrada para quem recebe. No DF-e quase tudo é nota de
    terceiro contra o nosso CNPJ, então o que vale é quem emitiu.
    """
    if cnpj_empresa and motor.so_numeros(nota.emitente_cnpj) == cnpj_empresa:
        return "Saída"
    return "Entrada"


def tipo_titulo_da_nota(db: Session, nota: Nota) -> str:
    """PAGAR numa nota de entrada, RECEBER numa nota emitida pela empresa."""
    return "PAGAR" if sentido(nota, cnpj_da_empresa(db, nota.empresa_id)) == "Entrada" else "RECEBER"


# --------------------------------------------------------------------------- #
# Cadastros preenchidos a partir do XML
# --------------------------------------------------------------------------- #
def unidade_padrao(db: Session, empresa_id: int, sigla: str) -> int | None:
    sigla = (sigla or "").strip().upper()[:20]
    if not sigla:
        return None
    unidade = (
        db.query(Unidade)
        .filter(Unidade.empresa_id == empresa_id, func.upper(Unidade.codigo) == sigla)
        .first()
    )
    if not unidade:
        unidade = Unidade(empresa_id=empresa_id, codigo=sigla, nome=sigla,
                          peso_conversao=60 if sigla in ("SC", "SACA") else 0)
        db.add(unidade)
        db.flush()
    return unidade.id


def parceiro_do_emitente(db: Session, nota: Nota, criar: bool) -> Parceiro | None:
    """Acha (ou cria) o cliente/fornecedor do emitente e completa os dados fiscais."""
    documento = motor.so_numeros(nota.emitente_cnpj)
    parceiro = None
    if documento:
        parceiro = next(
            (p for p in db.query(Parceiro).filter(Parceiro.empresa_id == nota.empresa_id).all()
             if motor.so_numeros(p.cpf_cnpj) == documento),
            None,
        )
    if not parceiro and not criar:
        return None

    emit = None
    try:
        emit = ET.fromstring(nota.xml or "").find(f".//{{{motor.NS}}}emit")
    except ET.ParseError:
        emit = None

    def campo(*nomes):
        if emit is None:
            return ""
        for nome in nomes:
            achado = emit.find(f".//{{{motor.NS}}}{nome}")
            if achado is not None and achado.text:
                return achado.text.strip()
        return ""

    if not parceiro:
        parceiro = Parceiro(
            empresa_id=nota.empresa_id,
            tipo="FORNECEDOR" if nota.tipo_operacao != "0" else "CLIENTE",
            pessoa="J" if len(documento) == 14 else "F",
            nome=(nota.emitente_nome or "SEM NOME")[:160],
            cpf_cnpj=documento or None,
        )
        db.add(parceiro)

    # completa só o que estiver em branco — não sobrescreve o que o usuário digitou
    preencher = {
        "nome_fantasia": campo("xFant"),
        "rg_ie": nota.emitente_ie or campo("IE"),
        "logradouro": campo("xLgr"),
        "numero": campo("nro"),
        "complemento": campo("xCpl"),
        "bairro": campo("xBairro"),
        "cidade": campo("xMun"),
        "uf": nota.emitente_uf or campo("UF"),
        "cep": campo("CEP"),
        "telefone": campo("fone"),
        "codigo_municipio": campo("cMun"),
        "codigo_pais": campo("cPais") or "1058",
        "pais": campo("xPais") or "BRASIL",
    }
    for nome, valor in preencher.items():
        if valor and not getattr(parceiro, nome, None):
            setattr(parceiro, nome, valor[:160])
    if not parceiro.indicador_ie or parceiro.indicador_ie == "9":
        parceiro.indicador_ie = "1" if (parceiro.rg_ie or "").strip() else "9"
    if not parceiro.regime_tributario:
        parceiro.regime_tributario = {
            "1": "SIMPLES NACIONAL", "2": "SIMPLES NACIONAL - EXCESSO",
            "3": "REGIME NORMAL",
        }.get(campo("CRT"), None)
    db.flush()
    return parceiro


def produto_do_item(db: Session, empresa_id: int, item: dict,
                    atualizar: bool) -> tuple[Produto | None, bool]:
    """Acha o produto do cadastro pelo código/GTIN/nome; cria quando não existir.

    Devolve (produto, criado agora?).
    """
    codigo = (item.get("codigo") or "").strip()[:20]
    gtin = (item.get("gtin") or "").strip()
    descricao = (item.get("descricao") or "").strip()
    produtos = db.query(Produto).filter(Produto.empresa_id == empresa_id).all()

    produto = next((p for p in produtos if codigo and (p.codigo or "").strip() == codigo), None)
    if not produto and gtin:
        produto = next((p for p in produtos if (p.gtin or "").strip() == gtin), None)
    if not produto and descricao:
        produto = next(
            (p for p in produtos if (p.nome or "").strip().upper() == descricao.upper()), None)
    criado = False
    if not produto:
        if not atualizar:
            return None, False
        base = codigo or (gtin[-14:] if gtin else f"NF{abs(hash(descricao)) % 99999:05d}")
        existentes = {(p.codigo or "").upper() for p in produtos}
        novo_codigo, sufixo = base.upper()[:20], 1
        while novo_codigo in existentes:
            sufixo += 1
            novo_codigo = f"{base.upper()[:16]}-{sufixo}"
        produto = Produto(empresa_id=empresa_id, codigo=novo_codigo,
                          nome=(descricao or "PRODUTO")[:120])
        db.add(produto)
        criado = True
    if not atualizar:
        return produto, False

    unidade = (item.get("unidade") or "").strip().upper()
    fiscais = {
        "ncm": item.get("ncm"), "cest": item.get("cest"), "cfop_padrao": item.get("cfop"),
        "unidade_comercial": unidade, "unidade_tributavel": unidade,
        "gtin": gtin, "gtin_tributavel": gtin, "cst_icms": item.get("icms_cst"),
    }
    for nome, valor in fiscais.items():
        if valor and not getattr(produto, nome, None):
            setattr(produto, nome, str(valor)[:TAMANHO_FISCAL[nome]])
    if not produto.aliquota_icms and item.get("icms_aliquota"):
        produto.aliquota_icms = round(float(item["icms_aliquota"]), 4)
    if not produto.origem:
        produto.origem = "0"
    if not produto.unidade_id and unidade:
        produto.unidade_id = unidade_padrao(db, empresa_id, unidade)
    db.flush()
    return produto, criado


# --------------------------------------------------------------------------- #
# Importação do XML para as tabelas da nota
# --------------------------------------------------------------------------- #
def importar_xml(db: Session, nota: Nota, criar_parceiro: bool = True,
                 atualizar_produtos: bool = True) -> dict:
    """Grava itens e pagamentos da nota e completa os cadastros. Não gera título."""
    if nota.resumo or not nota.xml:
        raise HTTPException(
            400,
            "Esta nota está no sistema apenas como resumo. Dê ciência da operação e busque "
            "os documentos de novo para receber o XML completo.",
        )
    lido = motor.ler_documento(nota.xml, nota.esquema or "")
    if not lido:
        raise HTTPException(400, "Não foi possível ler o XML desta nota.")

    nota.itens.clear()
    nota.pagamentos.clear()
    db.flush()

    parceiro = parceiro_do_emitente(db, nota, criar_parceiro)
    if parceiro:
        nota.parceiro_id = parceiro.id

    produtos_criados = produtos_ligados = 0
    for item in lido.get("itens", []):
        produto, criado = produto_do_item(db, nota.empresa_id, item, atualizar_produtos)
        if produto is not None:
            produtos_ligados += 1
            produtos_criados += 1 if criado else 0
        db.add(NotaItem(
            nota_id=nota.id,
            numero=item.get("numero") or 1,
            codigo=(item.get("codigo") or "")[:60],
            gtin=(item.get("gtin") or "")[:14],
            descricao=(item.get("descricao") or "-")[:200],
            ncm=(item.get("ncm") or "")[:10],
            cest=(item.get("cest") or "")[:9],
            cfop=(item.get("cfop") or "")[:5],
            unidade=(item.get("unidade") or "")[:10],
            quantidade=item.get("quantidade") or 0,
            valor_unitario=item.get("valor_unitario") or 0,
            valor_total=dinheiro(item.get("valor_total")),
            desconto=dinheiro(item.get("desconto")),
            frete=dinheiro(item.get("frete")),
            icms_cst=(item.get("icms_cst") or "")[:3],
            icms_base=dinheiro(item.get("icms_base")),
            icms_aliquota=item.get("icms_aliquota") or 0,
            icms_valor=dinheiro(item.get("icms_valor")),
            ipi_valor=dinheiro(item.get("ipi_valor")),
            pis_valor=dinheiro(item.get("pis_valor")),
            cofins_valor=dinheiro(item.get("cofins_valor")),
            produto_id=produto.id if produto is not None else None,
        ))

    for pagamento in lido.get("pagamentos", []):
        db.add(NotaPagamento(
            nota_id=nota.id,
            origem=pagamento.get("origem") or "PAGAMENTO",
            codigo=(pagamento.get("codigo") or "")[:2],
            descricao=(pagamento.get("descricao") or "")[:80],
            numero=(pagamento.get("numero") or "")[:60],
            vencimento=parse_data(pagamento.get("vencimento")),
            valor=dinheiro(pagamento.get("valor")),
            troco=dinheiro(pagamento.get("troco")),
            bandeira=(pagamento.get("bandeira") or "")[:30],
            cnpj_credenciadora=(pagamento.get("cnpj_credenciadora") or "")[:20],
            autorizacao=(pagamento.get("autorizacao") or "")[:40],
        ))

    nota.importada = True
    nota.importada_em = datetime.utcnow()
    db.flush()
    db.refresh(nota)
    return {
        "parceiro": parceiro,
        "produtos_ligados": produtos_ligados,
        "produtos_criados": produtos_criados,
        "itens": len(nota.itens),
        "pagamentos": len(nota.pagamentos),
    }


# --------------------------------------------------------------------------- #
# Faturar e desfaturar
# --------------------------------------------------------------------------- #
def titulo_da_nota(db: Session, nota: Nota) -> Lancamento | None:
    """O título gerado pela nota — ou None se ele não existe mais (excluído por fora)."""
    if not nota.lancamento_id:
        return None
    lancamento = db.get(Lancamento, nota.lancamento_id)
    if lancamento is None:
        nota.lancamento_id = None
        nota.faturada_em = None
    return lancamento


def faturar(db: Session, nota: Nota, opcoes, usuario: Usuario) -> Lancamento:
    """Gera a conta a pagar (ou a receber) da nota, já classificada e contabilizada.

    Importa o XML antes, se a nota ainda não tiver itens — assim o usuário fatura
    numa tacada só, sem precisar lembrar de importar primeiro.
    """
    if titulo_da_nota(db, nota) is not None:
        raise HTTPException(
            400, "Esta nota já está faturada. Desfature antes de gerar outro título.")
    if nota.situacao == "CANCELADA":
        raise HTTPException(400, "Esta nota está cancelada na SEFAZ e não pode ser faturada.")
    if not nota.itens:
        importar_xml(db, nota, getattr(opcoes, "criar_parceiro", True),
                     getattr(opcoes, "atualizar_produtos", True))

    valor = dinheiro(getattr(opcoes, "valor", None) or nota.valor_total)
    if valor <= 0:
        raise HTTPException(400, "A nota está sem valor total: não dá para gerar o título.")
    parceiro_id = getattr(opcoes, "parceiro_id", None) or nota.parceiro_id
    if not parceiro_id:
        raise HTTPException(
            400, "Para faturar é preciso ligar a nota a um cliente/fornecedor.")
    nota.parceiro_id = parceiro_id

    tipo = (getattr(opcoes, "tipo_titulo", None) or tipo_titulo_da_nota(db, nota)).upper()
    if tipo not in ("PAGAR", "RECEBER"):
        raise HTTPException(400, "O título tem de ser a pagar ou a receber.")

    from .routers.contratos import conta_padrao  # importado aqui para não criar ciclo

    conta_id = getattr(opcoes, "conta_contabil_id", None) or conta_padrao(
        db, nota.empresa_id, "compra" if tipo == "PAGAR" else "venda")

    emissao = (nota.data_emissao or datetime.utcnow()).date()
    nome = nota.emitente_nome if tipo == "PAGAR" else (nota.destinatario_nome or nota.emitente_nome)
    descricao = f"NF-e {nota.numero or ''}/{nota.serie or ''} - {nome or ''}".strip(" -/")
    lancamento = Lancamento(
        empresa_id=nota.empresa_id,
        tipo=tipo,
        modo="SIMPLES",
        numero_documento=(nota.numero or "")[:40],
        parceiro_id=parceiro_id,
        descricao=descricao[:200],
        data_emissao=emissao,
        data_competencia=emissao,
        valor_total=valor,
        operacao_id=getattr(opcoes, "operacao_id", None),
        observacao=f"Chave {motor.formatar_chave(nota.chave)}",
        usuario_id=usuario.id,
    )
    db.add(lancamento)
    db.flush()
    db.add(LancamentoItem(
        lancamento_id=lancamento.id, conta_contabil_id=conta_id,
        centro_custo_id=getattr(opcoes, "centro_custo_id", None),
        operacao_id=getattr(opcoes, "operacao_id", None),
        descricao=descricao[:200], valor=valor,
    ))

    duplicatas = [p for p in nota.pagamentos if p.origem == "DUPLICATA" and p.vencimento]
    usar_duplicatas = duplicatas and not getattr(opcoes, "vencimento", None)
    if usar_duplicatas:
        lancamento.modo = "MULTIPLO" if len(duplicatas) > 1 else "SIMPLES"
        soma = 0.0
        for numero, dup in enumerate(duplicatas, start=1):
            parcela = dinheiro(dup.valor) if numero < len(duplicatas) else round(valor - soma, 2)
            soma += parcela
            db.add(Parcela(lancamento_id=lancamento.id, numero=numero,
                           data_vencimento=dup.vencimento, valor=parcela))
    else:
        db.add(Parcela(lancamento_id=lancamento.id, numero=1,
                       data_vencimento=getattr(opcoes, "vencimento", None) or emissao,
                       valor=valor))
    db.flush()
    db.refresh(lancamento)
    contabil.contabilizar_lancamento(db, lancamento)

    nota.lancamento_id = lancamento.id
    nota.faturada_em = datetime.utcnow()
    nota.faturada_por_id = usuario.id
    observacao = (getattr(opcoes, "observacao", None) or "").strip()
    nota.faturamento_observacao = observacao[:300] or None
    db.flush()
    return lancamento


def desfaturar(db: Session, nota: Nota) -> dict:
    """Apaga o título gerado pela nota e libera a nota para faturar de novo.

    Só no AgroDock: a nota continua igual na SEFAZ. Um título com baixa (dinheiro
    que já entrou ou saiu) não é apagado — primeiro estorne a baixa.
    """
    lancamento = titulo_da_nota(db, nota)
    if lancamento is None:
        nota.faturada_em = nota.faturada_por_id = nota.faturamento_observacao = None
        raise HTTPException(400, "Esta nota não está faturada.")
    baixas = [b for p in lancamento.parcelas for b in p.baixas]
    if baixas:
        raise HTTPException(
            400,
            f"O título desta nota já tem {len(baixas)} baixa(s). Estorne as baixas em "
            f"Contas a {'Pagar' if lancamento.tipo == 'PAGAR' else 'Receber'} antes de desfaturar.",
        )
    contabil.estornar(db, "LANCAMENTO", lancamento.id)
    numero = lancamento.id
    tipo = lancamento.tipo
    db.delete(lancamento)
    nota.lancamento_id = None
    nota.faturada_em = None
    nota.faturada_por_id = None
    nota.faturamento_observacao = None
    db.flush()
    return {"lancamento_id": numero, "tipo": tipo}
