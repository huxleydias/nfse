import pytest


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "chave-de-teste-para-fernet-e-sessao")
    from app.core import db
    db.reset_engine_para_testes()
    db.init_db()
    s = db.get_session()
    yield s
    s.close()
    db.reset_engine_para_testes()


class TestNota:
    def test_crud(self, session):
        from app.models.nota import Nota
        nota = Nota(tomador_nome="Fulano", valor=599.0, status="autorizada")
        session.add(nota)
        session.commit()
        assert nota.id is not None
        assert session.query(Nota).count() == 1

    def test_ref_externa_unica(self, session):
        from sqlalchemy.exc import IntegrityError
        from app.models.nota import Nota
        session.add(Nota(ref_externa="woo-1", valor=1.0))
        session.commit()
        session.add(Nota(ref_externa="woo-1", valor=2.0))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_to_dict_sem_xml_por_padrao(self, session):
        from app.models.nota import Nota
        nota = Nota(valor=1.0, xml_enviado="<x/>")
        session.add(nota)
        session.commit()
        assert "xml_enviado" not in nota.to_dict()
        assert nota.to_dict(com_xml=True)["xml_enviado"] == "<x/>"


class TestConfigStore:
    def test_default_seed(self, session):
        from app.models.config_store import get_config
        cfg = get_config(session)
        assert cfg["modo_teste"] is True
        assert cfg["serie_rps"] == "PM"
        assert cfg["proximo_numero_rps"] == 8

    def test_save_e_get(self, session):
        from app.models.config_store import get_config, save_config
        cfg = get_config(session)
        cfg["prestador"]["cnpj"] = "11222333000181"
        save_config(session, cfg)
        assert get_config(session)["prestador"]["cnpj"] == "11222333000181"

    def test_alocar_numero_rps_sequencial(self, session):
        from app.models.config_store import alocar_numero_rps, get_config
        assert alocar_numero_rps(session) == 8
        assert alocar_numero_rps(session) == 9
        assert get_config(session)["proximo_numero_rps"] == 10


class TestCrypto:
    def test_roundtrip(self, session):
        from app.core.crypto import decrypt, encrypt
        assert decrypt(encrypt("senha-do-cert")) == "senha-do-cert"

    def test_cifrado_nao_e_texto_puro(self, session):
        from app.core.crypto import encrypt
        assert "senha-do-cert" not in encrypt("senha-do-cert")


class TestCertStore:
    def test_salvar_e_carregar(self, session, pfx_bytes):
        from app.nfse.cert_store import (
            carregar_certificado,
            metadata_certificado,
            salvar_certificado,
        )
        from tests.conftest import SENHA_PFX
        meta = salvar_certificado(session, pfx_bytes, SENHA_PFX)
        assert "EMPRESA TESTE" in meta["cn"]
        cert, key = carregar_certificado(session)
        assert cert is not None
        assert metadata_certificado(session)["vencido"] is False

    def test_senha_errada_no_upload(self, session, pfx_bytes):
        from app.nfse.cert_store import salvar_certificado
        from app.nfse.signer import CertificadoError
        with pytest.raises(CertificadoError):
            salvar_certificado(session, pfx_bytes, "senha-errada")

    def test_sem_certificado(self, session):
        from app.nfse.cert_store import carregar_certificado, metadata_certificado
        from app.nfse.signer import CertificadoError
        assert metadata_certificado(session) is None
        with pytest.raises(CertificadoError):
            carregar_certificado(session)
