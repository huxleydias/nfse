from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import db_session
from app.core.security import sessao_requerida
from app.models.config_edicao import ConfigInvalida, aplicar
from app.models.config_store import get_config

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", dependencies=[Depends(sessao_requerida)])
def obter_config(session=Depends(db_session)):
    cfg = get_config(session)
    # Nunca expor a senha cifrada do certificado
    cfg.pop("certificado", None)
    return cfg


@router.put("", dependencies=[Depends(sessao_requerida)])
def atualizar_config(novos: dict, session=Depends(db_session)):
    try:
        return aplicar(session, novos)
    except ConfigInvalida as e:
        raise HTTPException(status_code=422, detail=e.erros)
