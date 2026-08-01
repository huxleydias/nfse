"""Cliente SOAP do webservice LoteNFe da Prefeitura de Sao Paulo.

Endpoint novo (nfews) e o unico que aceita o layout v2 da reforma
tributaria. TLS mutuo com o certificado A1 do prestador.

Contrato extraido do WSDL do proprio endpoint
(https://nfews.prefeitura.sp.gov.br/lotenfe.asmx?WSDL, exige o certificado
para abrir). Tres detalhes que diferem do endpoint antigo e que fazem o
servidor recusar a chamada se errados:

1. targetNamespace e `http://www.prefeitura.sp.gov.br/nfe`, nao
   `.../nfe/ws/lotenfe`.
2. O elemento do corpo tem sufixo Request: `EnvioRPSRequest`, nao `EnvioRPS`.
3. Cada operacao tem seu proprio SOAPAction, em camelCase e sem seguir o
   nome do metodo ao pe da letra (TesteEnvioLoteRPS usa `testeenvio`).
   SOAPAction errado devolve HTTP 500 com soap:Fault
   "Server did not recognize the value of HTTP Header SOAPAction".
"""
import os

import requests

from .signer import cert_key_to_temp_pem

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
NFE_NS = "http://www.prefeitura.sp.gov.br/nfe"
URL_PADRAO = "https://nfews.prefeitura.sp.gov.br/lotenfe.asmx"

# operacao -> SOAPAction (valores exatos do WSDL)
SOAP_ACTIONS = {
    "EnvioRPS": "http://www.prefeitura.sp.gov.br/nfe/ws/envioRPS",
    "EnvioLoteRPS": "http://www.prefeitura.sp.gov.br/nfe/ws/envioLoteRPS",
    "TesteEnvioLoteRPS": "http://www.prefeitura.sp.gov.br/nfe/ws/testeenvio",
    "CancelamentoNFe": "http://www.prefeitura.sp.gov.br/nfe/ws/cancelamentoNFe",
    "ConsultaNFe": "http://www.prefeitura.sp.gov.br/nfe/ws/consultaNFe",
    "ConsultaNFeEmitidas": "http://www.prefeitura.sp.gov.br/nfe/ws/consultaNFeEmitidas",
    "ConsultaNFeRecebidas": "http://www.prefeitura.sp.gov.br/nfe/ws/consultaNFeRecebidas",
    "ConsultaLote": "http://www.prefeitura.sp.gov.br/nfe/ws/consultaLote",
    "ConsultaInformacoesLote": "http://www.prefeitura.sp.gov.br/nfe/ws/consultaInformacoesLote",
    "ConsultaCNPJ": "http://www.prefeitura.sp.gov.br/nfe/ws/consultaCNPJ",
}

VERSAO_SCHEMA = 2
TIMEOUT_SEG = 60


class PrefeituraIndisponivelError(Exception):
    pass


def montar_envelope(metodo: str, xml_pedido: str) -> str:
    """Envelope SOAP 1.1 conforme o WSDL: elemento <MetodoRequest> no
    namespace da prefeitura, com VersaoSchema e MensagemXML em CDATA."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<soap:Envelope xmlns:soap="{SOAP_NS}">\n'
        "  <soap:Body>\n"
        f'    <{metodo}Request xmlns="{NFE_NS}">\n'
        f"      <VersaoSchema>{VERSAO_SCHEMA}</VersaoSchema>\n"
        f"      <MensagemXML><![CDATA[{xml_pedido}]]></MensagemXML>\n"
        f"    </{metodo}Request>\n"
        "  </soap:Body>\n"
        "</soap:Envelope>"
    )


class SoapClient:
    def __init__(self, cert, private_key, url: str = URL_PADRAO):
        self._cert = cert
        self._key = private_key
        self._url = url

    def _post(self, metodo: str, xml_pedido: str) -> str:
        try:
            soap_action = SOAP_ACTIONS[metodo]
        except KeyError:
            raise ValueError(f"Metodo SOAP desconhecido: {metodo}")

        envelope = montar_envelope(metodo, xml_pedido)
        cert_path, key_path = cert_key_to_temp_pem(self._cert, self._key)
        try:
            resposta = requests.post(
                self._url,
                data=envelope.encode("utf-8"),
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": f'"{soap_action}"',
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
