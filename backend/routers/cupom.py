"""Cupom fiscal eletrônico (NFC-e, modelo 65): configuração, venda e impressão.

Rotas
-----
GET    /api/cupom/config          CSC e série (nunca devolve o CSC)
PUT    /api/cupom/config          salva
POST   /api/cupom/venda           cria a venda e já transmite — é o balcão
GET    /api/cupom/{id}            abre o cupom
GET    /api/cupom/{id}/impressao  a folha de 80 mm, pronta para a térmica

Cancelar usa a mesma rota da nota (`POST /api/nfe/{id}/cancelar`), porque o
evento é o mesmo 110111 — só o endereço da SEFAZ muda, e disso o motor cuida.

Por que a venda é uma chamada só
--------------------------------
Na NF-e o caminho é rascunho → conferir → transmitir, porque a nota é montada
com calma. No balcão não existe isso: o consumidor está esperando. Então
`/venda` cria e transmite de uma vez, e devolve o cupom pronto para imprimir.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import correio, cupom as nfce, dfe as motor
from ..database import get_db
from ..deps import acesso_liberado, validar_empresa
from ..models import ConfigCupom, Empresa, Nota, NotaPagamento, Usuario
from ..utils import dinheiro, serializar

router = APIRouter(prefix="/api/cupom", tags=["cupom"])


class ConfigCupomIn(BaseModel):
    empresa_id: int
    serie: str | None = "1"
    # em branco = mantém o que já está guardado
    csc_homologacao: str | None = None
    csc_id_homologacao: str | None = None
    csc_producao: str | None = None
    csc_id_producao: str | None = None
    ativo: bool = True


class ItemVendaIn(BaseModel):
    produto_id: int | None = None
    descricao: str | None = None
    quantidade: float = 1
    valor_unitario: float = 0
    desconto: float = 0
    cfop: str | None = None


class PagamentoVendaIn(BaseModel):
    # 01 dinheiro | 03 cartão de crédito | 04 cartão de débito | 17 Pix | 99 outros
    codigo: str = "01"
    valor: float = 0


class VendaIn(BaseModel):
    empresa_id: int
    ambiente: str | None = None
    itens: list[ItemVendaIn] = []
    pagamentos: list[PagamentoVendaIn] = []
    consumidor_documento: str | None = None
    consumidor_nome: str | None = None
    troco: float = 0
    confirmo_producao: bool = False


def config_do_cupom(db: Session, empresa_id: int) -> ConfigCupom | None:
    return db.query(ConfigCupom).filter(ConfigCupom.empresa_id == empresa_id).first()


def _ficha_config(config: ConfigCupom | None, empresa: Empresa) -> dict:
    """O que a tela recebe. **O CSC nunca sai daqui** — só o aviso de que existe."""
    return {
        "serie": (config.serie if config else "1") or "1",
        "ativo": config.ativo if config else True,
        "tem_csc_homologacao": bool(config and config.csc_homologacao),
        "tem_csc_producao": bool(config and config.csc_producao),
        "csc_id_homologacao": config.csc_id_homologacao if config else None,
        "csc_id_producao": config.csc_id_producao if config else None,
        "uf": empresa.uf,
        "uf_atendida": nfce.uf_atendida(empresa.uf),
        "ufs_com_cupom": sorted(nfce.AUTORIZACAO),
        "minutos_para_cancelar": nfce.MINUTOS_PARA_CANCELAR,
    }


@router.get("/config")
def ler_config(empresa_id: int, db: Session = Depends(get_db),
               usuario: Usuario = Depends(acesso_liberado)):
    empresa = validar_empresa(db, empresa_id, usuario)
    return _ficha_config(config_do_cupom(db, empresa_id), empresa)


@router.put("/config")
def salvar_config(dados: ConfigCupomIn, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(acesso_liberado)):
    empresa = validar_empresa(db, dados.empresa_id, usuario)
    config = config_do_cupom(db, dados.empresa_id)
    if config is None:
        config = ConfigCupom(empresa_id=dados.empresa_id)
        db.add(config)
    serie = (dados.serie or "1").strip() or "1"
    if not serie.isdigit() or not 1 <= int(serie) <= 999:
        raise HTTPException(400, "A série do cupom é um número de 1 a 999.")
    config.serie = str(int(serie))
    for campo_csc, campo_id in (("csc_homologacao", "csc_id_homologacao"),
                                ("csc_producao", "csc_id_producao")):
        valor = (getattr(dados, campo_csc) or "").strip()
        if valor:
            # o CSC some daqui cifrado e não volta por nenhuma rota
            setattr(config, campo_csc, correio.cifrar(valor))
        identificador = (getattr(dados, campo_id) or "").strip()
        if identificador:
            if not identificador.isdigit() or len(identificador) > 6:
                raise HTTPException(
                    400, "O número de identificação do CSC (idToken) tem de 1 a 6 dígitos.")
            setattr(config, campo_id, identificador)
    config.ativo = bool(dados.ativo)
    config.atualizado_em = datetime.utcnow()
    db.commit()
    db.refresh(config)
    return _ficha_config(config, empresa)


# --------------------------------------------------------------------------- #
# A venda
# --------------------------------------------------------------------------- #
@router.post("/venda")
def vender(dados: VendaIn, db: Session = Depends(get_db),
           usuario: Usuario = Depends(acesso_liberado)):
    """Cria o cupom e já transmite. É a tela de balcão em uma chamada só."""
    from ..schemas import NotaEmitidaIn
    from .emissao import _aplicar_itens, criar_rascunho, transmitir
    from ..schemas import TransmitirNotaIn

    empresa = validar_empresa(db, dados.empresa_id, usuario)
    if not nfce.uf_atendida(empresa.uf):
        raise HTTPException(
            400, f"O cupom fiscal ainda não está ligado à SEFAZ de "
                 f"{empresa.uf or '(sem UF)'}. Hoje o sistema emite cupom em: "
                 f"{', '.join(sorted(nfce.AUTORIZACAO))}.")
    if not dados.itens:
        raise HTTPException(400, "O cupom está sem itens — nada foi vendido.")
    config = config_do_cupom(db, dados.empresa_id)
    ambiente = (dados.ambiente or "2").strip() or "2"
    # falha cedo e com a frase certa, antes de gastar número de cupom
    try:
        nfce.csc_do_ambiente(config, ambiente)
    except nfce.ErroCupom as erro:
        raise HTTPException(400, str(erro)) from None

    # o CPF errado é descoberto aqui, antes de gastar número de cupom e antes de
    # abrir o certificado — senão o erro que aparece é o do certificado
    documento = motor.so_numeros(dados.consumidor_documento or "")
    if documento and len(documento) not in (11, 14):
        raise HTTPException(
            400, "O CPF (ou CNPJ) do consumidor está incompleto. Deixe em branco para o "
                 "cupom sair sem identificação, ou digite o documento inteiro.")

    total = sum(round(float(i.quantidade or 0) * float(i.valor_unitario or 0)
                      - float(i.desconto or 0), 2) for i in dados.itens)
    pagamentos = dados.pagamentos or [PagamentoVendaIn(codigo="01", valor=total)]
    pago = sum(float(p.valor or 0) for p in pagamentos)
    if round(pago, 2) + 0.001 < round(total, 2):
        raise HTTPException(
            400, f"O pagamento ({pago:.2f}) é menor que o total do cupom ({total:.2f}).")

    corpo = NotaEmitidaIn(
        empresa_id=dados.empresa_id,
        parceiro_id=None,
        ambiente=ambiente,
        serie=(config.serie if config else "1") or "1",
        natureza_operacao="VENDA AO CONSUMIDOR",
        itens=[{"produto_id": i.produto_id, "descricao": i.descricao,
                "quantidade": i.quantidade, "valor_unitario": i.valor_unitario,
                "desconto": i.desconto, "cfop": i.cfop} for i in dados.itens],
    )
    ficha = criar_rascunho(corpo, db, usuario)
    nota = db.get(Nota, ficha["nota"]["id"])
    nota.modelo = "65"
    nota.consumidor_documento = (dados.consumidor_documento or "").strip() or None
    nota.consumidor_nome = (dados.consumidor_nome or "").strip() or None
    # troco: o que o consumidor deu a mais. Vai no XML, não é desconto nem venda
    nota.troco = (float(dados.troco) if dados.troco
                  else max(0.0, round(pago - total, 2)))
    # as formas de pagamento do cupom (grupo <pag>) — a nota fiscal usa
    # duplicatas, o cupom usa isto
    for forma in pagamentos:
        codigo = (forma.codigo or "01").zfill(2)
        nota.pagamentos.append(NotaPagamento(
            origem="PAGAMENTO", codigo=codigo,
            descricao=motor.FORMAS_PAGAMENTO.get(codigo, "Outros"),
            valor=dinheiro(forma.valor)))
    db.commit()

    retorno = transmitir(nota.id, TransmitirNotaIn(
        empresa_id=dados.empresa_id, confirmo_producao=dados.confirmo_producao),
        db, usuario)
    retorno["cupom_id"] = nota.id
    return retorno


@router.get("/{nota_id}")
def abrir(nota_id: int, db: Session = Depends(get_db),
          usuario: Usuario = Depends(acesso_liberado)):
    nota = _cupom(db, nota_id, usuario)
    return {"cupom": serializar(nota, exclude={"xml"}, extras={
        "itens": [serializar(i) for i in nota.itens],
        "pagamentos": [serializar(p) for p in nota.pagamentos],
        "pode_cancelar": _pode_cancelar(nota)[0],
        "motivo_nao_cancela": _pode_cancelar(nota)[1],
    })}


def _cupom(db: Session, nota_id: int, usuario: Usuario) -> Nota:
    nota = db.get(Nota, nota_id)
    if not nota or (nota.modelo or "") != "65":
        raise HTTPException(404, "Cupom não encontrado.")
    validar_empresa(db, nota.empresa_id, usuario)
    return nota


def _pode_cancelar(nota: Nota) -> tuple[bool, str]:
    """No cupom o prazo é curto — em Minas, 30 minutos."""
    if nota.status_emissao != "AUTORIZADA":
        return False, "Só dá para cancelar cupom autorizado."
    if not nota.data_autorizacao:
        return False, "Este cupom não tem a hora da autorização guardada."
    limite = nota.data_autorizacao + timedelta(minutes=nfce.MINUTOS_PARA_CANCELAR)
    if datetime.utcnow() > limite:
        return False, (f"Passou o prazo de {nfce.MINUTOS_PARA_CANCELAR} minutos para "
                       "cancelar o cupom. Faça uma devolução (nota de entrada).")
    return True, ""


@router.get("/{nota_id}/impressao", response_class=None)
def imprimir(nota_id: int, db: Session = Depends(get_db),
             usuario: Usuario = Depends(acesso_liberado)):
    """A folha do cupom, no tamanho da bobina de 80 mm."""
    from fastapi.responses import HTMLResponse

    from .. import danfe_cupom

    nota = _cupom(db, nota_id, usuario)
    empresa = db.get(Empresa, nota.empresa_id)
    if not (nota.xml or "").strip():
        raise HTTPException(400, "Este cupom ainda não foi autorizado pela SEFAZ.")
    return HTMLResponse(danfe_cupom.gerar(nota.xml, empresa))
