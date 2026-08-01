"""PDF oficial da NFS-e, servido pela propria prefeitura.

O webservice LoteNFe devolve XML, nunca PDF. Quem gera o documento impresso
e um endpoint publico do portal da NF-e paulistana:

    https://nfe.prefeitura.sp.gov.br/contribuinte/notaprintpdf.aspx
        ?inscricao={ccm}&nf={numero}&verificacao={codigo}

E publico de proposito (qualquer um com o codigo de verificacao confere a
nota), entao nao exige certificado nem login. Buscamos server-side para nao
expor a inscricao municipal na URL do navegador e para entregar o arquivo
com um nome decente.
"""
import requests

URL_PDF = "https://nfe.prefeitura.sp.gov.br/contribuinte/notaprintpdf.aspx"
TIMEOUT_SEG = 60


class PdfIndisponivelError(Exception):
    pass


def montar_url_pdf(inscricao: str, numero_nfse: str, codigo_verificacao: str) -> str:
    from .utils import so_digitos

    return (
        f"{URL_PDF}?inscricao={so_digitos(inscricao)}"
        f"&nf={so_digitos(numero_nfse)}"
        f"&verificacao={codigo_verificacao}"
    )


def baixar_pdf(inscricao: str, numero_nfse: str, codigo_verificacao: str) -> bytes:
    url = montar_url_pdf(inscricao, numero_nfse, codigo_verificacao)
    try:
        resposta = requests.get(url, timeout=TIMEOUT_SEG)
    except requests.exceptions.RequestException as e:
        raise PdfIndisponivelError(f"Falha ao buscar o PDF na prefeitura: {e}") from e

    if not resposta.ok:
        raise PdfIndisponivelError(
            f"Prefeitura respondeu HTTP {resposta.status_code} ao pedir o PDF"
        )
    # A prefeitura devolve HTML de erro com status 200 quando a chave nao bate
    if not resposta.content.startswith(b"%PDF"):
        raise PdfIndisponivelError(
            "Prefeitura nao devolveu um PDF. Confira numero da nota e codigo "
            "de verificacao."
        )
    return resposta.content
