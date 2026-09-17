"""Cadastro da tabela de ICMS (UF do vendedor x UF do comprador x produto)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import icms as regras
from ..database import get_db
from ..deps import acesso_liberado, validar_empresa
from ..models import AliquotaIcms, Produto, Usuario
from ..schemas import AliquotaIcmsIn, GerarIcmsPadraoIn
from ..utils import serializar

router = APIRouter(prefix="/api/icms", tags=["icms"])


def _dict(linha: AliquotaIcms) -> dict:
    return serializar(linha, extras={
        "produto_nome": linha.produto.nome if linha.produto else None,
        "regra": f"{linha.uf_origem} → {linha.uf_destino}",
    })


def _validar(db: Session, dados: AliquotaIcmsIn, ignorar_id: int | None = None) -> tuple[str, str]:
    origem = regras.normalizar_uf(dados.uf_origem)
    destino = regras.normalizar_uf(dados.uf_destino)
    if not origem:
        raise HTTPException(400, "Escolha a UF do vendedor.")
    if not destino:
        raise HTTPException(400, "Escolha a UF do comprador.")
    if dados.aliquota is None or dados.aliquota < 0 or dados.aliquota > 100:
        raise HTTPException(400, "A alíquota deve ficar entre 0 e 100%.")
    if dados.produto_id:
        produto = db.get(Produto, dados.produto_id)
        if not produto or produto.empresa_id != dados.empresa_id:
            raise HTTPException(400, "Produto inválido.")
    repetida = db.query(AliquotaIcms).filter(
        AliquotaIcms.empresa_id == dados.empresa_id,
        AliquotaIcms.uf_origem == origem,
        AliquotaIcms.uf_destino == destino,
        AliquotaIcms.produto_id.is_(None) if not dados.produto_id
        else AliquotaIcms.produto_id == dados.produto_id,
    )
    if ignorar_id:
        repetida = repetida.filter(AliquotaIcms.id != ignorar_id)
    if repetida.first():
        alvo = "este produto" if dados.produto_id else "todos os produtos"
        raise HTTPException(400, f"Já existe uma alíquota {origem} → {destino} para {alvo}. Edite a linha existente.")
    return origem, destino


@router.get("")
def listar(empresa_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, empresa_id, usuario)
    linhas = (
        db.query(AliquotaIcms)
        .filter(AliquotaIcms.empresa_id == empresa_id)
        .order_by(AliquotaIcms.uf_origem, AliquotaIcms.uf_destino, AliquotaIcms.produto_id)
        .all()
    )
    return [_dict(l) for l in linhas]


@router.get("/ufs")
def ufs():
    return regras.UFS


@router.get("/aliquota")
def consultar(
    empresa_id: int,
    uf_origem: str | None = None,
    uf_destino: str | None = None,
    produto_id: int | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(acesso_liberado),
):
    """Qual alíquota o contrato usaria para esse par de estados (e produto)."""
    validar_empresa(db, empresa_id, usuario)
    linha = regras.buscar_aliquota(db, empresa_id, uf_origem, uf_destino, produto_id)
    return {"encontrada": bool(linha), "aliquota": float(linha.aliquota) if linha else 0.0,
            "linha": _dict(linha) if linha else None}


@router.post("")
def criar(dados: AliquotaIcmsIn, db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)):
    validar_empresa(db, dados.empresa_id, usuario)
    origem, destino = _validar(db, dados)
    linha = AliquotaIcms(
        empresa_id=dados.empresa_id, uf_origem=origem, uf_destino=destino,
        produto_id=dados.produto_id or None, aliquota=round(dados.aliquota, 4),
        observacao=(dados.observacao or "").strip() or None, ativo=dados.ativo,
    )
    db.add(linha)
    db.commit()
    db.refresh(linha)
    return _dict(linha)


@router.put("/{linha_id}")
def atualizar(linha_id: int, dados: AliquotaIcmsIn, db: Session = Depends(get_db),
              usuario: Usuario = Depends(acesso_liberado)):
    linha = db.get(AliquotaIcms, linha_id)
    if not linha:
        raise HTTPException(404, "Alíquota não encontrada.")
    validar_empresa(db, linha.empresa_id, usuario)
    dados.empresa_id = linha.empresa_id
    origem, destino = _validar(db, dados, ignorar_id=linha.id)
    linha.uf_origem, linha.uf_destino = origem, destino
    linha.produto_id = dados.produto_id or None
    linha.aliquota = round(dados.aliquota, 4)
    linha.observacao = (dados.observacao or "").strip() or None
    linha.ativo = dados.ativo
    db.commit()
    db.refresh(linha)
    return _dict(linha)


@router.delete("/{linha_id}")
def excluir(linha_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(acesso_liberado)):
    """Excluir não mexe nos contratos já salvos: eles guardam o percentual e o valor."""
    linha = db.get(AliquotaIcms, linha_id)
    if not linha:
        raise HTTPException(404, "Alíquota não encontrada.")
    validar_empresa(db, linha.empresa_id, usuario)
    db.delete(linha)
    db.commit()
    return {"ok": True}


@router.post("/gerar-padrao")
def gerar_padrao(dados: GerarIcmsPadraoIn, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(acesso_liberado)):
    """Cria as linhas gerais (todos os produtos) saindo de um estado para os outros 26,
    com a alíquota interestadual de referência (7% ou 12%)."""
    validar_empresa(db, dados.empresa_id, usuario)
    origem = regras.normalizar_uf(dados.uf_origem)
    if not origem:
        raise HTTPException(400, "Escolha a UF do vendedor.")
    existentes = {
        l.uf_destino: l for l in db.query(AliquotaIcms).filter(
            AliquotaIcms.empresa_id == dados.empresa_id, AliquotaIcms.uf_origem == origem,
            AliquotaIcms.produto_id.is_(None))
    }
    criadas = atualizadas = mantidas = 0
    for destino in regras.UFS:
        if destino == origem:
            if dados.aliquota_interna is None:
                continue
            valor, obs = float(dados.aliquota_interna), "Operação interna (informada)"
        else:
            valor = regras.aliquota_interestadual(origem, destino)
            obs = "Interestadual de referência (Res. Senado 22/89)"
        atual = existentes.get(destino)
        if atual and not dados.substituir:
            mantidas += 1
            continue
        if atual:
            atual.aliquota, atual.observacao, atual.ativo = valor, obs, True
            atualizadas += 1
        else:
            db.add(AliquotaIcms(empresa_id=dados.empresa_id, uf_origem=origem, uf_destino=destino,
                                aliquota=valor, observacao=obs, ativo=True))
            criadas += 1
    db.commit()
    return {"criadas": criadas, "atualizadas": atualizadas, "mantidas": mantidas,
            "mensagem": f"{origem}: {criadas} alíquota(s) criada(s), {atualizadas} atualizada(s), "
                        f"{mantidas} já existia(m) e foram mantida(s)."}
