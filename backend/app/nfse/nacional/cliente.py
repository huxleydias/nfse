"""Cliente REST da Sefin Nacional (Emissor Publico Nacional, API do contribuinte).

Contrato (Swagger oficial, que so abre com certificado):
- POST /nfse com {"dpsXmlGZipB64"}: 201 com chaveAcesso e nfseXmlGZipB64;
  erro com {"erros": [MensagemProcessamento]}.
- GET /dps/{id}: chave de acesso da NFS-e gerada a partir da DPS; 404 se a
  DPS nao virou nota.
- GET /nfse/{chave}: NFS-e em nfseXmlGZipB64.
- POST /nfse/{chave}/eventos com {"pedidoRegistroEventoXmlGZipB64"}: 201 com
  eventoXmlGZipB64; erro com {"erro": MensagemProcessamento}.

Autenticacao por TLS mutuo com o certificado A1 ICP-Brasil do prestador.
"""
import base64
import gzip
import os

import requests

from app.nfse.signer import cert_key_to_temp_pem
from app.nfse.soap_client import PrefeituraIndisponivelError

URLS = {
    False: "https://sefin.nfse.gov.br/SefinNacional",
    True: "https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional",
}
TIMEOUT_SEG = 60


class SefinIndisponivelError(PrefeituraIndisponivelError):
    """Rede, timeout ou HTTP 5xx: nao se sabe se a DPS foi processada."""


class SefinCertificadoRecusadoError(PrefeituraIndisponivelError):
    """HTTP 403 sem mensagem de negocio: o TLS mutuo recusou o certificado."""


class SefinRecusouError(Exception):
    def __init__(self, erros: list[dict], status: int):
        self.erros = erros
        self.status = status
        super().__init__("; ".join(f"[{e['codigo']}] {e['descricao']}" for e in erros))


def compactar(xml: bytes) -> str:
    return base64.b64encode(gzip.compress(xml)).decode("ascii")


def descompactar(dados_b64: str) -> bytes:
    return gzip.decompress(base64.b64decode(dados_b64))


def _campo(item: dict, nome: str) -> str:
    """Le campo sem depender de maiuscula/minuscula (Codigo ou codigo)."""
    for chave, valor in item.items():
        if chave.lower() == nome:
            return "" if valor is None else str(valor)
    return ""


def normalizar_mensagens(corpo) -> list[dict]:
    """Converte erros/erro/alertas da API no formato do sistema:
    {codigo, descricao, complemento?}."""
    if not isinstance(corpo, dict):
        return []
    itens = []
    for chave, valor in corpo.items():
        if chave.lower() in ("erros", "erro", "alertas"):
            if isinstance(valor, list):
                itens.extend(v for v in valor if isinstance(v, dict))
            elif isinstance(valor, dict):
                itens.append(valor)
    mensagens = []
    for item in itens:
        msg = {
            "codigo": _campo(item, "codigo"),
            "descricao": _campo(item, "descricao") or _campo(item, "mensagem"),
        }
        complemento = _campo(item, "complemento")
        if complemento:
            msg["complemento"] = complemento
        mensagens.append(msg)
    return mensagens


class SefinClient:
    def __init__(self, cert, private_key, homologacao: bool = False,
                 base_url: str | None = None):
        self._cert = cert
        self._key = private_key
        self.homologacao = homologacao
        self._base = (base_url or URLS[homologacao]).rstrip("/")

    def _requisicao(self, metodo: str, caminho: str, corpo: dict | None = None):
        cert_path, key_path = cert_key_to_temp_pem(self._cert, self._key)
        try:
            return requests.request(
                metodo,
                f"{self._base}{caminho}",
                json=corpo,
                headers={"Accept": "application/json"},
                cert=(cert_path, key_path),
                timeout=TIMEOUT_SEG,
            )
        except requests.exceptions.RequestException as e:
            raise SefinIndisponivelError(
                f"Falha de comunicacao com o Sistema Nacional: {e}"
            ) from e
        finally:
            os.unlink(cert_path)
            os.unlink(key_path)

    @staticmethod
    def _json(resposta):
        try:
            return resposta.json()
        except ValueError:
            return None

    def _tratar(self, resposta, sucesso=(200, 201)) -> dict:
        corpo = self._json(resposta)
        if resposta.status_code in sucesso and isinstance(corpo, dict):
            return corpo
        if resposta.status_code >= 500:
            raise SefinIndisponivelError(
                f"Sistema Nacional respondeu HTTP {resposta.status_code}: "
                f"{resposta.text[:300]}"
            )
        mensagens = normalizar_mensagens(corpo)
        if mensagens:
            raise SefinRecusouError(mensagens, resposta.status_code)
        if resposta.status_code == 403:
            raise SefinCertificadoRecusadoError(
                "Sistema Nacional recusou o certificado (HTTP 403)"
            )
        raise SefinIndisponivelError(
            f"Resposta inesperada do Sistema Nacional (HTTP "
            f"{resposta.status_code}): {resposta.text[:300]}"
        )

    def emitir(self, dps_xml: bytes) -> dict:
        resposta = self._requisicao("POST", "/nfse", {"dpsXmlGZipB64": compactar(dps_xml)})
        return self._tratar(resposta)

    def consultar_dps(self, id_dps: str) -> str | None:
        """Chave de acesso da NFS-e gerada a partir da DPS, ou None."""
        resposta = self._requisicao("GET", f"/dps/{id_dps}")
        if resposta.status_code == 404:
            return None
        corpo = self._tratar(resposta)
        return _campo(corpo, "chaveacesso") or None

    def consultar_nfse(self, chave_acesso: str) -> dict:
        return self._tratar(self._requisicao("GET", f"/nfse/{chave_acesso}"))

    def registrar_evento(self, chave_acesso: str, pedido_xml: bytes) -> dict:
        resposta = self._requisicao(
            "POST",
            f"/nfse/{chave_acesso}/eventos",
            {"pedidoRegistroEventoXmlGZipB64": compactar(pedido_xml)},
        )
        return self._tratar(resposta)
