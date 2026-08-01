import io

import bcrypt
import pytest
from fastapi.testclient import TestClient

from tests.conftest import SENHA_PFX
from tests.test_emitter import ClientFake, resposta_sucesso
from tests.test_parser import envelopar_soap


@pytest.fixture
def api(tmp_path, monkeypatch, pfx_bytes):
    hash_ = bcrypt.hashpw(b"senha-forte", bcrypt.gensalt()).decode()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "chave-de-teste-para-fernet-e-sessao")
    monkeypatch.setenv("ADMIN_USER", "huxley")
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
    r = api.post("/api/auth/login", json={"usuario": "huxley", "senha": "senha-forte"})
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
            "cnpj": "37624983000147",
            "inscricao_municipal": "66467799",
            "razao_social": "PUNKMETRICS LTDA",
            "email": "contato@punkmetrics.com",
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

    fake = ClientFake(resposta_envio=resposta_sucesso())
    monkeypatch.setattr(
        "app.api.notas.SoapClient", lambda cert, key: fake
    )
    api.soap_fake = fake
    return api


PAYLOAD = {
    "tomador": {"cpf_cnpj": "111.444.777-35", "razao_social": "Fulano"},
    "servico": "05762",
    "valor": 599.0,
    "descricao": "Curso IA para Designers",
    "ref_externa": "woo-1",
}


class TestAuth:
    def test_login_ok(self, api):
        r = api.post("/api/auth/login", json={"usuario": "huxley", "senha": "senha-forte"})
        assert r.status_code == 200
        assert "nfse_sessao" in r.cookies

    def test_login_errado(self, api):
        r = api.post("/api/auth/login", json={"usuario": "huxley", "senha": "x"})
        assert r.status_code == 401

    def test_rate_limit(self, api):
        for _ in range(5):
            api.post("/api/auth/login", json={"usuario": "huxley", "senha": "x"})
        r = api.post("/api/auth/login", json={"usuario": "huxley", "senha": "x"})
        assert r.status_code == 429

    def test_rota_protegida_sem_auth(self, api):
        assert api.get("/api/notas").status_code == 401
        assert api.get("/api/config").status_code == 401

    def test_health_aberta(self, api):
        assert api.get("/api/health").status_code == 200


class TestEmissaoAPI:
    def test_emitir_com_sessao(self, api_configurada):
        r = api_configurada.post("/api/notas", json=PAYLOAD)
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["nota"]["numero_nfse"] == "1234"
        assert corpo["nota"]["status"] == "autorizada"

    def test_emitir_com_bearer(self, api_configurada):
        api_configurada.cookies.clear()
        r = api_configurada.post(
            "/api/notas", json={**PAYLOAD, "ref_externa": "woo-2"},
            headers={"Authorization": "Bearer token-api-de-teste-com-32-chars-ok"},
        )
        assert r.status_code == 200, r.text

    def test_payload_invalido_422(self, api_configurada):
        r = api_configurada.post("/api/notas", json={**PAYLOAD, "valor": -1})
        assert r.status_code == 422

    def test_cpf_invalido_422(self, api_configurada):
        r = api_configurada.post(
            "/api/notas",
            json={**PAYLOAD, "tomador": {"cpf_cnpj": "123"}},
        )
        assert r.status_code == 422

    def test_sem_certificado_409(self, api_logada):
        r = api_logada.post("/api/notas", json=PAYLOAD)
        assert r.status_code == 409
        assert "certificado" in r.json()["detail"].lower()

    def test_listar_e_detalhe(self, api_configurada):
        api_configurada.post("/api/notas", json=PAYLOAD)
        r = api_configurada.get("/api/notas")
        notas = r.json()["notas"]
        assert len(notas) == 1
        nota_id = notas[0]["id"]
        det = api_configurada.get(f"/api/notas/{nota_id}").json()["nota"]
        assert "xml_enviado" in det

    def test_cancelar(self, api_configurada):
        from pathlib import Path
        api_configurada.post("/api/notas", json=PAYLOAD)
        nota_id = api_configurada.get("/api/notas").json()["notas"][0]["id"]
        api_configurada.soap_fake.resposta_cancel = envelopar_soap(
            (Path(__file__).parent / "fixtures" / "retorno_cancelamento_ok.xml").read_text(),
            "CancelamentoNFe",
        )
        r = api_configurada.delete(f"/api/notas/{nota_id}")
        assert r.status_code == 200, r.text
        assert r.json()["nota"]["status"] == "cancelada"


