import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

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
from app.nfse.nacional import AMBIENTE_HOMOLOGACAO, url_consulta_publica
from app.nfse.parser import RespostaInvalidaError
from app.nfse.pdf import PdfIndisponivelError, baixar_pdf
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
        raise HTTPException(
            status_code=400,
            detail={"erros_prefeitura": e.erros, "emissor": e.emissor},
        )
    except (PrefeituraIndisponivelError, RespostaInvalidaError) as e:
        raise HTTPException(status_code=502, detail=str(e))

    if resultado.get("teste") and "nota" not in resultado:
        # Modo teste municipal: so validacao, nenhuma nota
        return {"teste": True, "resultado": resultado["resultado"]}
    # No nacional o modo teste emite na producao restrita e grava a nota
    return {
        "teste": bool(resultado.get("teste")),
        "idempotente": resultado.get("idempotente", False),
        "nota": nota_com_link(resultado["nota"]),
        "alertas": resultado.get("alertas", []),
    }


def nota_com_link(nota: Nota, com_xml: bool = False) -> dict:
    """Nota nacional ganha o link oficial da Consulta Publica."""
    dados = nota.to_dict(com_xml=com_xml)
    if nota.chave_acesso:
        dados["pdf_url"] = url_consulta_publica(
            nota.chave_acesso, homologacao=nota.ambiente == AMBIENTE_HOMOLOGACAO
        )
    return dados


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
    return {"notas": [nota_com_link(n) for n in q.limit(500).all()]}


@router.get("/{nota_id}", dependencies=[Depends(bearer_ou_sessao)])
def detalhe_nota(nota_id: int, session=Depends(db_session)):
    nota = session.get(Nota, nota_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="Nota nao encontrada")
    return {"nota": nota_com_link(nota, com_xml=True)}


@router.get("/{nota_id}/pdf", dependencies=[Depends(bearer_ou_sessao)])
def pdf_nota(nota_id: int, download: bool = False, session=Depends(db_session)):
    """PDF oficial da NFS-e.

    Municipal: buscado no portal da prefeitura. Nacional: redireciona para a
    Consulta Publica, onde o DANFSe oficial e baixado (a API de geracao do
    DANFSe foi suspensa em 03/08/2026).
    """
    nota = session.get(Nota, nota_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="Nota nao encontrada")
    if nota.chave_acesso:
        return RedirectResponse(nota_com_link(nota)["pdf_url"], status_code=307)
    if not nota.numero_nfse or not nota.codigo_verificacao:
        raise HTTPException(
            status_code=409,
            detail="Nota sem numero de NFS-e ou codigo de verificacao: "
            "so notas autorizadas tem PDF",
        )

    from app.models.config_store import get_config

    inscricao = get_config(session)["prestador"]["inscricao_municipal"]
    try:
        conteudo = baixar_pdf(inscricao, nota.numero_nfse, nota.codigo_verificacao)
    except PdfIndisponivelError as e:
        raise HTTPException(status_code=502, detail=str(e))

    disposicao = "attachment" if download else "inline"
    nome = f"nfse-{nota.numero_nfse}.pdf"
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposicao}; filename="{nome}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.delete("/{nota_id}", dependencies=[Depends(bearer_ou_sessao)])
def cancelar_nota(
    nota_id: int,
    motivo_codigo: int = Query(default=1, description="Nacional: 1, 2 ou 9"),
    motivo: str | None = Query(default=None, description="Nacional: 15 a 255 caracteres"),
    session=Depends(db_session),
):
    nota = session.get(Nota, nota_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="Nota nao encontrada")
    if nota.status == "cancelada":
        return {"nota": nota_com_link(nota)}
    if nota.status != "autorizada":
        raise HTTPException(status_code=409, detail=f"Nota com status {nota.status} nao pode ser cancelada")

    client, cert, key = _client_e_cert(session)
    try:
        nota = cancelar(nota, session, client, cert, key, motivo_codigo, motivo)
    except PrefeituraRecusouError as e:
        raise HTTPException(
            status_code=400,
            detail={"erros_prefeitura": e.erros, "emissor": e.emissor},
        )
    except (PrefeituraIndisponivelError, RespostaInvalidaError) as e:
        raise HTTPException(status_code=502, detail=str(e))
    except EmissaoInvalidaError as e:
        raise HTTPException(status_code=409, detail=e.detalhes)
    except XSDValidationError as e:
        raise HTTPException(status_code=422, detail={"xsd": e.erros})
    return {"nota": nota_com_link(nota)}


class SyncPayload(BaseModel):
    inicio: date
    fim: date


@router.post("/sync", dependencies=[Depends(sessao_requerida)])
def sync_notas(payload: SyncPayload, session=Depends(db_session)):
    client, cert, key = _client_e_cert(session)
    try:
        resultado = sincronizar(payload.inicio, payload.fim, session, client, cert, key)
    except EmissaoInvalidaError as e:
        raise HTTPException(status_code=409, detail=e.detalhes)
    except (PrefeituraIndisponivelError, RespostaInvalidaError) as e:
        raise HTTPException(status_code=502, detail=str(e))
    except XSDValidationError as e:
        raise HTTPException(status_code=422, detail={"xsd": e.erros})
    return resultado
