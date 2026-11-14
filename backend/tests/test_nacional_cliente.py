"""SefinClient com HTTP simulado e leitura do retorno da NFS-e."""
import gzip
import json

import pytest
import requests

from app.nfse.nacional import NS
from app.nfse.nacional.cliente import (
    URLS,
    SefinCertificadoRecusadoError,
    SefinClient,
    SefinIndisponivelError,
    SefinRecusouError,
    compactar,
    descompactar,
    normalizar_mensagens,
)
from app.nfse.nacional.retorno import ler_nfse, xml_nfse
from app.nfse.parser import RespostaInvalidaError
from app.nfse.soap_client import PrefeituraIndisponivelError

def chave_teste() -> str:
    """Municipio (7) + ambiente gerador (1) + tipo de inscricao (1) +
    inscricao (14) + numero (13) + ano/mes (4) + codigo (9) + DV (1)."""
    c = "3550308" + "1" + "2" + "11222333000181" + "0000000000017" + "2611" + "000000001" + "3"
    assert len(c) == 50
    return c


def xml_nfse_fake(chave: str, numero: str = "17") -> bytes:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<NFSe xmlns="{NS}" versao="1.01"><infNFSe Id="NFS{chave}">'
        f"<nNFSe>{numero}</nNFSe><cStat>100</cStat>"
        f"<dhProc>2026-11-14T10:31:00-03:00</dhProc></infNFSe></NFSe>"
    ).encode()


class RespostaFake:
    def __init__(self, status: int, corpo=None, texto: str | None = None):
        self.status_code = status
        self._corpo = corpo
        self.text = texto if texto is not None else json.dumps(corpo or {})

    def json(self):
        if self._corpo is None:
            raise ValueError("sem json")
        return self._corpo


@pytest.fixture
def http(monkeypatch):
    chamadas = []
    respostas = []

    def request(metodo, url, json=None, headers=None, cert=None, timeout=None):
        chamadas.append({"metodo": metodo, "url": url, "json": json, "cert": cert})
        resposta = respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    monkeypatch.setattr("app.nfse.nacional.cliente.requests.request", request)
    return chamadas, respostas


@pytest.fixture
def cliente(cert_e_chave):
    cert, key = cert_e_chave
    return SefinClient(cert, key, homologacao=True)


class TestCompactacao:
    def test_ida_e_volta(self):
        xml = b"<DPS>acentua\xc3\xa7\xc3\xa3o</DPS>"
        assert descompactar(compactar(xml)) == xml
        assert gzip.decompress(__import__("base64").b64decode(compactar(xml))) == xml


class TestMensagens:
    def test_erros_lista_com_maiusculas(self):
        corpo = {"erros": [{"Codigo": "E0014", "Descricao": "DPS ja convertida", "Complemento": "x"}]}
        assert normalizar_mensagens(corpo) == [
            {"codigo": "E0014", "descricao": "DPS ja convertida", "complemento": "x"}
        ]

    def test_erro_unico_e_mensagem_como_descricao(self):
        corpo = {"erro": {"codigo": "E0840", "mensagem": "Evento recusado"}}
        assert normalizar_mensagens(corpo) == [{"codigo": "E0840", "descricao": "Evento recusado"}]

    def test_corpo_vazio(self):
        assert normalizar_mensagens(None) == []
        assert normalizar_mensagens({"outra": 1}) == []


