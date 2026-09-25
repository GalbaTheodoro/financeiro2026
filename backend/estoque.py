"""Controle de estoque: entrada pela nota, baixa na venda e custo médio.

A ideia
-------
O estoque é a **soma dos movimentos**, não um número solto que alguém edita.
Cada entrada e cada saída vira uma linha em ``movimentos_estoque``, e o saldo
do produto é atualizado junto — no produto para a lista ser rápida, na linha
para o extrato mostrar como o estoque ficou depois de cada mexida.

Só entra no controle o produto marcado com **controla estoque**. Comissão,
frete e serviço continuam saindo em nota sem mexer em saldo nenhum.

De onde vem cada movimento
--------------------------
=============  =========================================================
Entrada        A nota de entrada, pelo botão **Gerar estoque**. É manual de
               propósito: nota de entrada chega da SEFAZ o tempo todo, e nem
               toda ela é mercadoria que a empresa guarda.
Saída          A NF-e de saída e o cupom fiscal, **sozinhos**, no momento em
               que a SEFAZ autoriza. Autorizou, saiu do estoque.
Devolução      Nota cancelada devolve o que tinha tirado (ou tirado de volta o
               que tinha posto).
Ajuste         A tela de estoque, para acerto de inventário e saldo inicial.
=============  =========================================================

O custo médio
-------------
Ponderado, que é o método que a legislação aceita e o que quase toda empresa
usa. Na **entrada**::

    novo_custo = (saldo x custo_medio + quantidade x custo_da_entrada)
                 / (saldo + quantidade)

Na **saída** o custo que sai é o custo médio do momento — o custo médio em si
não muda. É isso que faz o relatório responder "quanto vale o que está parado".

O custo da entrada é o valor do item na nota: ``valor_total - desconto +
frete``. Não entram IPI nem ST, que nem sempre compõem custo e dependem do
regime da empresa — quem precisar desse detalhe ajusta pela tela.

A unidade
---------
O saldo é contado na unidade do **primeiro movimento** do produto. Um
movimento em outra unidade é **recusado**, com a frase dizendo o que fazer:
somar saca com quilo estraga o estoque em silêncio, e estoque errado é pior
que estoque nenhum.

Falta de saldo
--------------
A venda é **barrada** antes de ir para a SEFAZ (``conferir_venda``), porque a
nota autorizada não volta atrás. A mensagem diz o produto, quanto tem e quanto
a nota quer.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from .models import MovimentoEstoque, Nota, NotaItem, Produto
from .utils import dinheiro

# Origens possíveis de um movimento (ver o docstring do modelo).
ORIGENS = ("NOTA", "SAIDA", "CUPOM", "AJUSTE", "SALDO_INICIAL", "ESTORNO")

# quantidade menor que isto é zero: evita saldo "0,00001" por arredondamento
MIGALHA = 0.0001


def _q(valor) -> float:
    """Quantidade com 4 casas — é a precisão da coluna."""
    return round(float(valor or 0) + 1e-9, 4)


def _c(valor) -> float:
    """Custo unitário com 6 casas."""
    return round(float(valor or 0) + 1e-12, 6)


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #
def controla(produto: Produto | None) -> bool:
    return bool(produto is not None and produto.controla_estoque)


def saldo(produto: Produto | None) -> float:
    return _q(produto.estoque_atual) if produto is not None else 0.0


def valor_em_estoque(produto: Produto) -> float:
    return dinheiro(_q(produto.estoque_atual) * _c(produto.custo_medio))


def unidade_do_saldo(produto: Produto) -> str:
    """Em que unidade o saldo é contado."""
    return (produto.estoque_unidade or produto.unidade_comercial or "").strip().upper()


def _normalizar_unidade(texto: str | None) -> str:
    return (texto or "").strip().upper()[:10]


class ErroEstoque(Exception):
    """Algo impede o movimento, com a frase pronta para a tela."""


def conferir_unidade(produto: Produto, unidade: str) -> str:
    """Devolve a unidade do movimento, ou explode explicando a diferença."""
    unidade = _normalizar_unidade(unidade) or unidade_do_saldo(produto)
    atual = unidade_do_saldo(produto)
    if atual and unidade and unidade != atual:
        raise ErroEstoque(
            f"O estoque de {produto.nome} é contado em {atual} e este movimento está em "
            f"{unidade}. Somar as duas coisas estragaria o saldo — acerte a unidade do "
            "item da nota ou do cadastro do produto."
        )
    return unidade or atual


# --------------------------------------------------------------------------- #
# O movimento
# --------------------------------------------------------------------------- #
def registrar(
    db: Session,
    produto: Produto,
    tipo: str,
    quantidade: float,
    *,
    custo_unitario: float = 0,
    unidade: str = "",
    origem: str = "AJUSTE",
    data_movimento: date | None = None,
    nota: Nota | None = None,
    nota_item_id: int | None = None,
    documento: str = "",
    parceiro_id: int | None = None,
    historico: str = "",
    usuario_id: int | None = None,
) -> MovimentoEstoque:
    """Aplica um movimento e devolve a linha gravada.

    É o **único** lugar que mexe em `estoque_atual` e `custo_medio`: quem
    precisar mover estoque chama daqui, para o custo médio nunca sair errado.
    """
    quantidade = _q(quantidade)
    if quantidade <= 0:
        raise ErroEstoque("A quantidade do movimento tem de ser maior que zero.")
    if tipo not in ("E", "S"):
        raise ErroEstoque("O movimento é de entrada (E) ou de saída (S).")

    unidade = conferir_unidade(produto, unidade)
    anterior = _q(produto.estoque_atual)
    medio = _c(produto.custo_medio)

    if tipo == "E":
        custo_unitario = _c(custo_unitario)
        novo_saldo = _q(anterior + quantidade)
        # média ponderada; saldo negativo não entra na conta, senão o custo
        # médio sai invertido
        base = max(anterior, 0.0)
        if novo_saldo > MIGALHA:
            medio = _c((base * medio + quantidade * custo_unitario) / (base + quantidade))
        else:
            medio = custo_unitario
        custo_total = dinheiro(quantidade * custo_unitario)
    else:
        # na saída o custo que sai é o custo médio do momento
        custo_unitario = medio
        novo_saldo = _q(anterior - quantidade)
        custo_total = dinheiro(quantidade * custo_unitario)

    if abs(novo_saldo) < MIGALHA:
        novo_saldo = 0.0

    movimento = MovimentoEstoque(
        empresa_id=produto.empresa_id,
        produto_id=produto.id,
        data=data_movimento or date.today(),
        tipo=tipo,
        quantidade=quantidade,
        unidade=unidade or None,
        custo_unitario=custo_unitario,
        custo_total=custo_total,
        saldo=novo_saldo,
        custo_medio=medio,
        origem=origem if origem in ORIGENS else "AJUSTE",
        nota_id=nota.id if nota is not None else None,
        nota_item_id=nota_item_id,
        documento=(documento or "")[:40] or None,
        parceiro_id=parceiro_id,
        historico=(historico or "")[:200] or None,
        usuario_id=usuario_id,
    )
    db.add(movimento)

    produto.estoque_atual = novo_saldo
    produto.custo_medio = medio
    produto.estoque_unidade = unidade or produto.estoque_unidade
    produto.estoque_atualizado_em = datetime.utcnow()
    db.flush()
    return movimento


# --------------------------------------------------------------------------- #
# A nota
# --------------------------------------------------------------------------- #
def custo_do_item(item: NotaItem) -> float:
    """O que a mercadoria custou nesta linha: valor do item, menos desconto, mais frete."""
    return dinheiro(float(item.valor_total or 0) - float(item.desconto or 0)
                    + float(item.frete or 0))


def itens_com_estoque(db: Session, nota: Nota) -> list[tuple[NotaItem, Produto]]:
    """Os itens da nota que mexem no estoque, já com o produto do cadastro."""
    saida = []
    for item in nota.itens:
        if not item.produto_id:
            continue
        produto = db.get(Produto, item.produto_id)
        if controla(produto) and _q(item.quantidade) > 0:
            saida.append((item, produto))
    return saida


def _documento(nota: Nota) -> str:
    numero = (nota.numero or "").strip()
    serie = (nota.serie or "").strip()
    if numero and serie:
        return f"{numero}/{serie}"
    return numero or (nota.chave or "")[-9:]


def conferir_venda(db: Session, nota: Nota) -> list[str]:
    """O que impede a nota de sair, por causa de estoque. Lista vazia = pode ir.

    Rodado **antes** de transmitir: a nota autorizada não volta atrás, então é
    aqui que a falta de saldo tem de aparecer.
    """
    problemas: list[str] = []
    # quanto cada produto sai nesta nota (o mesmo produto pode vir em duas linhas)
    pedido: dict[int, float] = {}
    for item, produto in itens_com_estoque(db, nota):
        try:
            conferir_unidade(produto, item.unidade)
        except ErroEstoque as erro:
            problemas.append(str(erro))
            continue
        pedido[produto.id] = _q(pedido.get(produto.id, 0) + _q(item.quantidade))

    for produto_id, quantidade in pedido.items():
        produto = db.get(Produto, produto_id)
        disponivel = saldo(produto)
        if quantidade - disponivel > MIGALHA:
            unidade = unidade_do_saldo(produto) or ""
            problemas.append(
                f"{produto.nome}: a nota tira {_texto(quantidade)} {unidade} e o estoque tem "
                f"{_texto(disponivel)} {unidade}. Lance a entrada da mercadoria ou acerte o "
                "saldo em Movimento > Estoque.".replace("  ", " ").strip()
            )
    return problemas


def _texto(valor: float) -> str:
    """Quantidade sem casas inúteis: 12 em vez de 12,0000."""
    valor = _q(valor)
    if abs(valor - round(valor)) < MIGALHA:
        return str(int(round(valor)))
    return f"{valor:.4f}".rstrip("0").rstrip(".").replace(".", ",")


def entrada_da_nota(db: Session, nota: Nota, usuario_id: int | None = None) -> dict:
    """Põe no estoque a mercadoria da nota de entrada. É o botão da tela."""
    if nota.estoque_em:
        raise ErroEstoque(
            "O estoque desta nota já foi gerado. Para refazer, estorne primeiro.")
    linhas = itens_com_estoque(db, nota)
    if not linhas:
        raise ErroEstoque(
            "Nenhum item desta nota está ligado a um produto que controla estoque. "
            "Importe a nota (para ligar os itens ao cadastro) e marque "
            "\"controla estoque\" no produto."
        )
    documento = _documento(nota)
    data_nota = nota.data_emissao.date() if nota.data_emissao else date.today()
    movidos = []
    for item, produto in linhas:
        quantidade = _q(item.quantidade)
        custo = custo_do_item(item)
        registrar(
            db, produto, "E", quantidade,
            custo_unitario=custo / quantidade if quantidade else 0,
            unidade=item.unidade, origem="NOTA", data_movimento=data_nota,
            nota=nota, nota_item_id=item.id, documento=documento,
            parceiro_id=nota.parceiro_id,
            historico=f"Entrada pela nota {documento}"[:200],
            usuario_id=usuario_id,
        )
        movidos.append({"produto": produto.nome, "quantidade": quantidade,
                        "unidade": unidade_do_saldo(produto),
                        "saldo": saldo(produto),
                        "custo_medio": _c(produto.custo_medio)})
    nota.estoque_em = datetime.utcnow()
    nota.estoque_por_id = usuario_id
    db.flush()
    return {"movimentos": movidos,
            "mensagem": f"{len(movidos)} produto(s) entraram no estoque."}


def saida_da_nota(db: Session, nota: Nota, usuario_id: int | None = None) -> dict:
    """Baixa o estoque da nota de saída ou do cupom. Chamado pela autorização.

    Não levanta erro: a nota já está autorizada na SEFAZ, e travar aqui não
    desfaz nada. O que não puder ser baixado volta como aviso.
    """
    if nota.estoque_em:
        return {"movimentos": [], "aviso": ""}
    origem = "CUPOM" if (nota.modelo or "") == "65" else "SAIDA"
    documento = _documento(nota)
    data_nota = nota.data_emissao.date() if nota.data_emissao else date.today()
    movidos, avisos = [], []
    for item, produto in itens_com_estoque(db, nota):
        try:
            registrar(
                db, produto, "S", _q(item.quantidade), unidade=item.unidade,
                origem=origem, data_movimento=data_nota, nota=nota,
                nota_item_id=item.id, documento=documento,
                parceiro_id=nota.parceiro_id,
                historico=f"Saída pela nota {documento}"[:200],
                usuario_id=usuario_id,
            )
            movidos.append({"produto": produto.nome, "quantidade": _q(item.quantidade),
                            "unidade": unidade_do_saldo(produto),
                            "saldo": saldo(produto)})
        except ErroEstoque as erro:
            avisos.append(str(erro))
    if movidos:
        nota.estoque_em = datetime.utcnow()
        nota.estoque_por_id = usuario_id
    db.flush()
    return {"movimentos": movidos, "aviso": " ".join(avisos)}


def estornar_nota(db: Session, nota: Nota, usuario_id: int | None = None,
                  motivo: str = "") -> dict:
    """Desfaz o que a nota fez no estoque, com movimentos de sentido contrário.

    Não apaga nada: quem apaga movimento apaga a história. O estorno é uma linha
    nova, e o extrato mostra as duas.
    """
    if not nota.estoque_em:
        raise ErroEstoque("Esta nota não mexeu no estoque.")
    originais = (
        db.query(MovimentoEstoque)
        .filter(MovimentoEstoque.nota_id == nota.id,
                MovimentoEstoque.origem != "ESTORNO")
        .order_by(MovimentoEstoque.id)
        .all()
    )
    ja_estornados = {
        m.nota_item_id for m in db.query(MovimentoEstoque)
        .filter(MovimentoEstoque.nota_id == nota.id,
                MovimentoEstoque.origem == "ESTORNO").all()
    }
    documento = _documento(nota)
    desfeitos = []
    for movimento in originais:
        if movimento.nota_item_id in ja_estornados:
            continue
        produto = db.get(Produto, movimento.produto_id)
        if produto is None:
            continue
        contrario = "S" if movimento.tipo == "E" else "E"
        registrar(
            db, produto, contrario, _q(movimento.quantidade),
            custo_unitario=_c(movimento.custo_unitario),
            unidade=movimento.unidade or "", origem="ESTORNO",
            nota=nota, nota_item_id=movimento.nota_item_id, documento=documento,
            parceiro_id=nota.parceiro_id,
            historico=(motivo or f"Estorno do estoque da nota {documento}")[:200],
            usuario_id=usuario_id,
        )
        desfeitos.append({"produto": produto.nome, "quantidade": _q(movimento.quantidade),
                          "saldo": saldo(produto)})
    nota.estoque_em = None
    nota.estoque_por_id = None
    db.flush()
    return {"movimentos": desfeitos,
            "mensagem": f"{len(desfeitos)} movimento(s) estornado(s)."}


# --------------------------------------------------------------------------- #
# Consultas para a tela
# --------------------------------------------------------------------------- #
def ficha_produto(produto: Produto) -> dict:
    disponivel = saldo(produto)
    minimo = _q(produto.estoque_minimo)
    return {
        "produto_id": produto.id,
        "codigo": produto.codigo,
        "nome": produto.nome,
        "unidade": unidade_do_saldo(produto),
        "saldo": disponivel,
        "custo_medio": _c(produto.custo_medio),
        "valor": valor_em_estoque(produto),
        "minimo": minimo,
        "negativo": disponivel < -MIGALHA,
        "abaixo_do_minimo": bool(minimo > 0 and disponivel < minimo),
        "atualizado_em": (produto.estoque_atualizado_em.isoformat(timespec="seconds")
                          if produto.estoque_atualizado_em else None),
        "ativo": produto.ativo,
    }


def posicao(db: Session, empresa_id: int, busca: str = "",
            apenas_com_saldo: bool = False) -> dict:
    """A posição de estoque: um produto por linha, com saldo e valor."""
    consulta = db.query(Produto).filter(
        Produto.empresa_id == empresa_id,
        Produto.controla_estoque.is_(True),
    )
    if busca:
        alvo = f"%{busca.strip()}%"
        consulta = consulta.filter(Produto.nome.ilike(alvo) | Produto.codigo.ilike(alvo))
    fichas = [ficha_produto(p) for p in consulta.order_by(Produto.nome).all()]
    if apenas_com_saldo:
        fichas = [f for f in fichas if abs(f["saldo"]) > MIGALHA]
    return {
        "produtos": fichas,
        "resumo": {
            "produtos": len(fichas),
            "valor_total": dinheiro(sum(f["valor"] for f in fichas)),
            "negativos": sum(1 for f in fichas if f["negativo"]),
            "abaixo_do_minimo": sum(1 for f in fichas if f["abaixo_do_minimo"]),
            "sem_saldo": sum(1 for f in fichas if abs(f["saldo"]) <= MIGALHA),
        },
    }
