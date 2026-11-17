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

# Dois leiautes convivem ate 30/11/2026 (comunicados CGNFS-e de 20/10 e
# 29/10/2026): a producao segue a NT 004 (com o tpRetPisCofins da NT 007) e a
# producao restrita ja roda a NT 009, que entra na producao em 01/12/2026. Na
# DPS que este sistema monta, a unica diferenca e o finNFSe obrigatorio em
# infDPS. Se o governo adiar a data, basta mudar INICIO_NT009_PRODUCAO.
LEIAUTE_NT004 = "nt004"
LEIAUTE_NT009 = "nt009"
INICIO_NT009_PRODUCAO = date(2026, 12, 1)

_PASTA_SCHEMAS = {
    LEIAUTE_NT004: "nacional/1.01",
    LEIAUTE_NT009: "nacional/1.01-nt009",
}


def leiaute_vigente(homologacao: bool, hoje: date) -> str:
    """Leiaute que o Sistema Nacional aceita hoje no ambiente de destino."""
    if homologacao or hoje >= INICIO_NT009_PRODUCAO:
        return LEIAUTE_NT009
    return LEIAUTE_NT004


def schema_dps(leiaute: str) -> str:
    return f"{_PASTA_SCHEMAS[leiaute]}/DPS_v1.01.xsd"


def schema_evento(leiaute: str) -> str:
    return f"{_PASTA_SCHEMAS[leiaute]}/pedRegEvento_v1.01.xsd"


SCHEMA_DPS = schema_dps(LEIAUTE_NT004)
SCHEMA_EVENTO = schema_evento(LEIAUTE_NT004)

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