class TestSefinClient:
    def test_urls_por_ambiente(self, cert_e_chave):
        cert, key = cert_e_chave
        assert SefinClient(cert, key)._base == URLS[False]
        assert "producaorestrita" in SefinClient(cert, key, homologacao=True)._base

    def test_emitir_envia_gzip_base64_com_mtls(self, http, cliente):
        chamadas, respostas = http
        respostas.append(RespostaFake(201, {"chaveAcesso": chave_teste(),
                                            "nfseXmlGZipB64": compactar(xml_nfse_fake(chave_teste()))}))
        corpo = cliente.emitir(b"<DPS/>")
        assert corpo["chaveAcesso"] == chave_teste()
        chamada = chamadas[0]
        assert chamada["metodo"] == "POST"
        assert chamada["url"] == f"{URLS[True]}/nfse"
        assert descompactar(chamada["json"]["dpsXmlGZipB64"]) == b"<DPS/>"
        assert chamada["cert"] is not None

    def test_pem_temporario_removido(self, http, cliente):
        import os

        chamadas, respostas = http
        respostas.append(RespostaFake(201, {"ok": 1}))
        cliente.emitir(b"<DPS/>")
        cert_path, key_path = chamadas[0]["cert"]
        assert not os.path.exists(cert_path) and not os.path.exists(key_path)

    def test_recusa_400(self, http, cliente):
        _, respostas = http
        respostas.append(RespostaFake(400, {"erros": [{"codigo": "E0310", "descricao": "Codigo inexistente"}]}))
        with pytest.raises(SefinRecusouError) as exc:
            cliente.emitir(b"<DPS/>")
        assert exc.value.erros[0]["codigo"] == "E0310"
        assert exc.value.status == 400

    def test_403_sem_mensagem_e_certificado(self, http, cliente):
        _, respostas = http
        respostas.append(RespostaFake(403, None, "<html>Forbidden</html>"))
        with pytest.raises(SefinCertificadoRecusadoError, match="certificado"):
            cliente.emitir(b"<DPS/>")

    def test_403_com_mensagem_e_recusa(self, http, cliente):
        _, respostas = http
        respostas.append(RespostaFake(403, {"erros": [{"codigo": "E1209", "descricao": "Sem CNPJ"}]}))
        with pytest.raises(SefinRecusouError):
            cliente.emitir(b"<DPS/>")

    def test_5xx_e_indisponivel(self, http, cliente):
        _, respostas = http
        respostas.append(RespostaFake(503, None, "fora do ar"))
        with pytest.raises(SefinIndisponivelError):
            cliente.emitir(b"<DPS/>")

    def test_falha_de_rede(self, http, cliente):
        _, respostas = http
        respostas.append(requests.exceptions.ConnectTimeout("timeout"))
        with pytest.raises(SefinIndisponivelError) as exc:
            cliente.emitir(b"<DPS/>")
        assert isinstance(exc.value, PrefeituraIndisponivelError)

    def test_consultar_dps_encontrada_e_nao_encontrada(self, http, cliente):
        chamadas, respostas = http
        respostas.append(RespostaFake(200, {"chaveAcesso": chave_teste()}))
        respostas.append(RespostaFake(404, {"erro": {"codigo": "E404", "descricao": "nao encontrada"}}))
        assert cliente.consultar_dps("DPS123") == chave_teste()
        assert cliente.consultar_dps("DPS456") is None
        assert chamadas[0]["url"].endswith("/dps/DPS123")
        assert chamadas[0]["metodo"] == "GET"

    def test_registrar_evento(self, http, cliente):
        chamadas, respostas = http
        respostas.append(RespostaFake(201, {"eventoXmlGZipB64": compactar(b"<evento/>")}))
        cliente.registrar_evento(chave_teste(), b"<pedRegEvento/>")
        assert chamadas[0]["url"].endswith(f"/nfse/{chave_teste()}/eventos")
        assert descompactar(chamadas[0]["json"]["pedidoRegistroEventoXmlGZipB64"]) == b"<pedRegEvento/>"


class TestRetorno:
    def test_ler_nfse(self):
        corpo = {"nfseXmlGZipB64": compactar(xml_nfse_fake(chave_teste(), "17"))}
        info = ler_nfse(xml_nfse(corpo))
        assert info["chave_acesso"] == chave_teste()
        assert info["numero_nfse"] == "17"
        assert info["c_stat"] == "100"

    def test_resposta_sem_xml(self):
        with pytest.raises(RespostaInvalidaError):
            xml_nfse({"chaveAcesso": "x"})

    def test_base64_invalido(self):
        with pytest.raises(RespostaInvalidaError):
            xml_nfse({"nfseXmlGZipB64": "nao-e-gzip"})

    def test_xml_sem_id(self):
        with pytest.raises(RespostaInvalidaError):
            ler_nfse(f'<NFSe xmlns="{NS}"><infNFSe/></NFSe>'.encode())

    def test_nao_resolve_entidades(self):
        xml = (
            b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
            + f'<NFSe xmlns="{NS}"><infNFSe Id="NFS{chave_teste()}"><nNFSe>&e;</nNFSe></infNFSe></NFSe>'.encode()
        )
        info = ler_nfse(xml)
        assert "root" not in (info["numero_nfse"] or "")
