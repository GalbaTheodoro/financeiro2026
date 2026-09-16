"""Funções auxiliares de serialização e datas."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import inspect


def _valor(v):
    if isinstance(v, (datetime,)):
        return v.isoformat(timespec="seconds")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def serializar(obj, extras: dict | None = None, exclude: set | None = None) -> dict:
    """Converte um objeto do SQLAlchemy num dicionário pronto para JSON."""
    if obj is None:
        return None
    exclude = exclude or set()
    dados = {}
    for coluna in inspect(obj).mapper.column_attrs:
        if coluna.key in exclude:
            continue
        dados[coluna.key] = _valor(getattr(obj, coluna.key))
    if extras:
        dados.update({k: _valor(v) for k, v in extras.items()})
    return dados


def serializar_lista(objs, **kw) -> list:
    return [serializar(o, **kw) for o in objs]


def parse_data(valor, padrao=None):
    """Aceita 'YYYY-MM-DD', date ou None."""
    if valor in (None, "", "null"):
        return padrao
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    return date.fromisoformat(str(valor)[:10])


def dinheiro(v) -> float:
    return round(float(v or 0) + 1e-9, 2)


def somar(valores) -> float:
    return round(sum(float(v or 0) for v in valores) + 1e-9, 2)


def adicionar_meses(d: date, meses: int) -> date:
    """Soma meses preservando o fim de mês quando possível."""
    ano = d.year + (d.month - 1 + meses) // 12
    mes = (d.month - 1 + meses) % 12 + 1
    dias_mes = [31, 29 if (ano % 4 == 0 and ano % 100 != 0) or ano % 400 == 0 else 28,
                31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes - 1]
    return date(ano, mes, min(d.day, dias_mes))


def endereco_linha(obj) -> str:
    """Endereço em uma linha só: 'Rua X, 250 - Sala 2, Centro, Campinas/SP - CEP 13010-100'."""
    if obj is None:
        return ""
    rua = " ".join(x for x in [getattr(obj, "logradouro", None) or "",
                               getattr(obj, "numero", None) or ""] if x).strip()
    if rua and getattr(obj, "numero", None):
        rua = f"{obj.logradouro}, {obj.numero}"
    partes = [rua, getattr(obj, "complemento", None), getattr(obj, "bairro", None)]
    cidade = getattr(obj, "cidade", None)
    uf = getattr(obj, "uf", None)
    if cidade:
        partes.append(f"{cidade}/{uf}" if uf else cidade)
    elif uf:
        partes.append(uf)
    texto = " - ".join(x for x in partes if x)
    cep = getattr(obj, "cep", None)
    return f"{texto} - CEP {cep}" if cep and texto else (texto or (f"CEP {cep}" if cep else ""))


def moeda_br(valor) -> str:
    """Formata um número no padrão brasileiro: R$ 1.234,56."""
    return f"R$ {float(valor or 0):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
