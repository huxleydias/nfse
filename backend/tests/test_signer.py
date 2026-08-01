import base64
import hashlib
import io
import os

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from lxml import etree

from app.nfse.signer import (
    CertificadoError,
    cert_key_to_temp_pem,
    cert_metadata,
    load_pfx,
    sign_rps_hash,
    sign_xml_enveloped,
)
from app.nfse.xml_builder import build_pedido_envio_rps
from app.nfse.xsd_validator import validar
from tests.conftest import SENHA_PFX
from tests.test_xml_builder import PRESTADOR, rps_base

DSIG = "{http://www.w3.org/2000/09/xmldsig#}"


class TestLoadPfx:
    def test_senha_correta(self, pfx_bytes):
        cert, key = load_pfx(pfx_bytes, SENHA_PFX)
        assert cert is not None and key is not None

    def test_senha_errada(self, pfx_bytes):
        with pytest.raises(CertificadoError):
            load_pfx(pfx_bytes, "senha-errada")

    def test_metadata(self, cert_e_chave):
        cert, _ = cert_e_chave
        meta = cert_metadata(cert)
        assert "EMPRESA TESTE" in meta["cn"]
        assert meta["dias_restantes"] > 300
        assert not meta["vencido"]


class TestSignRpsHash:
    def test_assinatura_verificavel(self, cert_e_chave):
        cert, key = cert_e_chave
        b64 = sign_rps_hash(key, "STRINGDETESTE")
        cert.public_key().verify(
            base64.b64decode(b64),
            b"STRINGDETESTE",
            asym_padding.PKCS1v15(),
            hashes.SHA1(),
        )


class TestSignXmlEnveloped:
    def test_documento_assinado_valida_no_xsd(self, cert_e_chave):
        cert, key = cert_e_chave
        root = build_pedido_envio_rps(PRESTADOR, rps_base(), "QUJD")
        sign_xml_enveloped(root, cert, key)
        validar(root, "PedidoEnvioRPS_v02.xsd")

    def test_digest_confere_com_doc_sem_signature(self, cert_e_chave):
        cert, key = cert_e_chave
        root = build_pedido_envio_rps(PRESTADOR, rps_base(), "QUJD")

        buf = io.BytesIO()
        etree.ElementTree(root).write_c14n(buf, exclusive=False, with_comments=False)
        digest_esperado = base64.b64encode(hashlib.sha1(buf.getvalue()).digest()).decode()

        sign_xml_enveloped(root, cert, key)
        digest_no_xml = root.find(f".//{DSIG}DigestValue").text
        assert digest_no_xml == digest_esperado

    def test_signature_value_verificavel(self, cert_e_chave):
        cert, key = cert_e_chave
        root = build_pedido_envio_rps(PRESTADOR, rps_base(), "QUJD")
        sign_xml_enveloped(root, cert, key)

        signed_info = root.find(f".//{DSIG}SignedInfo")
        buf = io.BytesIO()
        etree.ElementTree(signed_info).write_c14n(buf, exclusive=False, with_comments=False)
        sig_b64 = root.find(f".//{DSIG}SignatureValue").text
        cert.public_key().verify(
            base64.b64decode(sig_b64),
            buf.getvalue(),
            asym_padding.PKCS1v15(),
            hashes.SHA1(),
        )


class TestTempPem:
    def test_gera_e_carrega(self, cert_e_chave):
        cert, key = cert_e_chave
        cert_path, key_path = cert_key_to_temp_pem(cert, key)
        try:
            assert open(cert_path).read().startswith("-----BEGIN CERTIFICATE-----")
            assert "PRIVATE KEY" in open(key_path).read()
        finally:
            os.unlink(cert_path)
            os.unlink(key_path)
