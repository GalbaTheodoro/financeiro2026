"""ICMS dos contratos: tabela UF do vendedor x UF do comprador e o cálculo.

O ICMS aqui é informativo: aparece no contrato e na impressão, mas não altera o
valor negociado nem a corretagem. Valor = valor negociado x alíquota.

Qual linha da tabela vale
-------------------------
1. linha ativa do mesmo par de estados **e do mesmo produto** do contrato;
2. se não houver, linha ativa do par de estados com produto em branco ("todos").

Referência para gerar a tabela (Resolução do Senado nº 22/1989)
-------------------------------------------------------------
Nas operações interestaduais, saindo de MG, PR, RJ, RS, SC ou SP para os estados do
Norte, Nordeste, Centro-Oeste e o Espírito Santo: 7%. Nas demais operações entre
estados: 12%. É só um ponto de partida — isenção, diferimento e redução de base do
café e de outros produtos agrícolas variam por estado, e o contador deve confirmar.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AliquotaIcms, Empresa, Parceiro

UFS = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB",
    "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]
SUL_SUDESTE_SEM_ES = {"MG", "PR", "RJ", "RS", "SC", "SP"}


def normalizar_uf(uf: str | None) -> str | None:
    texto = (uf or "").strip().upper()
    return texto if texto in UFS else None


def aliquota_interestadual(origem: str, destino: str) -> float | None:
    """Alíquota interestadual de referência (None quando origem = destino)."""
    if origem == destino:
        return None
    if origem in SUL_SUDESTE_SEM_ES and destino not in SUL_SUDESTE_SEM_ES:
        return 7.0
    return 12.0


def buscar_aliquota(db: Session, empresa_id: int, uf_origem: str | None,
                    uf_destino: str | None, produto_id: int | None) -> AliquotaIcms | None:
    origem, destino = normalizar_uf(uf_origem), normalizar_uf(uf_destino)
    if not origem or not destino:
        return None
    linhas = (
        db.query(AliquotaIcms)
        .filter(
            AliquotaIcms.empresa_id == empresa_id,
            AliquotaIcms.uf_origem == origem,
            AliquotaIcms.uf_destino == destino,
            AliquotaIcms.ativo.is_(True),
        )
        .all()
    )
    if produto_id:
        especifica = next((l for l in linhas if l.produto_id == produto_id), None)
        if especifica:
            return especifica
    return next((l for l in linhas if l.produto_id is None), None)


def calcular_icms(db: Session, empresa_id: int, vendedor_id: int | None, comprador_id: int | None,
                  produto_id: int | None, valor_total: float, manual: bool,
                  percentual_digitado: float | None) -> dict:
    """Campos icms_* do contrato.

    Quem não está preenchido é a própria empresa: na compra o comprador é a
    empresa, na venda o vendedor é a empresa — então vale a UF do cadastro dela.
    """
    empresa = db.get(Empresa, empresa_id)
    uf_empresa = normalizar_uf(empresa.uf if empresa else None)
    vendedor = db.get(Parceiro, vendedor_id) if vendedor_id else None
    comprador = db.get(Parceiro, comprador_id) if comprador_id else None
    origem = normalizar_uf(vendedor.uf) if vendedor else uf_empresa
    destino = normalizar_uf(comprador.uf) if comprador else uf_empresa
    if manual:
        percentual = max(0.0, float(percentual_digitado or 0))
    else:
        linha = buscar_aliquota(db, empresa_id, origem, destino, produto_id)
        percentual = float(linha.aliquota) if linha else 0.0
    return {
        "icms_uf_origem": origem,
        "icms_uf_destino": destino,
        "icms_percentual": round(percentual, 4),
        "icms_valor": round(float(valor_total or 0) * percentual / 100 + 1e-9, 2),
        "icms_manual": bool(manual),
    }
