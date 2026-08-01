"""Gestao das chaves de API (usadas pela API REST e pelo servidor MCP)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import db_session
from app.core.security import sessao_requerida
from app.models import api_key as modelo

router = APIRouter(prefix="/api/chaves", tags=["chaves"])


class NovaChave(BaseModel):
    nome: str = Field(min_length=1, max_length=80)


@router.get("", dependencies=[Depends(sessao_requerida)])
def listar_chaves(session=Depends(db_session)):
    return {"chaves": [c.to_dict() for c in modelo.listar(session)]}


@router.post("", dependencies=[Depends(sessao_requerida)], status_code=201)
def criar_chave(payload: NovaChave, session=Depends(db_session)):
    registro, chave = modelo.criar(session, payload.nome)
    # A chave em claro so existe nesta resposta. Depois disso, so o hash.
    return {"chave": registro.to_dict(), "valor": chave}


@router.delete("/{key_id}", dependencies=[Depends(sessao_requerida)])
def revogar_chave(key_id: int, session=Depends(db_session)):
    registro = modelo.revogar(session, key_id)
    if registro is None:
        raise HTTPException(status_code=404, detail="Chave nao encontrada")
    return {"chave": registro.to_dict()}
