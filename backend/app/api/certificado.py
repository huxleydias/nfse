from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import db_session
from app.core.security import sessao_requerida
from app.nfse.cert_store import metadata_certificado, salvar_certificado
from app.nfse.signer import CertificadoError

router = APIRouter(prefix="/api/certificado", tags=["certificado"])


@router.post("", dependencies=[Depends(sessao_requerida)])
async def upload_certificado(
    arquivo: UploadFile = File(...),
    senha: str = Form(...),
    session=Depends(db_session),
):
    conteudo = await arquivo.read()
    if len(conteudo) > 512 * 1024:
        raise HTTPException(status_code=422, detail="Arquivo muito grande para um .pfx")
    try:
        meta = salvar_certificado(session, conteudo, senha)
    except CertificadoError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"certificado": meta}


@router.get("", dependencies=[Depends(sessao_requerida)])
def status_certificado(session=Depends(db_session)):
    meta = metadata_certificado(session)
    return {"certificado": meta}
