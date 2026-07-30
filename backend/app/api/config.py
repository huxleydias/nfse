from fastapi import APIRouter, Depends

from app.api.deps import db_session
from app.core.security import sessao_requerida
from app.models.config_store import get_config, save_config

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", dependencies=[Depends(sessao_requerida)])
def obter_config(session=Depends(db_session)):
    cfg = get_config(session)
    # Nunca expor a senha cifrada do certificado
    cfg.pop("certificado", None)
    return cfg


@router.put("", dependencies=[Depends(sessao_requerida)])
def atualizar_config(novos: dict, session=Depends(db_session)):
    cfg = get_config(session)
    # Bloco certificado so muda via upload dedicado
    novos.pop("certificado", None)
    cfg.update(novos)
    save_config(session, cfg)
    cfg_limpa = {k: v for k, v in cfg.items() if k != "certificado"}
    return cfg_limpa
