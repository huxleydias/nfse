import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ValidationError

from app.api.deps import db_session
from app.core.security import bearer_ou_sessao, sessao_requerida
from app.models.nota import Nota
from app.nfse.cert_store import carregar_certificado
from app.nfse.emitter import (
    EmissaoInvalidaError,
    EmissaoPayload,
    PrefeituraRecusouError,
    RefEmAndamentoError,
    cancelar,
    emitir,
    sincronizar,
)
from app.nfse.parser import RespostaInvalidaError
from app.nfse.signer import CertificadoError
from app.nfse.soap_client import PrefeituraIndisponivelError, SoapClient
from app.nfse.xsd_validator import XSDValidationError

router = APIRouter(prefix="/api/notas", tags=["notas"])


def _client_e_cert(session):
    try:
        cert, key = carregar_certificado(session)
    except CertificadoError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return SoapClient(cert, key), cert, key


@router.post("", dependencies=[Depends(bearer_ou_sessao)])
def emitir_nota(payload: EmissaoPayload, session=Depends(db_session)):
    client, cert, key = _client_e_cert(session)
    try:
        resultado = emitir(payload, session, client, cert, key)
    except RefEmAndamentoError:
        raise HTTPException(
            status_code=409,
            detail="Emissao com esta ref_externa em andamento. Tente novamente em instantes.",
        )
    except EmissaoInvalidaError as e:
        raise HTTPException(status_code=422, detail=e.detalhes)
    except XSDValidationError as e:
        raise HTTPException(status_code=422, detail={"xsd": e.erros})
    except PrefeituraRecusouError as e:
        raise HTTPException(status_code=400, detail={"erros_prefeitura": e.erros})
    except (PrefeituraIndisponivelError, RespostaInvalidaError) as e:
        raise HTTPException(status_code=502, detail=str(e))

    if resultado.get("teste"):
        return {"teste": True, "resultado": resultado["resultado"]}
    return {
        "teste": False,
        "idempotente": resultado.get("idempotente", False),
        "nota": resultado["nota"].to_dict(),
    }


@router.get("", dependencies=[Depends(bearer_ou_sessao)])
def listar_notas(
    inicio: str | None = Query(default=None),
    fim: str | None = Query(default=None),
    status: str | None = Query(default=None),
    session=Depends(db_session),
):
    q = session.query(Nota).order_by(Nota.id.desc())
    if status:
        q = q.filter(Nota.status == status)
    if inicio:
        q = q.filter(Nota.criada_em >= inicio)
    if fim:
        q = q.filter(Nota.criada_em <= fim + "T23:59:59")
    return {"notas": [n.to_dict() for n in q.limit(500).all()]}


@router.get("/{nota_id}", dependencies=[Depends(bearer_ou_sessao)])
def detalhe_nota(nota_id: int, session=Depends(db_session)):
    nota = session.get(Nota, nota_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="Nota nao encontrada")
    return {"nota": nota.to_dict(com_xml=True)}


@router.delete("/{nota_id}", dependencies=[Depends(bearer_ou_sessao)])
def cancelar_nota(nota_id: int, session=Depends(db_session)):
    nota = session.get(Nota, nota_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="Nota nao encontrada")
    if nota.status == "cancelada":
        return {"nota": nota.to_dict()}
    if nota.status != "autorizada":
        raise HTTPException(status_code=409, detail=f"Nota com status {nota.status} nao pode ser cancelada")

    client, cert, key = _client_e_cert(session)
    try:
        nota = cancelar(nota, session, client, cert, key)
    except PrefeituraRecusouError as e:
        raise HTTPException(status_code=400, detail={"erros_prefeitura": e.erros})
    except (PrefeituraIndisponivelError, RespostaInvalidaError) as e:
        raise HTTPException(status_code=502, detail=str(e))
    except EmissaoInvalidaError as e:
        raise HTTPException(status_code=409, detail=e.detalhes)
    return {"nota": nota.to_dict()}


class SyncPayload(BaseModel):
    inicio: date
    fim: date


@router.post("/sync", dependencies=[Depends(sessao_requerida)])
def sync_notas(payload: SyncPayload, session=Depends(db_session)):
    client, cert, key = _client_e_cert(session)
    try:
        resultado = sincronizar(payload.inicio, payload.fim, session, client, cert, key)
    except (PrefeituraIndisponivelError, RespostaInvalidaError) as e:
        raise HTTPException(status_code=502, detail=str(e))
    except XSDValidationError as e:
        raise HTTPException(status_code=422, detail={"xsd": e.erros})
    return resultado
