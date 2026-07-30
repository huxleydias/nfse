from pathlib import Path

import pytest

from app.nfse.parser import (
    RespostaInvalidaError,
    extrair_retorno_soap,
    parse_retorno_cancelamento,
    parse_retorno_consulta,
    parse_retorno_envio,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(nome: str) -> str:
    return (FIXTURES / nome).read_text()


def envelopar_soap(retorno_xml: str, metodo: str = "EnvioRPS") -> str:
    escapado = retorno_xml.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body>"
        f'<{metodo}Response xmlns="http://www.prefeitura.sp.gov.br/nfe/ws/lotenfe">'
        f"<RetornoXML>{escapado}</RetornoXML>"
        f"</{metodo}Response>"
        "</soap:Body></soap:Envelope>"
    )


class TestExtrairRetornoSoap:
    def test_extrai_retorno_xml(self):
        retorno = fixture("retorno_envio_sucesso.xml")
        soap = envelopar_soap(retorno)
        extraido = extrair_retorno_soap(soap)
        assert "RetornoEnvioRPS" in extraido

    def test_envelope_sem_retorno(self):
        with pytest.raises(RespostaInvalidaError):
            extrair_retorno_soap(
                '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
                "<soap:Body></soap:Body></soap:Envelope>"
            )

    def test_html_de_erro(self):
        with pytest.raises(RespostaInvalidaError):
            extrair_retorno_soap("<html><body>erro 500</body></html")


class TestParseRetornoEnvio:
    def test_sucesso(self):
        r = parse_retorno_envio(fixture("retorno_envio_sucesso.xml"))
        assert r["sucesso"] is True
        assert r["numero_nfse"] == "1234"
        assert r["codigo_verificacao"] == "ABCD1234"
        assert r["numero_rps"] == "8"
        assert r["serie_rps"] == "PM"
        assert r["erros"] == []

    def test_erro(self):
        r = parse_retorno_envio(fixture("retorno_envio_erro.xml"))
        assert r["sucesso"] is False
        assert len(r["erros"]) == 2
        assert r["erros"][0]["codigo"] == "1002"
        assert "Schema" in r["erros"][0]["descricao"]
        assert r["numero_nfse"] is None


class TestParseRetornoCancelamento:
    def test_ok(self):
        r = parse_retorno_cancelamento(fixture("retorno_cancelamento_ok.xml"))
        assert r["sucesso"] is True


class TestParseRetornoConsulta:
    def test_duas_notas(self):
        notas = parse_retorno_consulta(fixture("retorno_consulta_periodo.xml"))
        assert len(notas) == 2
        n1, n2 = notas
        assert n1["numero_nfse"] == "1234"
        assert n1["valor"] == 599.0
        assert n1["tomador_doc"] == "11144477735"
        assert n1["numero_rps"] == "8"
        assert n1["status"] == "N"
        assert n2["status"] == "C"
        assert n2["valor"] == 10000.0
        assert n2["tomador_doc"] == "04891850000188"
        assert n2["numero_rps"] is None
