"""Emissao no Sistema Nacional NFS-e (Sefin Nacional).

Optantes do Simples Nacional ME/EPP emitem so aqui para competencias a partir
de 01/11/2026 (Resolucao CGSN 191/2026). O leiaute e o da DPS v1.01, enviada
em JSON com o XML compactado em GZip + Base64, com TLS mutuo usando o mesmo
certificado A1 do ambiente municipal.
"""
from datetime import date, datetime, timedelta, timezone

NS = "http://www.sped.fazenda.gov.br/nfse"
VERSAO_LEIAUTE = "1.01"
VER_APLIC = "nfse-1.1"

SCHEMA_DPS = "nacional/1.01/DPS_v1.01.xsd"
SCHEMA_EVENTO = "nacional/1.01/pedRegEvento_v1.01.xsd"

# Brasilia nao tem horario de verao desde 2019: deslocamento fixo dispensa
# base de fusos no container.
FUSO_BRASILIA = timezone(timedelta(hours=-3))

AMBIENTE_PRODUCAO = "nacional"
AMBIENTE_HOMOLOGACAO = "nacional_homologacao"
AMBIENTES_NACIONAIS = (AMBIENTE_PRODUCAO, AMBIENTE_HOMOLOGACAO)

_CONSULTA_PUBLICA = {
    False: "https://www.nfse.gov.br/ConsultaPublica/",
    True: "https://www.producaorestrita.nfse.gov.br/ConsultaPublica/",
}


def agora_brasilia() -> datetime:
    return datetime.now(FUSO_BRASILIA).replace(microsecond=0)


def hoje_brasilia() -> date:
    return agora_brasilia().date()


def url_consulta_publica(chave_acesso: str, homologacao: bool = False) -> str:
    """Link oficial da nota, o mesmo do QR Code do DANFSe (NT 008).

    A API de geracao do DANFSe foi suspensa em 03/08/2026; o PDF oficial e
    baixado pela Consulta Publica.
    """
    return f"{_CONSULTA_PUBLICA[homologacao]}?tpc=1&chave={chave_acesso}"
