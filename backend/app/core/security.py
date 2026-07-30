"""Autenticacao: sessao da UI (cookie assinado) e bearer token da API."""
import secrets
import time

import bcrypt
from fastapi import Cookie, Header, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .settings import admin_password_hash, admin_user, api_token, secret_key

SESSAO_COOKIE = "nfse_sessao"
SESSAO_MAX_AGE = 7 * 24 * 3600  # 7 dias


def verificar_login(user: str, senha: str) -> bool:
    hash_conf = admin_password_hash()
    if not hash_conf or user != admin_user():
        return False
    try:
        return bcrypt.checkpw(senha.encode(), hash_conf.encode())
    except ValueError:
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key(), salt="nfse-sessao")


def criar_sessao(user: str) -> str:
    return _serializer().dumps({"user": user})


def validar_sessao(token: str) -> bool:
    try:
        _serializer().loads(token, max_age=SESSAO_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


def _bearer_valido(authorization: str | None) -> bool:
    token = api_token()
    if not token or not authorization or not authorization.startswith("Bearer "):
        return False
    return secrets.compare_digest(authorization.removeprefix("Bearer "), token)


def sessao_requerida(nfse_sessao: str | None = Cookie(default=None)):
    """Dependency: apenas sessao da UI."""
    if not nfse_sessao or not validar_sessao(nfse_sessao):
        raise HTTPException(status_code=401, detail="Sessao invalida ou expirada")


def bearer_ou_sessao(
    authorization: str | None = Header(default=None),
    nfse_sessao: str | None = Cookie(default=None),
):
    """Dependency: bearer token da API ou sessao da UI."""
    if _bearer_valido(authorization):
        return
    if nfse_sessao and validar_sessao(nfse_sessao):
        return
    raise HTTPException(status_code=401, detail="Nao autenticado")


class RateLimiter:
    """Limitador simples em memoria por chave (IP), janela deslizante."""

    def __init__(self, max_tentativas: int = 5, janela_seg: int = 60):
        self.max = max_tentativas
        self.janela = janela_seg
        self._hits: dict[str, list[float]] = {}

    def permitir(self, chave: str) -> bool:
        agora = time.monotonic()
        hits = [t for t in self._hits.get(chave, []) if agora - t < self.janela]
        if len(hits) >= self.max:
            self._hits[chave] = hits
            return False
        hits.append(agora)
        self._hits[chave] = hits
        return True


login_limiter = RateLimiter()
