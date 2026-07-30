"""Cifra da senha do certificado: Fernet com chave derivada da SECRET_KEY.

A senha nunca fica em texto puro em disco, banco, logs ou respostas.
"""
import base64
import hashlib

from cryptography.fernet import Fernet

from .settings import secret_key


def _fernet() -> Fernet:
    chave = hashlib.sha256(secret_key().encode()).digest()
    return Fernet(base64.urlsafe_b64encode(chave))


def encrypt(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def decrypt(cifrado: str) -> str:
    return _fernet().decrypt(cifrado.encode()).decode()
