"""Caixa e bancos — extrato, saldos, movimentos avulsos e transferências."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from .. import contabil
from ..database import get_db
from ..deps import acesso_liberado, validar_empresa
from ..models import Banco, ContaContabil, MovimentoCaixa, Usuario
from ..schemas import MovimentoCaixaIn, TransferenciaIn
from ..utils import dinheiro, parse_data, serializar

router = APIRouter(prefix="/api/caixa", tags=["caixa"], dependencies=[Depends(acesso_liberado)])


def movimento_dict(m: MovimentoCaixa) -> dict:
    return serializar(
        m,
        extras={
            "banco_nome": m.banco.nome if m.banco else None,
            "conta_contabil_codigo": m.conta_contabil.codigo if m.conta_contabil else None,
            "conta_contabil_nome": m.conta_contabil.nome if m.conta_contabil else None,
            "centro_custo_nome": m.centro_custo.nome if m.centro_custo else None,
            "operacao_nome": m.operacao.nome if m.operacao else None,
            "parceiro_nome": m.parceiro.nome if m.parceiro else None,
        },
    )


def saldo_banco(db: Session, banco: Banco, ate: date | None = None) -> float:
    query = db.query(
        func.coalesce(
            func.sum(
                case((MovimentoCaixa.tipo == "E", MovimentoCaixa.valor), else_=-MovimentoCaixa.valor)
            ),
            0,
        )
    ).filter(MovimentoCaixa.banco_id == banco.id)
    if ate:
        query = query.filter(MovimentoCaixa.data <= ate)
    movimento = float(query.scalar() or 0)
    return round(dinheiro(banco.saldo_inicial) + movimento, 2)


@router.get("/saldos")
def saldos(
    empresa_id: int,
    ate: str | None = None,
    db: Session = Depends(get_db),
):
    data_limite = parse_data(ate)
    bancos = (
        db.query(Banco)
        .filter(Banco.empresa_id == empresa_id, Banco.ativo.is_(True))
        .order_by(Banco.nome)
        .all()
    )
    linhas = []
    for banco in bancos:
        linhas.append(
            {
                "banco_id": banco.id,
                "nome": banco.nome,
                "tipo": banco.tipo,
                "agencia": banco.agencia,
                "conta": banco.conta,
                "saldo_inicial": dinheiro(banco.saldo_inicial),
                "saldo": saldo_banco(db, banco, data_limite),
            }
        )
    return {
        "data": (data_limite or date.today()).isoformat(),
        "contas": linhas,
        "total": round(sum(l["saldo"] for l in linhas), 2),
    }


@router.get("/extrato")
def extrato(
    empresa_id: int,
    banco_id: int | None = None,
    de: str | None = None,
    ate: str | None = None,
    tipo: str | None = None,
    db: Session = Depends(get_db),
):
    inicio = parse_data(de)
    fim = parse_data(ate)

    bancos = db.query(Banco).filter(Banco.empresa_id == empresa_id)
    if banco_id:
        bancos = bancos.filter(Banco.id == banco_id)
    bancos = bancos.all()
    if not bancos:
        return {"saldo_anterior": 0, "movimentos": [], "entradas": 0, "saidas": 0, "saldo_final": 0}

    saldo_anterior = sum(dinheiro(b.saldo_inicial) for b in bancos)
    ids = [b.id for b in bancos]

    if inicio:
        anteriores = (
            db.query(
                func.coalesce(
                    func.sum(
                        case(
                            (MovimentoCaixa.tipo == "E", MovimentoCaixa.valor),
                            else_=-MovimentoCaixa.valor,
                        )
                    ),
                    0,
                )
            )
            .filter(MovimentoCaixa.banco_id.in_(ids), MovimentoCaixa.data < inicio)
            .scalar()
        )
        saldo_anterior += float(anteriores or 0)

    query = db.query(MovimentoCaixa).filter(MovimentoCaixa.banco_id.in_(ids))
    if inicio:
        query = query.filter(MovimentoCaixa.data >= inicio)
    if fim:
        query = query.filter(MovimentoCaixa.data <= fim)
    if tipo:
        query = query.filter(MovimentoCaixa.tipo == tipo)
    movimentos = query.order_by(MovimentoCaixa.data, MovimentoCaixa.id).all()

    saldo = round(saldo_anterior, 2)
    linhas = []
    entradas = saidas = 0.0
    for m in movimentos:
        valor = dinheiro(m.valor)
        if m.tipo == "E":
            saldo += valor
            entradas += valor
        else:
            saldo -= valor
            saidas += valor
        linha = movimento_dict(m)
        linha["saldo_acumulado"] = round(saldo, 2)
        linhas.append(linha)

    return {
        "saldo_anterior": round(saldo_anterior, 2),
        "movimentos": linhas,
        "entradas": round(entradas, 2),
        "saidas": round(saidas, 2),
        "saldo_final": round(saldo, 2),
    }


@router.post("/movimentos")
def criar_movimento(
    dados: MovimentoCaixaIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    validar_empresa(db, dados.empresa_id)
    if dados.tipo not in ("E", "S"):
        raise HTTPException(400, "Tipo deve ser E (entrada) ou S (saída)")
    if dinheiro(dados.valor) <= 0:
        raise HTTPException(400, "Informe um valor maior que zero")
    banco = db.get(Banco, dados.banco_id)
    if not banco or banco.empresa_id != dados.empresa_id:
        raise HTTPException(400, "Conta bancária inválida")
    conta = db.get(ContaContabil, dados.conta_contabil_id)
    if not conta or conta.empresa_id != dados.empresa_id:
        raise HTTPException(400, "Conta contábil inválida")
    if not conta.analitica:
        raise HTTPException(400, f"A conta {conta.codigo} é sintética e não aceita lançamentos.")

    mov = MovimentoCaixa(
        empresa_id=dados.empresa_id,
        banco_id=dados.banco_id,
        data=dados.data or date.today(),
        tipo=dados.tipo,
        valor=dinheiro(dados.valor),
        historico=dados.historico,
        origem="AVULSO",
        conta_contabil_id=dados.conta_contabil_id,
        centro_custo_id=dados.centro_custo_id,
        operacao_id=dados.operacao_id,
        parceiro_id=dados.parceiro_id,
        documento=dados.documento,
        usuario_id=usuario.id,
    )
    db.add(mov)
    db.flush()
    mov.origem_id = mov.id
    contabil.contabilizar_movimento_caixa(db, mov)
    db.commit()
    db.refresh(mov)
    return movimento_dict(mov)


@router.post("/transferencias")
def transferir(
    dados: TransferenciaIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    validar_empresa(db, dados.empresa_id)
    if dados.banco_origem_id == dados.banco_destino_id:
        raise HTTPException(400, "Escolha contas diferentes para a transferência")
    valor = dinheiro(dados.valor)
    if valor <= 0:
        raise HTTPException(400, "Informe um valor maior que zero")
    origem = db.get(Banco, dados.banco_origem_id)
    destino = db.get(Banco, dados.banco_destino_id)
    if not origem or not destino or origem.empresa_id != dados.empresa_id:
        raise HTTPException(400, "Conta bancária inválida")

    data_mov = dados.data or date.today()
    historico = dados.historico or f"Transferência {origem.nome} → {destino.nome}"

    saida = MovimentoCaixa(
        empresa_id=dados.empresa_id, banco_id=origem.id, data=data_mov, tipo="S", valor=valor,
        historico=historico, origem="TRANSFERENCIA",
        conta_contabil_id=contabil.conta_do_banco(db, destino), usuario_id=usuario.id,
    )
    entrada = MovimentoCaixa(
        empresa_id=dados.empresa_id, banco_id=destino.id, data=data_mov, tipo="E", valor=valor,
        historico=historico, origem="TRANSFERENCIA",
        conta_contabil_id=contabil.conta_do_banco(db, origem), usuario_id=usuario.id,
    )
    db.add_all([saida, entrada])
    db.flush()
    saida.origem_id = entrada.id
    entrada.origem_id = entrada.id
    contabil.contabilizar_movimento_caixa(
        db, entrada, conta_contrapartida_id=contabil.conta_do_banco(db, origem)
    )
    db.commit()
    return {"ok": True, "saida": movimento_dict(saida), "entrada": movimento_dict(entrada)}


@router.delete("/movimentos/{movimento_id}")
def excluir_movimento(movimento_id: int, db: Session = Depends(get_db)):
    mov = db.get(MovimentoCaixa, movimento_id)
    if not mov:
        raise HTTPException(404, "Movimento não encontrado")
    if mov.origem == "BAIXA":
        raise HTTPException(
            400,
            "Este movimento veio de uma baixa de título. Estorne a baixa em Contas a "
            "Pagar/Receber para removê-lo.",
        )
    if mov.origem == "TRANSFERENCIA":
        par = (
            db.query(MovimentoCaixa)
            .filter(
                MovimentoCaixa.origem == "TRANSFERENCIA",
                MovimentoCaixa.origem_id == mov.origem_id,
            )
            .all()
        )
        contabil.estornar(db, "CAIXA", mov.origem_id)
        for m in par:
            db.delete(m)
    else:
        contabil.estornar(db, "CAIXA", mov.id)
        db.delete(mov)
    db.commit()
    return {"ok": True}


@router.post("/movimentos/{movimento_id}/conciliar")
def conciliar(movimento_id: int, conciliado: bool = True, db: Session = Depends(get_db)):
    mov = db.get(MovimentoCaixa, movimento_id)
    if not mov:
        raise HTTPException(404, "Movimento não encontrado")
    mov.conciliado = conciliado
    db.commit()
    return movimento_dict(mov)