class TestPdfAPI:
    def test_pdf_de_nota_autorizada(self, api_configurada, monkeypatch):
        import requests as req

        class R:
            ok, status_code, content = True, 200, b"%PDF-1.7 fake"

        monkeypatch.setattr(req, "get", lambda *a, **kw: R())
        api_configurada.post("/api/notas", json=PAYLOAD)
        nota_id = api_configurada.get("/api/notas").json()["notas"][0]["id"]

        r = api_configurada.get(f"/api/notas/{nota_id}/pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF")
        assert "inline" in r.headers["content-disposition"]

    def test_download_usa_attachment(self, api_configurada, monkeypatch):
        import requests as req

        class R:
            ok, status_code, content = True, 200, b"%PDF-1.7 fake"

        monkeypatch.setattr(req, "get", lambda *a, **kw: R())
        api_configurada.post("/api/notas", json=PAYLOAD)
        nota_id = api_configurada.get("/api/notas").json()["notas"][0]["id"]

        r = api_configurada.get(f"/api/notas/{nota_id}/pdf?download=true")
        assert "attachment" in r.headers["content-disposition"]
        assert "nfse-1234.pdf" in r.headers["content-disposition"]

    def test_nota_inexistente(self, api_configurada):
        assert api_configurada.get("/api/notas/9999/pdf").status_code == 404

    def test_nota_sem_numero_nfse(self, api_configurada):
        from app.core.db import get_session
        from app.models.nota import Nota
        s = get_session()
        nota = Nota(valor=1.0, status="erro")
        s.add(nota)
        s.commit()
        nota_id = nota.id
        s.close()
        r = api_configurada.get(f"/api/notas/{nota_id}/pdf")
        assert r.status_code == 409

    def test_pdf_exige_auth(self, api):
        assert api.get("/api/notas/1/pdf").status_code == 401


class TestCertificadoAPI:
    def test_upload_e_status(self, api_logada, pfx_bytes):
        r = api_logada.post(
            "/api/certificado",
            files={"arquivo": ("cert.pfx", io.BytesIO(pfx_bytes), "application/x-pkcs12")},
            data={"senha": SENHA_PFX},
        )
        assert r.status_code == 200
        assert "PUNKMETRICS TESTE" in r.json()["certificado"]["cn"]
        status = api_logada.get("/api/certificado").json()["certificado"]
        assert status["vencido"] is False

    def test_upload_senha_errada(self, api_logada, pfx_bytes):
        r = api_logada.post(
            "/api/certificado",
            files={"arquivo": ("cert.pfx", io.BytesIO(pfx_bytes), "application/x-pkcs12")},
            data={"senha": "errada"},
        )
        assert r.status_code == 422


class TestConfigAPI:
    def test_aliquota_em_percentual_barrada(self, api_configurada):
        # 2 significaria 200% no XML: erro de digitacao comum, barrado no save
        r = api_configurada.put("/api/config", json={
            "servicos": {"05762": {"aliquota": 2, "descricao_padrao": "x"}}
        })
        assert r.status_code == 422
        assert "0.02" in str(r.json()["detail"])

    def test_aliquota_em_fracao_aceita(self, api_configurada):
        r = api_configurada.put("/api/config", json={
            "servicos": {"05762": {"aliquota": 0.02, "descricao_padrao": "x"}}
        })
        assert r.status_code == 200

    def test_aliquota_negativa_barrada(self, api_configurada):
        r = api_configurada.put("/api/config", json={
            "servicos": {"05762": {"aliquota": -0.01}}
        })
        assert r.status_code == 422

    def test_get_nao_expoe_certificado(self, api_configurada):
        cfg = api_configurada.get("/api/config").json()
        assert "certificado" not in cfg

    def test_put_nao_sobrescreve_certificado(self, api_configurada):
        api_configurada.put("/api/config", json={"certificado": {"senha_cifrada": "hack"}})
        from app.core.db import get_session
        from app.models.config_store import get_config
        s = get_session()
        cfg = get_config(s)
        s.close()
        assert cfg["certificado"]["senha_cifrada"] != "hack"
