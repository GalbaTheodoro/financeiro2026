"""Consultas externas usadas pelos cadastros (CNPJ na Receita e CEP nos Correios)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import consulta_cep, consulta_cnpj
from ..database import get_db
from ..deps import acesso_liberado

router = APIRouter(prefix="/api/consulta", tags=["consulta"],
                   dependencies=[Depends(acesso_liberado)])


@router.get("/situacao")
def situacao(db: Session = Depends(get_db)):
    """Diz quais buscas automáticas estão disponíveis e por qual provedor."""
    return {
        "cnpj": consulta_cnpj.situacao_servico(db),
        "cep": consulta_cep.situacao_servico(db),
    }


@router.get("/cnpj/{cnpj}")
def buscar_cnpj(cnpj: str, db: Session = Depends(get_db)):
    """Dados cadastrais do CNPJ, já no formato usado pelo cadastro."""
    return consulta_cnpj.consultar(db, cnpj)


@router.get("/cep/{cep}")
def buscar_cep(cep: str, db: Session = Depends(get_db)):
    """Endereço do CEP, já no formato usado pelo cadastro."""
    return consulta_cep.consultar(db, cep)
