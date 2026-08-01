import pytest
import requests

from app.nfse.soap_client import (
    PrefeituraIndisponivelError,
    SoapClient,
    montar_envelope,
)


class RespostaFake:
    def __init__(self, ok=True, status_code=200, text="<ok/>"):
        self.ok = ok
        self.status_code = status_code
        self.text = text


@pytest.fixture
def client(cert_e_chave):
    cert, key = cert_e_chave
    return SoapClient(cert, key, url="https://exemplo.test/lotenfe.asmx")


class TestMontarEnvelope:
    def test_estrutura_conforme_wsdl(self):
        env = montar_envelope("EnvioRPS", "<PedidoEnvioRPS/>")
        # Elemento com sufixo Request, no namespace .../nfe (nao .../nfe/ws/lotenfe)
        assert '<EnvioRPSRequest xmlns="http://www.prefeitura.sp.gov.br/nfe">' in env
        assert "</EnvioRPSRequest>" in env
        assert "<VersaoSchema>2</VersaoSchema>" in env
        assert "<![CDATA[<PedidoEnvioRPS/>]]>" in env
        assert "lotenfe" not in env

    def test_consulta_emitidas(self):
        env = montar_envelope("ConsultaNFeEmitidas", "<x/>")
        assert "<ConsultaNFeEmitidasRequest" in env


class TestSoapActions:
    def test_valores_do_wsdl(self):
        from app.nfse.soap_client import SOAP_ACTIONS
        assert SOAP_ACTIONS["EnvioRPS"] == "http://www.prefeitura.sp.gov.br/nfe/ws/envioRPS"
        assert SOAP_ACTIONS["ConsultaNFeEmitidas"] == (
            "http://www.prefeitura.sp.gov.br/nfe/ws/consultaNFeEmitidas"
        )
        # TesteEnvioLoteRPS nao segue o nome do metodo
        assert SOAP_ACTIONS["TesteEnvioLoteRPS"] == (
            "http://www.prefeitura.sp.gov.br/nfe/ws/testeenvio"
        )
        assert SOAP_ACTIONS["CancelamentoNFe"] == (
            "http://www.prefeitura.sp.gov.br/nfe/ws/cancelamentoNFe"
        )


class TestSoapClient:
    def test_envio_rps_usa_metodo_certo(self, client, monkeypatch):
        capturado = {}

        def post_fake(url, data=None, headers=None, cert=None, timeout=None):
            capturado["data"] = data.decode()
            capturado["headers"] = headers
            capturado["cert"] = cert
            return RespostaFake()

        monkeypatch.setattr(requests, "post", post_fake)
        client.envio_rps("<x/>")
        assert "<EnvioRPSRequest" in capturado["data"]
        assert capturado["headers"]["SOAPAction"] == (
            '"http://www.prefeitura.sp.gov.br/nfe/ws/envioRPS"'
        )
        assert capturado["cert"] is not None

    def test_modo_teste_usa_teste_envio_lote(self, client, monkeypatch):
        capturado = {}

        def post_fake(url, data=None, headers=None, **kw):
            capturado["data"] = data.decode()
            capturado["headers"] = headers
            return RespostaFake()

        monkeypatch.setattr(requests, "post", post_fake)
        client.teste_envio_lote_rps("<x/>")
        assert "<TesteEnvioLoteRPSRequest" in capturado["data"]
        assert capturado["headers"]["SOAPAction"] == (
            '"http://www.prefeitura.sp.gov.br/nfe/ws/testeenvio"'
        )

    def test_consulta_periodo_usa_consulta_emitidas(self, client, monkeypatch):
        capturado = {}

        def post_fake(url, data=None, headers=None, **kw):
            capturado["data"] = data.decode()
            capturado["headers"] = headers
            return RespostaFake()

        monkeypatch.setattr(requests, "post", post_fake)
        client.consulta_nfe_periodo("<x/>")
        assert "<ConsultaNFeEmitidasRequest" in capturado["data"]
        assert capturado["headers"]["SOAPAction"] == (
            '"http://www.prefeitura.sp.gov.br/nfe/ws/consultaNFeEmitidas"'
        )

    def test_cancelamento(self, client, monkeypatch):
        capturado = {}

        def post_fake(url, data=None, headers=None, **kw):
            capturado["data"] = data.decode()
            capturado["headers"] = headers
            return RespostaFake()

        monkeypatch.setattr(requests, "post", post_fake)
        client.cancelamento_nfe("<x/>")
        assert "<CancelamentoNFeRequest" in capturado["data"]
        assert capturado["headers"]["SOAPAction"] == (
            '"http://www.prefeitura.sp.gov.br/nfe/ws/cancelamentoNFe"'
        )

    def test_timeout_vira_prefeitura_indisponivel(self, client, monkeypatch):
        def post_fake(*a, **kw):
            raise requests.exceptions.Timeout("timeout")

        monkeypatch.setattr(requests, "post", post_fake)
        with pytest.raises(PrefeituraIndisponivelError):
            client.envio_rps("<x/>")

    def test_http_500_vira_prefeitura_indisponivel(self, client, monkeypatch):
        monkeypatch.setattr(
            requests, "post",
            lambda *a, **kw: RespostaFake(ok=False, status_code=500, text="erro interno"),
        )
        with pytest.raises(PrefeituraIndisponivelError) as exc:
            client.envio_rps("<x/>")
        assert "500" in str(exc.value)
