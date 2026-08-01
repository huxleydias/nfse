"""Fixtures compartilhadas: certificado A1 self-signed em memoria."""
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

SENHA_PFX = "senha-teste-123"


@pytest.fixture(scope="session")
def pfx_bytes():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "EMPRESA TESTE:11222333000181"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Empresa Teste"),
    ])
    agora = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - timedelta(days=1))
        .not_valid_after(agora + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(
        b"teste", key, cert, None,
        serialization.BestAvailableEncryption(SENHA_PFX.encode()),
    )


@pytest.fixture(scope="session")
def cert_e_chave(pfx_bytes):
    from app.nfse.signer import load_pfx
    return load_pfx(pfx_bytes, SENHA_PFX)
