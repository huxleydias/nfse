from datetime import date

import pytest
from lxml import etree

from app.nfse.xml_builder import build_pedido_envio_rps
from app.nfse.xsd_validator import validar, XSDValidationError
from tests.test_xml_builder import PRESTADOR, rps_base

DSIG = "http://www.w3.org/2000/09/xmldsig#"


def dummy_signature(root):
    """Signature sintaticamente valida conforme xmldsig-core-schema."""
    sig = etree.SubElement(root, f"{{{DSIG}}}Signature")
    si = etree.SubElement(sig, f"{{{DSIG}}}SignedInfo")
    etree.SubElement(si, f"{{{DSIG}}}CanonicalizationMethod",
                     Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315")
    etree.SubElement(si, f"{{{DSIG}}}SignatureMethod",
                     Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1")
    ref = etree.SubElement(si, f"{{{DSIG}}}Reference", URI="")
    transforms = etree.SubElement(ref, f"{{{DSIG}}}Transforms")
    etree.SubElement(transforms, f"{{{DSIG}}}Transform",
                     Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature")
    etree.SubElement(ref, f"{{{DSIG}}}DigestMethod",
                     Algorithm="http://www.w3.org/2000/09/xmldsig#sha1")
    etree.SubElement(ref, f"{{{DSIG}}}DigestValue").text = "QUJD"
    etree.SubElement(sig, f"{{{DSIG}}}SignatureValue").text = "QUJD"
    keyinfo = etree.SubElement(sig, f"{{{DSIG}}}KeyInfo")
    x509 = etree.SubElement(keyinfo, f"{{{DSIG}}}X509Data")
    etree.SubElement(x509, f"{{{DSIG}}}X509Certificate").text = "QUJD"
    return root


class TestValidarPedidoEnvioRPS:
    def test_xml_do_builder_valida(self):
        root = build_pedido_envio_rps(PRESTADOR, rps_base(), "QUJD")
        dummy_signature(root)
        validar(root, "PedidoEnvioRPS_v02.xsd")

    def test_sem_nbs_falha_citando_nbs(self):
        rps = rps_base()
        root = build_pedido_envio_rps(PRESTADOR, rps, "QUJD")
        dummy_signature(root)
        nbs = root.find(".//NBS")
        nbs.getparent().remove(nbs)
        with pytest.raises(XSDValidationError) as exc:
            validar(root, "PedidoEnvioRPS_v02.xsd")
        assert "NBS" in str(exc.value)

    def test_sem_ibscbs_falha(self):
        root = build_pedido_envio_rps(PRESTADOR, rps_base(), "QUJD")
        dummy_signature(root)
        ib = root.find(".//IBSCBS")
        ib.getparent().remove(ib)
        with pytest.raises(XSDValidationError):
            validar(root, "PedidoEnvioRPS_v02.xsd")

    def test_sem_signature_falha(self):
        root = build_pedido_envio_rps(PRESTADOR, rps_base(), "QUJD")
        with pytest.raises(XSDValidationError):
            validar(root, "PedidoEnvioRPS_v02.xsd")

    def test_lote_valida_no_xsd_de_lote(self):
        from app.nfse.xml_builder import build_pedido_envio_lote_rps
        root = build_pedido_envio_lote_rps(PRESTADOR, rps_base(), "QUJD")
        dummy_signature(root)
        validar(root, "PedidoEnvioLoteRPS_v02.xsd")

    def test_cclasstrib_curto_falha(self):
        rps = rps_base(fiscal={**rps_base()["fiscal"], "c_class_trib": "01"})
        root = build_pedido_envio_rps(PRESTADOR, rps, "QUJD")
        dummy_signature(root)
        with pytest.raises(XSDValidationError):
            validar(root, "PedidoEnvioRPS_v02.xsd")
