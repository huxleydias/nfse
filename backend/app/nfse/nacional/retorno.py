"""Leitura da NFS-e autorizada e do evento devolvidos pela Sefin Nacional."""
from lxml import etree

from app.nfse.parser import RespostaInvalidaError

from . import NS
from .cliente import _campo, descompactar

_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)


def _xml_da_resposta(corpo: dict, campo: str) -> bytes:
    dados = _campo(corpo, campo.lower())
    if not dados:
        raise RespostaInvalidaError(f"Resposta do Sistema Nacional sem {campo}")
    try:
        return descompactar(dados)
    except (OSError, ValueError) as e:
        raise RespostaInvalidaError(f"{campo} nao e GZip + Base64 valido: {e}") from e


def xml_nfse(corpo: dict) -> bytes:
    return _xml_da_resposta(corpo, "nfseXmlGZipB64")


def xml_evento(corpo: dict) -> bytes:
    return _xml_da_resposta(corpo, "eventoXmlGZipB64")


def ler_nfse(xml: bytes) -> dict:
    """Chave de acesso (Id sem o prefixo NFS), numero e situacao da NFS-e."""
    try:
        root = etree.fromstring(xml, parser=_PARSER)
    except etree.XMLSyntaxError as e:
        raise RespostaInvalidaError(f"XML da NFS-e invalido: {e}") from e
    inf = root if root.tag == f"{{{NS}}}infNFSe" else root.find(f"{{{NS}}}infNFSe")
    if inf is None or not (inf.get("Id") or "").startswith("NFS"):
        raise RespostaInvalidaError("XML da NFS-e sem infNFSe/@Id")
    return {
        "chave_acesso": inf.get("Id")[3:],
        "numero_nfse": inf.findtext(f"{{{NS}}}nNFSe"),
        "c_stat": inf.findtext(f"{{{NS}}}cStat"),
        "dh_proc": inf.findtext(f"{{{NS}}}dhProc"),
    }
