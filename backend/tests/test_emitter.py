import json
from datetime import date
from pathlib import Path

import pytest

from tests.test_parser import envelopar_soap

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "chave-de-teste-para-fernet-e-sessao")
    from app.core import db
    db.reset_engine_para_testes()
    db.init_db()
    s = db.get_session()
    yield s
    s.close()
    db.reset_engine_para_testes()


@pytest.fixture
def cfg_pronta(session):
    from app.models.config_store import get_config, save_config
    cfg = get_config(session)
    cfg["prestador"] = {
        "cnpj": "37624983000147",
        "inscricao_municipal": "66467799",
        "razao_social": "PUNKMETRICS LTDA",
        "email": "contato@punkmetrics.com",
    }
    cfg["servicos"] = {
        "05762": {
            "descricao_padrao": "Treinamento",
            "aliquota": 0.02,
            "iss_retido": False,
            "nbs": "000000000",
            "c_class_trib": "000001",
            "c_ind_op": "000000",
            "fin_nfse": 0,
            "ind_final": 1,
            "ind_dest": 0,
        }
    }
    cfg["modo_teste"] = False
    save_config(session, cfg)
    return cfg


class ClientFake:
    def __init__(self, resposta_envio=None, resposta_cancel=None, resposta_consulta=None):
        self.resposta_envio = resposta_envio
        self.resposta_cancel = resposta_cancel
        self.resposta_consulta = resposta_consulta
        self.chamadas = []
        self.versoes = []

    def envio_rps(self, xml, versao=2):
        self.chamadas.append(("envio_rps", xml))
        self.versoes.append(versao)
        return self.resposta_envio

    def teste_envio_lote_rps(self, xml, versao=2):
        self.chamadas.append(("teste_envio_lote_rps", xml))
        self.versoes.append(versao)
        return self.resposta_envio

    def cancelamento_nfe(self, xml, versao=2):
        self.chamadas.append(("cancelamento_nfe", xml))
        self.versoes.append(versao)
        return self.resposta_cancel

    def consulta_nfe_periodo(self, xml, versao=2):
        self.chamadas.append(("consulta_nfe_periodo", xml))
        self.versoes.append(versao)
        return self.resposta_consulta


def payload_ok(**overrides):
    from app.nfse.emitter import EmissaoPayload
    d = {
        "tomador": {"cpf_cnpj": "111.444.777-35", "razao_social": "Fulano"},
        "servico": "05762",
        "valor": 599.0,
        "descricao": "Curso IA para Designers",
        "ref_externa": "woo-999",
    }
    d.update(overrides)
    return EmissaoPayload(**d)


def resposta_sucesso():
    return envelopar_soap((FIXTURES / "retorno_envio_sucesso.xml").read_text())


def resposta_erro():
    return envelopar_soap((FIXTURES / "retorno_envio_erro.xml").read_text())


class TestEmitir:
    def test_emissao_feliz(self, session, cfg_pronta, cert_e_chave):
        from app.nfse.emitter import emitir
        cert, key = cert_e_chave
        client = ClientFake(resposta_envio=resposta_sucesso())
        resultado = emitir(payload_ok(), session, client, cert, key)
        nota = resultado["nota"]
        assert nota.status == "autorizada"
        assert nota.numero_nfse == "1234"
        assert nota.codigo_verificacao == "ABCD1234"
        assert nota.numero_rps == 8
        assert client.chamadas[0][0] == "envio_rps"
        assert "<RPS>" in client.chamadas[0][1]

    def test_erro_da_prefeitura_grava_nota_erro(self, session, cfg_pronta, cert_e_chave):
        from app.models.nota import Nota
        from app.nfse.emitter import PrefeituraRecusouError, emitir
        cert, key = cert_e_chave
        client = ClientFake(resposta_envio=resposta_erro())
        with pytest.raises(PrefeituraRecusouError) as exc:
            emitir(payload_ok(), session, client, cert, key)
        assert exc.value.erros[0]["codigo"] == "1002"
        nota = session.query(Nota).first()
        assert nota.status == "erro"
        assert "1002" in nota.erros_json
        assert nota.xml_enviado is not None

    def test_idempotencia_ref_externa(self, session, cfg_pronta, cert_e_chave):
        from app.nfse.emitter import emitir
        cert, key = cert_e_chave
        client = ClientFake(resposta_envio=resposta_sucesso())
        r1 = emitir(payload_ok(), session, client, cert, key)
        r2 = emitir(payload_ok(), session, client, cert, key)
        assert r2["idempotente"] is True
        assert r2["nota"].id == r1["nota"].id
        assert len(client.chamadas) == 1

    def test_retry_apos_erro_reemite(self, session, cfg_pronta, cert_e_chave):
        from app.nfse.emitter import PrefeituraRecusouError, emitir
        cert, key = cert_e_chave
        client = ClientFake(resposta_envio=resposta_erro())
        with pytest.raises(PrefeituraRecusouError):
            emitir(payload_ok(), session, client, cert, key)
        client.resposta_envio = resposta_sucesso()
        resultado = emitir(payload_ok(), session, client, cert, key)
        assert resultado["nota"].status == "autorizada"

    def test_modo_teste_usa_lote_e_nao_grava(self, session, cfg_pronta, cert_e_chave):
        from app.models.config_store import get_config, save_config
        from app.models.nota import Nota
        from app.nfse.emitter import emitir
        cfg = get_config(session)
        cfg["modo_teste"] = True
        save_config(session, cfg)
        cert, key = cert_e_chave
        client = ClientFake(resposta_envio=resposta_sucesso())
        resultado = emitir(payload_ok(), session, client, cert, key)
        assert resultado["teste"] is True
        assert client.chamadas[0][0] == "teste_envio_lote_rps"
        assert "PedidoEnvioLoteRPS" in client.chamadas[0][1]
        assert session.query(Nota).count() == 0

    def test_servico_nao_cadastrado(self, session, cfg_pronta, cert_e_chave):
        from app.nfse.emitter import EmissaoInvalidaError, emitir
        cert, key = cert_e_chave
        client = ClientFake()
        with pytest.raises(EmissaoInvalidaError):
            emitir(payload_ok(servico="99999"), session, client, cert, key)

    def test_cpf_invalido_no_payload(self, cfg_pronta):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            payload_ok(tomador={"cpf_cnpj": "111.444.777-99"})


