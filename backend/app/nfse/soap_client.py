"""Cliente SOAP do webservice LoteNFe da Prefeitura de Sao Paulo.

Endpoint novo (nfews) e o unico que aceita o layout v2 da reforma
tributaria. TLS mutuo com o certificado A1 do prestador.
"""
import os

import requests

from .signer import cert_key_to_temp_pem

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
WS_NS = "http://www.prefeitura.sp.gov.br/nfe/ws/lotenfe"
URL_PADRAO = "https://nfews.prefeitura.sp.gov.br/lotenfe.asmx"

VERSAO_SCHEMA = 2
TIMEOUT_SEG = 60


class PrefeituraIndisponivelError(Exception):
    pass


def montar_envelope(metodo: str, xml_pedido: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<soap:Envelope xmlns:soap="{SOAP_NS}" xmlns:nfe="{WS_NS}">\n'
        "  <soap:Body>\n"
        f"    <nfe:{metodo}>\n"
        f"      <nfe:VersaoSchema>{VERSAO_SCHEMA}</nfe:VersaoSchema>\n"
        f"      <nfe:MensagemXML><![CDATA[{xml_pedido}]]></nfe:MensagemXML>\n"
        f"    </nfe:{metodo}>\n"
        "  </soap:Body>\n"
        "</soap:Envelope>"
    )


class SoapClient:
    def __init__(self, cert, private_key, url: str = URL_PADRAO):
        self._cert = cert
        self._key = private_key
        self._url = url

    def _post(self, metodo: str, xml_pedido: str) -> str:
        envelope = montar_envelope(metodo, xml_pedido)
        cert_path, key_path = cert_key_to_temp_pem(self._cert, self._key)
        try:
            resposta = requests.post(
                self._url,
                data=envelope.encode("utf-8"),
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": f'"{WS_NS}/{metodo}"',
                },
                cert=(cert_path, key_path),
                timeout=TIMEOUT_SEG,
            )
        except requests.exceptions.RequestException as e:
            raise PrefeituraIndisponivelError(
                f"Falha de comunicacao com a prefeitura: {e}"
            ) from e
        finally:
            os.unlink(cert_path)
            os.unlink(key_path)

        if not resposta.ok:
            raise PrefeituraIndisponivelError(
                f"Prefeitura respondeu HTTP {resposta.status_code}: "
                f"{resposta.text[:500]}"
            )
        return resposta.text

    def envio_rps(self, xml_pedido: str) -> str:
        return self._post("EnvioRPS", xml_pedido)

    def teste_envio_lote_rps(self, xml_pedido: str) -> str:
        """Valida o lote na prefeitura sem emitir nota (modo teste)."""
        return self._post("TesteEnvioLoteRPS", xml_pedido)

    def consulta_nfe(self, xml_pedido: str) -> str:
        return self._post("ConsultaNFe", xml_pedido)

    def consulta_nfe_periodo(self, xml_pedido: str) -> str:
        return self._post("ConsultaNFeEmitidas", xml_pedido)

    def cancelamento_nfe(self, xml_pedido: str) -> str:
        return self._post("CancelamentoNFe", xml_pedido)
