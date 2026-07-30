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
    def test_estrutura(self):
        env = montar_envelope("EnvioRPS", "<PedidoEnvioRPS/>")
        assert "<nfe:EnvioRPS>" in env
        assert "<nfe:VersaoSchema>2</nfe:VersaoSchema>" in env
        assert "<![CDATA[<PedidoEnvioRPS/>]]>" in env
        assert 'xmlns:nfe="http://www.prefeitura.sp.gov.br/nfe/ws/lotenfe"' in env


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
        assert "<nfe:EnvioRPS>" in capturado["data"]
        assert capturado["headers"]["SOAPAction"].endswith('/EnvioRPS"')
        assert capturado["cert"] is not None

    def test_modo_teste_usa_teste_envio_lote(self, client, monkeypatch):
        capturado = {}

        def post_fake(url, data=None, **kw):
            capturado["data"] = data.decode()
            return RespostaFake()

        monkeypatch.setattr(requests, "post", post_fake)
        client.teste_envio_lote_rps("<x/>")
        assert "<nfe:TesteEnvioLoteRPS>" in capturado["data"]

    def test_cancelamento(self, client, monkeypatch):
        capturado = {}
        monkeypatch.setattr(
            requests, "post",
            lambda url, data=None, **kw: capturado.update(data=data.decode()) or RespostaFake(),
        )
        client.cancelamento_nfe("<x/>")
        assert "<nfe:CancelamentoNFe>" in capturado["data"]

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
