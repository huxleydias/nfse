from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import db_session
from app.core.security import sessao_requerida
from app.models.config_store import get_config, save_config

router = APIRouter(prefix="/api/config", tags=["config"])

# O XML da prefeitura recebe a aliquota como fracao (0.02 = 2%). ISS municipal
# vai de 2% a 5%, entao qualquer valor acima de 1 e percentual digitado por
# engano e viraria uma nota com aliquota absurda. Barrar aqui e melhor do que
# descobrir na nota emitida.
ALIQUOTA_MAX = 1.0


def _validar_servicos(servicos: dict) -> None:
    erros = []
    for codigo, s in (servicos or {}).items():
        try:
            aliquota = float(s.get("aliquota", 0))
        except (TypeError, ValueError):
            erros.append(f"Servico {codigo}: aliquota nao e numero")
            continue
        if aliquota < 0 or aliquota > ALIQUOTA_MAX:
            erros.append(
                f"Servico {codigo}: aliquota {aliquota} fora da faixa. "
                f"Use fracao, nao percentual: 2% e 0.02"
            )
    if erros:
        raise HTTPException(status_code=422, detail=erros)


@router.get("", dependencies=[Depends(sessao_requerida)])
def obter_config(session=Depends(db_session)):
    cfg = get_config(session)
    # Nunca expor a senha cifrada do certificado
    cfg.pop("certificado", None)
    return cfg


@router.put("", dependencies=[Depends(sessao_requerida)])
def atualizar_config(novos: dict, session=Depends(db_session)):
    if "servicos" in novos:
        _validar_servicos(novos["servicos"])
    cfg = get_config(session)
    # Bloco certificado so muda via upload dedicado
    novos.pop("certificado", None)
    cfg.update(novos)
    save_config(session, cfg)
    cfg_limpa = {k: v for k, v in cfg.items() if k != "certificado"}
    return cfg_limpa
