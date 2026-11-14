"""XMLDSig enveloped por referencia ao Id (infDPS, infPedReg).

Diferente da assinatura do webservice de SP, que cobre o documento inteiro
(URI vazia): no nacional a Reference aponta para o Id do grupo assinado e a
Signature entra como irma dele, dentro da raiz.

A Signature vai sem prefixo (namespace padrao do xmldsig): o Sistema Nacional
recusa prefixo de namespace na area de dados (E1228).

Algoritmo: bibliotecas abertas que emitem em producao usam RSA-SHA256; uma
usa RSA-SHA1. ALGORITMO_PADRAO fica numa constante para a troca ser de uma
linha se a homologacao recusar com E0714.
"""
import base64
import hashlib

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.serialization import Encoding
from lxml import etree

DS = "http://www.w3.org/2000/09/xmldsig#"
C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"

ALGORITMOS = {
    "sha256": {
        "hash": hashes.SHA256,
        "digest": hashlib.sha256,
        "signature_method": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
        "digest_method": "http://www.w3.org/2001/04/xmlenc#sha256",
    },
    "sha1": {
        "hash": hashes.SHA1,
        "digest": hashlib.sha1,
        "signature_method": "http://www.w3.org/2000/09/xmldsig#rsa-sha1",
        "digest_method": "http://www.w3.org/2000/09/xmldsig#sha1",
    },
}
ALGORITMO_PADRAO = "sha256"


def _c14n(element) -> bytes:
    """C14N inclusiva do elemento tratado como documento isolado.

    O c14n de subarvore do lxml emite `xmlns=""` espurio em alguns filhos
    (reset de namespace), e a assinatura sai diferente da que um verificador
    padrao calcula. Reserializar e reparsear o elemento sozinho preserva os
    namespaces herdados e gera a forma canonica correta.
    """
    isolado = etree.fromstring(etree.tostring(element, with_tail=False))
    return etree.tostring(isolado, method="c14n", exclusive=False, with_comments=False)


def _ds(parent, tag: str, **attrs):
    el = etree.SubElement(parent, f"{{{DS}}}{tag}")
    for chave, valor in attrs.items():
        el.set(chave, valor)
    return el


def assinar(root: etree._Element, elemento: etree._Element, cert, private_key,
            algoritmo: str = ALGORITMO_PADRAO) -> etree._Element:
    """Assina `elemento` (que precisa ter atributo Id) e anexa a Signature
    ao final de `root`."""
    alg = ALGORITMOS[algoritmo]
    ref_id = elemento.get("Id")
    if not ref_id:
        raise ValueError("Elemento a assinar precisa do atributo Id")

    digest = base64.b64encode(alg["digest"](_c14n(elemento)).digest()).decode()

    signature = etree.SubElement(root, f"{{{DS}}}Signature", nsmap={None: DS})
    signed_info = _ds(signature, "SignedInfo")
    _ds(signed_info, "CanonicalizationMethod", Algorithm=C14N)
    _ds(signed_info, "SignatureMethod", Algorithm=alg["signature_method"])
    ref = _ds(signed_info, "Reference", URI=f"#{ref_id}")
    transforms = _ds(ref, "Transforms")
    _ds(transforms, "Transform", Algorithm=ENVELOPED)
    _ds(transforms, "Transform", Algorithm=C14N)
    _ds(ref, "DigestMethod", Algorithm=alg["digest_method"])
    _ds(ref, "DigestValue").text = digest

    assinatura = private_key.sign(
        _c14n(signed_info), asym_padding.PKCS1v15(), alg["hash"]()
    )
    _ds(signature, "SignatureValue").text = base64.b64encode(assinatura).decode()
    key_info = _ds(signature, "KeyInfo")
    x509 = _ds(key_info, "X509Data")
    _ds(x509, "X509Certificate").text = base64.b64encode(
        cert.public_bytes(Encoding.DER)
    ).decode()
    return root