class TestLayout:
    def test_default_e_layout_1(self, session, cfg_pronta, cert_e_chave):
        from app.nfse.emitter import emitir
        cert, key = cert_e_chave
        client = ClientFake(resposta_envio=resposta_sucesso())
        emitir(payload_ok(), session, client, cert, key)
        xml = client.chamadas[0][1]
        # Layout 1: sem campos da reforma, com ValorServicos e Versao="1"
        assert 'Versao="1"' in xml
        assert "<ValorServicos>" in xml
        assert "IBSCBS" not in xml
        assert "<NBS>" not in xml
        assert "cLocPrestacao" not in xml

    def test_layout_2_quando_configurado(self, session, cfg_pronta, cert_e_chave):
        from app.models.config_store import get_config, save_config
        from app.nfse.emitter import emitir
        cfg = get_config(session)
        cfg["layout"] = 2
        save_config(session, cfg)
        cert, key = cert_e_chave
        client = ClientFake(resposta_envio=resposta_sucesso())
        emitir(payload_ok(), session, client, cert, key)
        xml = client.chamadas[0][1]
        assert 'Versao="2"' in xml
        assert "<IBSCBS>" in xml
        assert "<ValorFinalCobrado>" in xml
        assert "<ValorServicos>" not in xml

    def test_versao_schema_acompanha_o_layout(self, session, cfg_pronta, cert_e_chave):
        from app.nfse.emitter import emitir
        cert, key = cert_e_chave
        client = ClientFake(resposta_envio=resposta_sucesso())
        emitir(payload_ok(), session, client, cert, key)
        assert client.versoes[0] == 1

    def test_assinatura_v1_usa_inscricao_com_8_posicoes(self):
        from datetime import date
        from app.nfse.sign_string import build_sign_string_v1, build_sign_string_v2
        comum = dict(
            inscricao="66467799", serie="PM", numero=8, data_emissao=date(2026, 8, 1),
            tributacao="T", status="N", iss_retido=False, deducoes=0.0,
            cod_servico="05762", tomador={"cpf": "11144477735"},
        )
        v1 = build_sign_string_v1(valor_servicos=599.0, **comum)
        v2 = build_sign_string_v2(valor_cobrado=599.0, **comum)
        assert v1.startswith("66467799PM   ")
        assert v2.startswith("000066467799PM   ")
        assert len(v1) < len(v2)


class TestCancelar:
    def test_cancela_autorizada(self, session, cfg_pronta, cert_e_chave):
        from app.nfse.emitter import cancelar, emitir
        cert, key = cert_e_chave
        client = ClientFake(
            resposta_envio=resposta_sucesso(),
            resposta_cancel=envelopar_soap(
                (FIXTURES / "retorno_cancelamento_ok.xml").read_text(), "CancelamentoNFe"
            ),
        )
        nota = emitir(payload_ok(), session, client, cert, key)["nota"]
        cancelada = cancelar(nota, session, client, cert, key)
        assert cancelada.status == "cancelada"
        assert "PedidoCancelamentoNFe" in client.chamadas[-1][1]


class TestSincronizar:
    def test_upsert(self, session, cfg_pronta, cert_e_chave):
        from app.models.nota import Nota
        from app.nfse.emitter import sincronizar
        cert, key = cert_e_chave
        client = ClientFake(
            resposta_consulta=envelopar_soap(
                (FIXTURES / "retorno_consulta_periodo.xml").read_text(), "ConsultaNFeEmitidas"
            )
        )
        resultado = sincronizar(date(2026, 7, 1), date(2026, 7, 31), session, client, cert, key)
        assert resultado["novas"] == 2
        assert session.query(Nota).count() == 2
        cancelada = session.query(Nota).filter(Nota.numero_nfse == "1235").first()
        assert cancelada.status == "cancelada"

        # Segunda sincronizacao nao duplica
        resultado2 = sincronizar(date(2026, 7, 1), date(2026, 7, 31), session, client, cert, key)
        assert resultado2["novas"] == 0
        assert session.query(Nota).count() == 2
