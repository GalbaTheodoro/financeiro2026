"""Cupons de desconto da assinatura.

Não confundir com o **cupom fiscal** (NFC-e, em ``backend/cupom.py``): aqui é o
desconto de venda, o "PRIMAVERA10" que o cliente digita e paga menos.

Como funciona
-------------
O administrador do site cadastra um código e uma porcentagem, e liga ou desliga
o cupom quando quiser — sem validade e sem limite de uso, foi assim que ficou
combinado. Quem digita um cupom válido fica com ele **guardado na assinatura**,
junto com a porcentagem copiada:

* copiar a porcentagem é de propósito. Se depois o administrador mudar o
  PRIMAVERA10 de 10% para 5%, quem já aplicou continua pagando com os 10% que
  foram combinados na hora;
* o desconto vale na **primeira cobrança**. Quando o administrador confirma o
  Pix, ``consumir`` tira o cupom da assinatura e guarda no histórico quanto ele
  abateu. A renovação volta ao preço cheio;
* pacote de usuários extra **não** recebe desconto: o cupom é do plano.

Uma conta pode trocar de cupom antes de pagar — vale o último digitado.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .models import Assinatura, CupomDesconto
from .utils import dinheiro

# um código curto e sem espaço é o que cabe num cartaz e no WhatsApp
TAMANHO_MAXIMO = 30


class CupomInvalido(Exception):
    """O código não existe ou está desligado. A frase já é a que vai para a tela."""


def normalizar(codigo: str | None) -> str:
    """"  primavera 10 " vira "PRIMAVERA10": é assim que ele é guardado e buscado."""
    return "".join((codigo or "").split()).upper()[:TAMANHO_MAXIMO]


def percentual_valido(valor) -> float:
    """Aceita 10, "10", "10,5". Fora de 0 a 100 é recusado."""
    try:
        numero = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        raise CupomInvalido("Informe a porcentagem de desconto do cupom.") from None
    if numero <= 0 or numero > 100:
        raise CupomInvalido("A porcentagem do cupom tem de ficar entre 0 e 100.")
    return round(numero, 2)


def buscar(db: Session, codigo: str | None) -> CupomDesconto | None:
    limpo = normalizar(codigo)
    if not limpo:
        return None
    return db.query(CupomDesconto).filter(CupomDesconto.codigo == limpo).first()


def validar(db: Session, codigo: str | None) -> CupomDesconto:
    """Devolve o cupom ou levanta ``CupomInvalido`` com a frase para a tela.

    A frase é a mesma para código errado e para cupom desligado de propósito:
    quem está do lado de fora não precisa saber que o cupom existe e acabou.
    """
    cupom = buscar(db, codigo)
    if cupom is None or not cupom.ativo:
        raise CupomInvalido("Cupom não encontrado ou não está mais valendo.")
    return cupom


def calcular(valor: float, percentual: float | None) -> tuple[float, float]:
    """(desconto, a pagar) — arredondado em centavos, nunca negativo."""
    if not percentual:
        return 0.0, dinheiro(valor)
    desconto = dinheiro(float(valor) * float(percentual) / 100)
    return desconto, dinheiro(max(float(valor) - desconto, 0))


def aplicar(db: Session, assinatura: Assinatura, codigo: str | None) -> CupomDesconto:
    """Gruda o cupom na conta. Não cobra nada: só muda o valor que vai ser cobrado."""
    cupom = validar(db, codigo)
    assinatura.cupom_codigo = cupom.codigo
    assinatura.cupom_percentual = float(cupom.percentual or 0)
    assinatura.cupom_aplicado_em = datetime.utcnow()
    db.flush()
    return cupom


def remover(assinatura: Assinatura) -> None:
    assinatura.cupom_codigo = None
    assinatura.cupom_percentual = None
    assinatura.cupom_aplicado_em = None


def desconto_da_assinatura(assinatura: Assinatura | None, valor: float) -> dict:
    """O que a tela de pagamento mostra: de quanto era, quanto abate, quanto fica."""
    percentual = float(assinatura.cupom_percentual or 0) if assinatura else 0.0
    desconto, pagar = calcular(valor, percentual)
    return {
        "codigo": (assinatura.cupom_codigo if assinatura else None) if desconto else None,
        "percentual": percentual if desconto else 0.0,
        "valor_cheio": dinheiro(valor),
        "desconto": desconto,
        "valor_pagar": pagar,
    }


def consumir(db: Session, assinatura: Assinatura, valor_cheio: float) -> float:
    """Gasta o cupom na confirmação do Pix e devolve quanto ele abateu.

    Chamado uma vez, quando o administrador confirma o recebimento. Depois disso
    a conta não tem mais cupom: a renovação é pelo preço cheio.
    """
    if not assinatura.cupom_codigo or not assinatura.cupom_percentual:
        return 0.0
    desconto, _pagar = calcular(valor_cheio, float(assinatura.cupom_percentual))
    cupom = buscar(db, assinatura.cupom_codigo)
    if cupom is not None:
        cupom.usos = int(cupom.usos or 0) + 1
    assinatura.cupom_usado_codigo = assinatura.cupom_codigo
    assinatura.cupom_usado_desconto = desconto
    assinatura.cupom_usado_em = datetime.utcnow()
    remover(assinatura)
    db.flush()
    return desconto


def serializar(cupom: CupomDesconto) -> dict:
    return {
        "id": cupom.id,
        "codigo": cupom.codigo,
        "descricao": cupom.descricao or "",
        "percentual": float(cupom.percentual or 0),
        "ativo": bool(cupom.ativo),
        "usos": int(cupom.usos or 0),
        "criado_em": cupom.criado_em.isoformat(timespec="seconds") if cupom.criado_em else None,
    }


def listar(db: Session) -> list[dict]:
    cupons = db.query(CupomDesconto).order_by(CupomDesconto.ativo.desc(),
                                              CupomDesconto.codigo).all()
    return [serializar(c) for c in cupons]


def criar(db: Session, codigo: str, percentual, descricao: str | None,
          ativo: bool = True) -> CupomDesconto:
    limpo = normalizar(codigo)
    if not limpo:
        raise CupomInvalido("Dê um código ao cupom (ex.: PRIMAVERA10).")
    if buscar(db, limpo) is not None:
        raise CupomInvalido(f"Já existe um cupom com o código {limpo}.")
    cupom = CupomDesconto(
        codigo=limpo,
        percentual=percentual_valido(percentual),
        descricao=(descricao or "").strip()[:120] or None,
        ativo=bool(ativo),
    )
    db.add(cupom)
    db.flush()
    return cupom


def editar(db: Session, cupom: CupomDesconto, codigo: str | None, percentual,
           descricao: str | None, ativo) -> CupomDesconto:
    if codigo is not None:
        limpo = normalizar(codigo)
        if not limpo:
            raise CupomInvalido("Dê um código ao cupom (ex.: PRIMAVERA10).")
        existente = buscar(db, limpo)
        if existente is not None and existente.id != cupom.id:
            raise CupomInvalido(f"Já existe um cupom com o código {limpo}.")
        cupom.codigo = limpo
    if percentual is not None:
        cupom.percentual = percentual_valido(percentual)
    if descricao is not None:
        cupom.descricao = (descricao or "").strip()[:120] or None
    if ativo is not None:
        cupom.ativo = bool(ativo)
    db.flush()
    return cupom
