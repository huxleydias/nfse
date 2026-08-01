"""Chaves de API: autenticam a API REST e o servidor MCP.

A chave completa aparece uma unica vez, no momento da criacao. O banco
guarda so o hash SHA-256, entao um vazamento do banco nao entrega acesso.
O prefixo fica em claro para o usuario identificar qual chave e qual na
lista sem precisar da chave inteira.
"""
import hashlib
import secrets
from datetime import datetime, timezone

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

PREFIXO = "nfse"
TAMANHO_SEGREDO = 32


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def gerar_chave() -> tuple[str, str, str]:
    """Retorna (chave_completa, prefixo_visivel, hash) de uma chave nova.

    O prefixo visivel e `nfse_` mais os 8 primeiros caracteres do segredo:
    o bastante para o usuario reconhecer a chave na lista, curto o bastante
    para nao servir de atalho para adivinhar o resto.
    """
    segredo = secrets.token_urlsafe(TAMANHO_SEGREDO)
    chave = f"{PREFIXO}_{segredo}"
    prefixo = f"{PREFIXO}_{segredo[:8]}"
    return chave, prefixo, hash_chave(chave)


def hash_chave(chave: str) -> str:
    return hashlib.sha256(chave.encode()).hexdigest()


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(80))
    prefixo: Mapped[str] = mapped_column(String(24), index=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    criada_em: Mapped[str] = mapped_column(String(40), default=_agora)
    ultimo_uso_em: Mapped[str | None] = mapped_column(String(40), nullable=True)
    revogada_em: Mapped[str | None] = mapped_column(String(40), nullable=True)

    @property
    def ativa(self) -> bool:
        return self.revogada_em is None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "nome": self.nome,
            "prefixo": self.prefixo,
            "criada_em": self.criada_em,
            "ultimo_uso_em": self.ultimo_uso_em,
            "revogada_em": self.revogada_em,
            "ativa": self.ativa,
        }


def criar(session, nome: str) -> tuple[ApiKey, str]:
    """Cria a chave e devolve (registro, chave em claro). A chave em claro
    nao pode ser recuperada depois."""
    chave, prefixo, hash_ = gerar_chave()
    registro = ApiKey(nome=nome[:80] or "sem nome", prefixo=prefixo, hash=hash_)
    session.add(registro)
    session.commit()
    return registro, chave


def validar(session, chave: str) -> ApiKey | None:
    """Devolve a chave ativa correspondente, marcando o uso. None se invalida
    ou revogada."""
    if not chave:
        return None
    registro = session.query(ApiKey).filter(ApiKey.hash == hash_chave(chave)).first()
    if registro is None or not registro.ativa:
        return None
    registro.ultimo_uso_em = _agora()
    session.commit()
    return registro


def revogar(session, key_id: int) -> ApiKey | None:
    registro = session.get(ApiKey, key_id)
    if registro is None:
        return None
    if registro.ativa:
        registro.revogada_em = _agora()
        session.commit()
    return registro


def listar(session) -> list[ApiKey]:
    return session.query(ApiKey).order_by(ApiKey.id.desc()).all()
