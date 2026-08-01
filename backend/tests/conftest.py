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


# Fixtures de API compartilhadas entre os testes de rotas.
import io  # noqa: E402

import bcrypt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def api(tmp_path, monkeypatch, pfx_bytes):
    hash_ = bcrypt.hashpw(b"senha-forte", bcrypt.gensalt()).decode()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "chave-de-teste-para-fernet-e-sessao")
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", hash_)
    monkeypatch.setenv("API_TOKEN", "token-api-de-teste-com-32-chars-ok")

    from app.core import db
    db.reset_engine_para_testes()

    from app.core import security
    security.login_limiter._hits.clear()

    from app.main import app
    with TestClient(app, base_url="https://testserver") as client:
        yield client
    db.reset_engine_para_testes()


@pytest.fixture
def api_logada(api):
    r = api.post("/api/auth/login", json={"usuario": "admin", "senha": "senha-forte"})
    assert r.status_code == 200
    return api


@pytest.fixture
def api_configurada(api_logada, pfx_bytes, monkeypatch):
    """Sessao logada, certificado enviado, config de prestador e servico pronta."""
    api = api_logada
    r = api.post(
        "/api/certificado",
        files={"arquivo": ("cert.pfx", io.BytesIO(pfx_bytes), "application/x-pkcs12")},
        data={"senha": SENHA_PFX},
    )
    assert r.status_code == 200
    r = api.put("/api/config", json={
        "prestador": {
            "cnpj": "11222333000181",
            "inscricao_municipal": "12345678",
            "razao_social": "EMPRESA EXEMPLO LTDA",
            "email": "contato@exemplo.com.br",
        },
        "servicos": {
            "05762": {
                "descricao_padrao": "Treinamento",
                "aliquota": 0.02, "iss_retido": False,
                "nbs": "000000000", "c_class_trib": "000001", "c_ind_op": "000000",
                "fin_nfse": 0, "ind_final": 1, "ind_dest": 0,
            }
        },
        "modo_teste": False,
    })
    assert r.status_code == 200

    from tests.test_emitter import ClientFake, resposta_sucesso

    fake = ClientFake(resposta_envio=resposta_sucesso())
    monkeypatch.setattr(
        "app.api.notas.SoapClient", lambda cert, key: fake
    )
    api.soap_fake = fake
    return api


