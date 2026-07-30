"""Armazenamento do certificado A1: .pfx no volume, senha cifrada no banco."""
from pathlib import Path

from app.core.crypto import decrypt, encrypt
from app.core.settings import data_dir
from app.models.config_store import get_config, save_config

from .signer import CertificadoError, cert_metadata, load_pfx

ARQUIVO_PFX = "certs/certificado.pfx"


def salvar_certificado(session, pfx_bytes: bytes, senha: str) -> dict:
    """Valida carregando o PFX, grava no volume e cifra a senha no banco."""
    cert, _key = load_pfx(pfx_bytes, senha)  # levanta CertificadoError se invalido

    caminho = data_dir() / ARQUIVO_PFX
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(pfx_bytes)

    cfg = get_config(session)
    cfg["certificado"] = {"arquivo": ARQUIVO_PFX, "senha_cifrada": encrypt(senha)}
    save_config(session, cfg)
    return cert_metadata(cert)


def carregar_certificado(session):
    """Retorna (cert, private_key) do certificado configurado."""
    cfg = get_config(session)
    info = cfg.get("certificado")
    if not info:
        raise CertificadoError("Nenhum certificado configurado. Envie o .pfx na tela Certificado.")
    caminho = data_dir() / info["arquivo"]
    if not Path(caminho).exists():
        raise CertificadoError("Arquivo do certificado nao encontrado no volume.")
    senha = decrypt(info["senha_cifrada"])
    return load_pfx(caminho.read_bytes(), senha)


def metadata_certificado(session) -> dict | None:
    try:
        cert, _ = carregar_certificado(session)
    except CertificadoError:
        return None
    return cert_metadata(cert)
