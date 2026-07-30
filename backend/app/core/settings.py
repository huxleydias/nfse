"""Configuracao por variaveis de ambiente. Segredos so no .env / Railway."""
import os
from pathlib import Path


def data_dir() -> Path:
    d = Path(os.environ.get("DATA_DIR", "./data"))
    d.mkdir(parents=True, exist_ok=True)
    (d / "certs").mkdir(exist_ok=True)
    return d


def secret_key() -> str:
    key = os.environ.get("SECRET_KEY", "")
    if not key:
        raise RuntimeError("SECRET_KEY nao definida no ambiente")
    return key


def admin_user() -> str:
    return os.environ.get("ADMIN_USER", "admin")


def admin_password_hash() -> str:
    return os.environ.get("ADMIN_PASSWORD_HASH", "")


def api_token() -> str:
    return os.environ.get("API_TOKEN", "")
