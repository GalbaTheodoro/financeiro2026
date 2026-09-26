"""Orçamento e pedido de venda — a tela de balcão e a finalização.

O caminho inteiro
-----------------
1. a pessoa monta o carrinho na tela de venda e grava: nasce um **orçamento** ou
   um **pedido**, com número, que dá para reabrir, imprimir e editar;
2. o orçamento aprovado vira pedido (mesmo número: o cliente continua falando do
   mesmo papel);
3. **Finalizar** abre a segunda tela: à vista ou a prazo, quantas parcelas, e que
   documento fiscal sai — nota (55) ou cupom (65).

A finalização **não reimplementa** emissão nem financeiro. Ela monta a entrada
das rotas que já existem e as chama: `criar_rascunho` + `transmitir` para a NF-e,
`/cupom/venda` para o cupom, e o `faturar` de sempre para virar conta a receber.
O pedido guarda o id da nota e do título, que é o rastro de onde ele foi parar.

Se a SEFAZ recusar, **o pedido não se perde**: ele continua ABERTO, com a
mensagem do erro, e dá para corrigir e finalizar de novo. Perder uma venda
montada porque o certificado venceu seria o pior jeito de descobrir isso.
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import pedidos as regras
from ..database import get_db
from ..deps import acesso_liberado, exigir_modulo, validar_empresa
from ..models import Lancamento, Nota, Parceiro, Pedido, PedidoItem, Produto, Usuario
from ..schemas import FinalizarPedidoIn, PedidoIn
from ..utils import dinheiro

# O pedido é a porta da venda: quem tem emissão de NF-e tem o pedido.
# O menu deste módulo pode ser tirado de um plano (ou de um cliente) na área do
# administrador — quem fecha a porta de verdade é a dependência abaixo.
router = APIRouter(prefix="/api/pedidos", tags=["pedidos"],
                   dependencies=[Depends(exigir_modulo("NFE"))])


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #
def _pedido(db: Session, pedido_id: int, usuario: Usuario) -> Pedido:
    pedido = db.get(Pedido, pedido_id)
    if not pedido:
        raise HTTPException(404, "Pedido não encontrado.")
    validar_empresa(db, pedido.empresa_id, usuario)
    return pedido


@router.get("")
def listar(empresa_id: int, tipo: str | None = None, situacao: str | None = None,
           busca: str | None = None, falta_documento: bool = False,
           db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    consulta = db.query(Pedido).filter(Pedido.empresa_id == empresa_id)
    if tipo:
        consulta = consulta.filter(Pedido.tipo == tipo)
    if situacao:
        consulta = consulta.filter(Pedido.situacao == situacao)
    if busca:
        alvo = f"%{busca.strip()}%"
        consulta = consulta.filter(
            Pedido.numero.ilike(alvo) | Pedido.cliente_nome.ilike(alvo))
    if falta_documento:
        consulta = consulta.filter(Pedido.situacao == "FINALIZADO", Pedido.nota_id.is_(None))
    linhas = consulta.order_by(Pedido.id.desc()).limit(300).all()
    abertos = [p for p in linhas if p.situacao == "ABERTO"]
    # a venda fechada sem nota é a que não pode ser esquecida: conta separado
    sem_documento = [p for p in linhas if regras.falta_documento(p)]
    return {
        "linhas": [regras.resumo(p) for p in linhas],
        "resumo": {
            "abertos": len(abertos),
            "valor_aberto": dinheiro(sum(float(p.valor_total or 0) for p in abertos)),
            "finalizados": sum(1 for p in linhas if p.situacao == "FINALIZADO"),
            "sem_documento": len(sem_documento),
            "valor_sem_documento": dinheiro(
                sum(float(p.valor_total or 0) for p in sem_documento)),
        },
        "tipos": regras.TIPOS,
        "situacoes": regras.SITUACOES,
    }


@router.get("/{pedido_id}")
def abrir(pedido_id: int, db: Session = Depends(get_db),
          usuario: Usuario = Depends(acesso_liberado)):
    return {"pedido": regras.ficha(db, _pedido(db, pedido_id, usuario))}


@router.get("/{pedido_id}/impressao")
def dados_impressao(pedido_id: int, db: Session = Depends(get_db),
                    usuario: Usuario = Depends(acesso_liberado)):
    """Tudo o que a folha do pedido precisa, num pacote só.

    As parcelas saem do **título**, quando o pedido já virou venda a prazo — e
    não de uma nova conta. O papel que o cliente leva tem de dizer os mesmos
    vencimentos que estão em Contas a Receber; refazer a conta aqui abriria a
    porta para os dois discordarem.
    """
    from datetime import datetime as agora

    from ..models import Empresa
    from ..utils import endereco_linha, serializar

    pedido = _pedido(db, pedido_id, usuario)
    empresa = db.get(Empresa, pedido.empresa_id)

    parcelas = []
    if pedido.lancamento_id:
        titulo = db.get(Lancamento, pedido.lancamento_id)
        parcelas = [
            {"numero": p.numero or str(i + 1).zfill(3),
             "vencimento": p.data_vencimento.isoformat() if p.data_vencimento else None,
             "valor": float(p.valor or 0)}
            for i, p in enumerate(sorted(titulo.parcelas, key=lambda x: x.data_vencimento))
        ] if titulo else []
    elif pedido.condicao == "PRAZO" and pedido.primeiro_vencimento:
        parcelas = [{**p, "vencimento": p["vencimento"].isoformat()}
                    for p in regras.montar_parcelas(
                        float(pedido.valor_total or 0), int(pedido.parcelas or 1),
                        pedido.primeiro_vencimento, int(pedido.intervalo_dias or 30))]

    cliente = None
    if pedido.parceiro is not None:
        cliente = dict(serializar(pedido.parceiro, exclude={"observacao"}),
                       endereco=endereco_linha(pedido.parceiro))
    elif pedido.cliente_nome:
        cliente = {"nome": pedido.cliente_nome, "cpf_cnpj": pedido.cliente_documento or "",
                   "endereco": ""}

    return {
        "pedido": regras.ficha(db, pedido),
        "empresa": dict(serializar(empresa), endereco=endereco_linha(empresa)),
        "cliente": cliente,
        "parcelas": parcelas,
        "emitido_em": agora.now().isoformat(timespec="minutes"),
    }


# --------------------------------------------------------------------------- #
# Gravar
# --------------------------------------------------------------------------- #
def _aplicar(db: Session, pedido: Pedido, dados: PedidoIn) -> Pedido:
    if dados.tipo not in regras.TIPOS:
        raise HTTPException(400, "O documento é orçamento ou pedido.")
    if dados.parceiro_id:
        parceiro = db.get(Parceiro, dados.parceiro_id)
        if not parceiro or parceiro.empresa_id != pedido.empresa_id:
            raise HTTPException(400, "Este cliente não é desta empresa.")
    pedido.tipo = dados.tipo
    pedido.data = dados.data or date.today()
    pedido.validade = dados.validade
    pedido.parceiro_id = dados.parceiro_id
    pedido.cliente_nome = (dados.cliente_nome or "").strip()[:160] or None
    pedido.cliente_documento = (dados.cliente_documento or "").strip()[:20] or None
    pedido.observacao = (dados.observacao or "").strip()[:300] or None
    pedido.desconto = max(0.0, float(dados.desconto or 0))

    pedido.itens.clear()
    db.flush()
    for entrada in dados.itens or []:
        produto = db.get(Produto, entrada.produto_id) if entrada.produto_id else None
        if produto is not None and produto.empresa_id != pedido.empresa_id:
            raise HTTPException(400, "Um dos produtos não é desta empresa.")
        descricao = (entrada.descricao or (produto.nome if produto else "")).strip()
        if not descricao:
            raise HTTPException(400, "Todo item precisa de uma descrição.")
        if float(entrada.quantidade or 0) <= 0:
            raise HTTPException(400, f"A quantidade de {descricao} tem de ser maior que zero.")
        pedido.itens.append(PedidoItem(
            produto_id=produto.id if produto else None,
            descricao=descricao[:200],
            unidade=(entrada.unidade or (produto.unidade_comercial if produto else "") or "UN")[:10],
            quantidade=float(entrada.quantidade or 0),
            valor_unitario=float(entrada.valor_unitario or 0),
            desconto=max(0.0, float(entrada.desconto or 0)),
        ))
    if not pedido.itens:
        raise HTTPException(400, "O pedido está sem itens — nada foi vendido.")
    regras.recalcular(pedido)
    return pedido


@router.post("")
def criar(dados: PedidoIn, db: Session = Depends(get_db),
          usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, dados.empresa_id, usuario)
    pedido = Pedido(empresa_id=dados.empresa_id,
                    numero=regras.proximo_numero(db, dados.empresa_id),
                    criado_por_id=usuario.id)
    db.add(pedido)
    db.flush()
    _aplicar(db, pedido, dados)
    db.commit()
    db.refresh(pedido)
    return {"ok": True, "pedido": regras.ficha(db, pedido),
            "mensagem": f"{regras.TIPOS[pedido.tipo]} nº {pedido.numero} gravado."}


@router.put("/{pedido_id}")
def salvar(pedido_id: int, dados: PedidoIn, db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    pedido = _pedido(db, pedido_id, usuario)
    if pedido.situacao != "ABERTO":
        raise HTTPException(
            400, f"Este pedido está {regras.SITUACOES[pedido.situacao].lower()} — "
                 "não dá mais para mexer nele.")
    dados.empresa_id = pedido.empresa_id
    _aplicar(db, pedido, dados)
    db.commit()
    db.refresh(pedido)
    return {"ok": True, "pedido": regras.ficha(db, pedido), "mensagem": "Pedido gravado."}


@router.post("/{pedido_id}/aprovar")
def aprovar(pedido_id: int, db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    """Orçamento aprovado pelo cliente vira pedido, com o mesmo número."""
    pedido = _pedido(db, pedido_id, usuario)
    if pedido.tipo != "ORCAMENTO":
        raise HTTPException(400, "Isto já é um pedido.")
    if pedido.situacao != "ABERTO":
        raise HTTPException(400, "Só orçamento aberto vira pedido.")
    pedido.tipo = "PEDIDO"
    db.commit()
    return {"ok": True, "pedido": regras.ficha(db, pedido),
            "mensagem": f"Orçamento nº {pedido.numero} aprovado: virou pedido."}


@router.post("/{pedido_id}/cancelar")
def cancelar(pedido_id: int, db: Session = Depends(get_db),
             usuario: Usuario = Depends(acesso_liberado)):
    pedido = _pedido(db, pedido_id, usuario)
    if pedido.situacao == "FINALIZADO":
        raise HTTPException(
            400, "Este pedido já virou venda. Cancele a nota e o título, não o pedido.")
    pedido.situacao = "CANCELADO"
    db.commit()
    return {"ok": True, "pedido": regras.ficha(db, pedido), "mensagem": "Pedido cancelado."}


@router.delete("/{pedido_id}")
def excluir(pedido_id: int, db: Session = Depends(get_db),
            usuario: Usuario = Depends(acesso_liberado)):
    pedido = _pedido(db, pedido_id, usuario)
    if pedido.situacao == "FINALIZADO":
        raise HTTPException(400, "Pedido finalizado não se apaga — ele virou venda.")
    db.delete(pedido)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Finalizar
# --------------------------------------------------------------------------- #
@router.post("/{pedido_id}/parcelas")
def simular_parcelas(pedido_id: int, dados: FinalizarPedidoIn,
                     db: Session = Depends(get_db),
                     usuario: Usuario = Depends(acesso_liberado)):
    """As parcelas antes de confirmar — a conta mora no servidor, não na tela.

    Assim o que a pessoa vê na tela é exatamente o que vai virar duplicata e
    conta a receber, inclusive o centavo da sobra.
    """
    pedido = _pedido(db, pedido_id, usuario)
    try:
        parcelas = regras.montar_parcelas(
            float(pedido.valor_total or 0), dados.parcelas,
            dados.primeiro_vencimento or date.today(), dados.intervalo_dias)
    except regras.ErroPedido as erro:
        raise HTTPException(400, str(erro)) from None
    return {
        "parcelas": [{**p, "vencimento": p["vencimento"].isoformat()} for p in parcelas],
        "total": dinheiro(sum(p["valor"] for p in parcelas)),
    }


def _conferir_finalizacao(pedido: Pedido, dados: FinalizarPedidoIn) -> None:
    if pedido.situacao != "ABERTO":
        raise HTTPException(400, "Este pedido já foi finalizado ou cancelado.")
    if pedido.tipo == "ORCAMENTO":
        raise HTTPException(
            400, "Orçamento não vira venda direto. Aprove primeiro — o botão Aprovar "
                 "transforma em pedido, com o mesmo número.")
    if not pedido.itens:
        raise HTTPException(400, "O pedido está sem itens.")
    if float(pedido.valor_total or 0) <= 0:
        raise HTTPException(400, "O pedido está zerado.")
    if dados.condicao not in regras.CONDICOES:
        raise HTTPException(400, "A condição é à vista ou a prazo.")
    if dados.documento not in regras.DOCUMENTOS:
        raise HTTPException(400, "Escolha o documento: nota fiscal ou cupom fiscal.")
    if dados.condicao == "PRAZO" and int(dados.parcelas or 1) < 1:
        raise HTTPException(400, "Informe em quantas parcelas.")


@router.post("/{pedido_id}/finalizar")
def finalizar(pedido_id: int, dados: FinalizarPedidoIn, db: Session = Depends(get_db),
              usuario: Usuario = Depends(acesso_liberado)):
    """Fecha a venda: emite o documento e, no a prazo, gera as contas a receber."""
    from ..schemas import ItemNotaIn, NotaEmitidaIn, ParcelaNotaIn
    from .emissao import criar_rascunho, transmitir
    from ..schemas import TransmitirNotaIn

    pedido = _pedido(db, pedido_id, usuario)
    _conferir_finalizacao(pedido, dados)

    condicao = dados.condicao
    quantidade = max(1, int(dados.parcelas or 1)) if condicao == "PRAZO" else 1
    primeiro = dados.primeiro_vencimento or date.today()
    try:
        parcelas = (regras.montar_parcelas(float(pedido.valor_total or 0), quantidade,
                                           primeiro, dados.intervalo_dias)
                    if condicao == "PRAZO" else [])
    except regras.ErroPedido as erro:
        raise HTTPException(400, str(erro)) from None

    # o desconto do pedido é rateado entre os itens: a nota não tem "desconto do
    # total", cada item leva o seu, e a soma tem de fechar com o valor do pedido
    itens = []
    desconto_total = float(pedido.desconto or 0)
    produtos = float(pedido.valor_produtos or 0) or 1.0
    sobra = dinheiro(desconto_total)
    for posicao, item in enumerate(pedido.itens):
        parte = (dinheiro(float(item.valor_total or 0) / produtos * desconto_total)
                 if posicao < len(pedido.itens) - 1 else sobra)
        sobra = dinheiro(sobra - parte)
        itens.append(ItemNotaIn(
            produto_id=item.produto_id,
            descricao=item.descricao,
            unidade=item.unidade or "UN",
            quantidade=float(item.quantidade or 0),
            valor_unitario=float(item.valor_unitario or 0),
            desconto=dinheiro(float(item.desconto or 0) + parte),
            usar_regra=True,
        ))

    if dados.documento == "SEM":
        # a venda fecha e o financeiro nasce; nota ou cupom saem depois, pelo
        # botão do próprio pedido
        nota, erro = None, ""
    elif dados.documento == "CUPOM":
        nota, erro = _finalizar_cupom(db, usuario, pedido, dados, itens)
    else:
        nota, erro = _finalizar_nota(
            db, usuario, pedido, dados, itens, parcelas,
            NotaEmitidaIn, ParcelaNotaIn, TransmitirNotaIn, criar_rascunho, transmitir)

    if erro:
        # a venda não se perde: o pedido continua aberto, com o motivo na tela
        db.commit()
        return {"ok": False, "mensagem": erro, "pedido": regras.ficha(db, pedido)}

    if dados.observacao:
        pedido.observacao = (dados.observacao or "").strip()[:300]
    try:
        mensagem = regras.concluir(db, pedido, nota, condicao, quantidade, primeiro,
                                   dados.intervalo_dias, dados.documento,
                                   dados.forma_pagamento, usuario)
    except regras.ErroPedido as erro:
        # o título não pôde nascer: desfaz e devolve o pedido aberto, com o motivo
        db.rollback()
        return {"ok": False, "mensagem": str(erro), "pedido": regras.ficha(db, pedido)}
    db.commit()
    db.refresh(pedido)
    return {"ok": True, "mensagem": mensagem, "pedido": regras.ficha(db, pedido)}


@router.post("/{pedido_id}/documento")
def emitir_documento(pedido_id: int, dados: FinalizarPedidoIn,
                     db: Session = Depends(get_db),
                     usuario: Usuario = Depends(acesso_liberado)):
    """Emite a nota ou o cupom de uma venda que já foi fechada sem documento.

    O título **não é gerado de novo**: ele já existe desde a finalização. A nota
    nasce ligada a ele (`lancamento_id`), para o sistema não oferecer faturar uma
    segunda vez e não contabilizar a mesma venda duas vezes.

    É aqui também que o estoque baixa — foi a escolha do Galba: o saldo mexe
    quando o documento sai, não antes.
    """
    from datetime import datetime as agora

    from ..schemas import ItemNotaIn, NotaEmitidaIn, ParcelaNotaIn, TransmitirNotaIn
    from .emissao import criar_rascunho, transmitir

    pedido = _pedido(db, pedido_id, usuario)
    if pedido.situacao != "FINALIZADO":
        raise HTTPException(400, "Só pedido finalizado emite documento fiscal.")
    if pedido.nota_id:
        raise HTTPException(
            400, "Este pedido já tem documento fiscal. Para trocar, cancele a nota na SEFAZ.")
    if dados.documento not in regras.DOCUMENTOS_FISCAIS:
        raise HTTPException(400, "Escolha o documento: nota fiscal ou cupom fiscal.")

    itens = [ItemNotaIn(
        produto_id=i.produto_id, descricao=i.descricao, unidade=i.unidade or "UN",
        quantidade=float(i.quantidade or 0), valor_unitario=float(i.valor_unitario or 0),
        desconto=float(i.desconto or 0), usar_regra=True) for i in pedido.itens]
    parcelas = []
    if pedido.lancamento_id:
        titulo = db.get(Lancamento, pedido.lancamento_id)
        if titulo is not None:
            # as duplicatas da nota são as parcelas do título que já existe, para
            # o papel, o XML e o financeiro contarem a mesma história
            parcelas = [{"numero": str(p.numero or i + 1).zfill(3),
                         "vencimento": p.data_vencimento, "valor": float(p.valor or 0)}
                        for i, p in enumerate(sorted(titulo.parcelas,
                                                     key=lambda x: x.data_vencimento))]

    if dados.documento == "CUPOM":
        nota, erro = _finalizar_cupom(db, usuario, pedido, dados, itens)
    else:
        nota, erro = _finalizar_nota(
            db, usuario, pedido, dados, itens, parcelas,
            NotaEmitidaIn, ParcelaNotaIn, TransmitirNotaIn, criar_rascunho, transmitir)
    if erro:
        db.commit()
        return {"ok": False, "mensagem": erro, "pedido": regras.ficha(db, pedido)}

    pedido.nota_id = nota.id
    pedido.documento = dados.documento
    # a nota assume o título que a venda já gerou, em vez de criar outro
    if pedido.lancamento_id and not nota.lancamento_id:
        nota.lancamento_id = pedido.lancamento_id
        nota.faturada_em = agora.utcnow()
        nota.faturada_por_id = usuario.id
        nota.faturamento_observacao = f"Título gerado pelo pedido nº {pedido.numero}"
    db.commit()
    db.refresh(pedido)
    return {
        "ok": True,
        "pedido": regras.ficha(db, pedido),
        "mensagem": (f"{regras.DOCUMENTOS[dados.documento]} emitida para o pedido nº "
                     f"{pedido.numero}." + (" O título que já existia foi mantido — "
                                            "nada foi lançado em dobro."
                                            if pedido.lancamento_id else "")),
    }


def _finalizar_cupom(db: Session, usuario: Usuario, pedido: Pedido,
                     dados: FinalizarPedidoIn, itens) -> tuple[Nota | None, str]:
    """Cupom: a rota do balcão já cria e transmite numa chamada só."""
    from .cupom import ItemVendaIn, PagamentoVendaIn, VendaIn, vender

    documento = pedido.cliente_documento
    nome = pedido.cliente_nome
    if pedido.parceiro is not None:      # cliente cadastrado: o cupom leva o CPF/CNPJ dele
        documento = documento or pedido.parceiro.cpf_cnpj
        nome = nome or pedido.parceiro.nome
    try:
        retorno = vender(VendaIn(
            empresa_id=pedido.empresa_id,
            ambiente=dados.ambiente,
            confirmo_producao=dados.confirmo_producao,
            consumidor_documento=documento,
            consumidor_nome=nome,
            itens=[ItemVendaIn(produto_id=i.produto_id, descricao=i.descricao,
                               quantidade=i.quantidade,
                               valor_unitario=i.valor_unitario, desconto=i.desconto)
                   for i in itens],
            pagamentos=[PagamentoVendaIn(codigo=dados.forma_pagamento or "01",
                                         valor=float(pedido.valor_total or 0))],
        ), db, usuario)
    except HTTPException as erro:
        return None, str(erro.detail)
    if not retorno.get("ok"):
        return None, retorno.get("mensagem") or "A SEFAZ não autorizou o cupom."
    return db.get(Nota, retorno.get("cupom_id")), ""


def _finalizar_nota(db: Session, usuario: Usuario, pedido: Pedido,
                    dados: FinalizarPedidoIn, itens, parcelas,
                    NotaEmitidaIn, ParcelaNotaIn, TransmitirNotaIn,
                    criar_rascunho, transmitir) -> tuple[Nota | None, str]:
    """NF-e: rascunho com as duplicatas do a prazo e transmissão, como sempre."""
    if not pedido.parceiro_id:
        return None, ("A nota fiscal precisa do cliente cadastrado. Escolha o cliente no "
                      "pedido, ou finalize como cupom fiscal, que aceita consumidor não "
                      "identificado.")
    ficha = criar_rascunho(NotaEmitidaIn(
        empresa_id=pedido.empresa_id,
        parceiro_id=pedido.parceiro_id,
        ambiente=dados.ambiente,
        natureza_operacao="VENDA DE MERCADORIA",
        informacoes_complementares=f"Pedido nº {pedido.numero}",
        itens=itens,
        parcelas=[ParcelaNotaIn(numero=p["numero"], vencimento=p["vencimento"],
                                valor=p["valor"]) for p in parcelas],
    ), db, usuario)
    nota = db.get(Nota, ficha["nota"]["id"])
    try:
        retorno = transmitir(nota.id, TransmitirNotaIn(
            empresa_id=pedido.empresa_id,
            confirmo_producao=dados.confirmo_producao), db, usuario)
    except HTTPException as erro:
        return None, str(erro.detail)
    if not retorno.get("ok"):
        return None, retorno.get("mensagem") or "A SEFAZ não autorizou a nota."
    return nota, ""
