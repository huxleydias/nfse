"""Certificado A1 e assinaturas criptograficas.

Duas assinaturas conforme manual v3.3.7:
1. sign_rps_hash: string de assinatura do RPS, RSA PKCS1v15 + SHA1, base64.
2. sign_xml_enveloped: XMLDSig enveloped (C14N inclusivo, digest SHA1,
   RSA-SHA1, KeyInfo EndCertOnly). Portado do emissor SOAP que funcionou
   em producao (abril/2026).
"""
import base64
import hashlib
import io
import tempfile
from datetime import datetime, timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree

XMLDSIG_NS = "http://www.w3.org/2000/09/xmldsig#"


class CertificadoError(Exception):
    pass


def load_pfx(pfx_bytes: bytes, senha: str):
    """Carrega PFX. Retorna (cert, private_key). Erro claro se senha errada."""
    try:
        key, cert, _extras = pkcs12.load_key_and_certificates(
            pfx_bytes, senha.encode()
        )
    except ValueError as e:
        raise CertificadoError(f"Nao foi possivel abrir o certificado: {e}") from e
    if cert is None or key is None:
        raise CertificadoError("Arquivo PFX sem certificado ou chave privada")
    return cert, key


def cert_metadata(cert) -> dict:
    """Metadados seguros para exibir na UI (nunca a chave ou senha)."""
    validade = cert.not_valid_after_utc
    agora = datetime.now(timezone.utc)
    cn = ""
    for attr in cert.subject:
        if attr.rfc4514_attribute_name == "CN":
            cn = str(attr.value)
    emissor = ""
    for attr in cert.issuer:
        if attr.rfc4514_attribute_name == "CN":
            emissor = str(attr.value)
    return {
        "cn": cn,
        "emissor": emissor,
        "valido_ate": validade.isoformat(),
        "dias_restantes": (validade - agora).days,
        "vencido": validade < agora,
    }


def sign_rps_hash(private_key, sign_string: str) -> str:
    """SHA1 + RSA PKCS1v15 da string de assinatura do RPS. Base64."""
    sig = private_key.sign(
        sign_string.encode("ascii"), asym_padding.PKCS1v15(), hashes.SHA1()
    )
    return base64.b64encode(sig).decode("ascii")


def _c14n(element) -> bytes:
    buf = io.BytesIO()
    etree.ElementTree(element).write_c14n(buf, exclusive=False, with_comments=False)
    return buf.getvalue()


def _cert_der_b64(cert) -> str:
    return base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()


def sign_xml_enveloped(root: etree._Element, cert, private_key) -> etree._Element:
    """XMLDSig enveloped sobre o documento completo."""
    doc_c14n = _c14n(root)
    digest_b64 = base64.b64encode(hashlib.sha1(doc_c14n).digest()).decode()

    sig_el = etree.SubElement(root, f"{{{XMLDSIG_NS}}}Signature")
    signed_info = etree.SubElement(sig_el, f"{{{XMLDSIG_NS}}}SignedInfo")

    c14n_meth = etree.SubElement(signed_info, f"{{{XMLDSIG_NS}}}CanonicalizationMethod")
    c14n_meth.set("Algorithm", "http://www.w3.org/TR/2001/REC-xml-c14n-20010315")
    sig_meth = etree.SubElement(signed_info, f"{{{XMLDSIG_NS}}}SignatureMethod")
    sig_meth.set("Algorithm", "http://www.w3.org/2000/09/xmldsig#rsa-sha1")

    ref = etree.SubElement(signed_info, f"{{{XMLDSIG_NS}}}Reference")
    ref.set("URI", "")
    transforms = etree.SubElement(ref, f"{{{XMLDSIG_NS}}}Transforms")
    t1 = etree.SubElement(transforms, f"{{{XMLDSIG_NS}}}Transform")
    t1.set("Algorithm", "http://www.w3.org/2000/09/xmldsig#enveloped-signature")
    t2 = etree.SubElement(transforms, f"{{{XMLDSIG_NS}}}Transform")
    t2.set("Algorithm", "http://www.w3.org/TR/2001/REC-xml-c14n-20010315")
    dm = etree.SubElement(ref, f"{{{XMLDSIG_NS}}}DigestMethod")
    dm.set("Algorithm", "http://www.w3.org/2000/09/xmldsig#sha1")
    dv = etree.SubElement(ref, f"{{{XMLDSIG_NS}}}DigestValue")
    dv.text = digest_b64

    signed_info_c14n = _c14n(signed_info)
    sig_bytes = private_key.sign(
        signed_info_c14n, asym_padding.PKCS1v15(), hashes.SHA1()
    )
    sig_val = etree.SubElement(sig_el, f"{{{XMLDSIG_NS}}}SignatureValue")
    sig_val.text = base64.b64encode(sig_bytes).decode()

    key_info = etree.SubElement(sig_el, f"{{{XMLDSIG_NS}}}KeyInfo")
    x509data = etree.SubElement(key_info, f"{{{XMLDSIG_NS}}}X509Data")
    x509cert = etree.SubElement(x509data, f"{{{XMLDSIG_NS}}}X509Certificate")
    x509cert.text = _cert_der_b64(cert)

    return root


def cert_key_to_temp_pem(cert, private_key) -> tuple[str, str]:
    """Escreve cert e chave em PEMs temporarios para TLS mutuo do requests.
    Chamador deve remover os arquivos apos o uso."""
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
        f.write(cert_pem)
        cert_path = f.name
    with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
        f.write(key_pem)
        key_path = f.name
    return cert_path, key_path
