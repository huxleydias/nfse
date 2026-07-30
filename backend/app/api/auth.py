from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.core.security import (
    SESSAO_COOKIE,
    SESSAO_MAX_AGE,
    criar_sessao,
    login_limiter,
    verificar_login,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginPayload(BaseModel):
    usuario: str
    senha: str


@router.post("/login")
def login(payload: LoginPayload, request: Request, response: Response):
    ip = request.client.host if request.client else "desconhecido"
    if not login_limiter.permitir(ip):
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde um minuto.")
    if not verificar_login(payload.usuario, payload.senha):
        raise HTTPException(status_code=401, detail="Usuario ou senha incorretos")
    response.set_cookie(
        SESSAO_COOKIE,
        criar_sessao(payload.usuario),
        max_age=SESSAO_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSAO_COOKIE)
    return {"ok": True}
