"""Emissao e cancelamento no ambiente nacional com Sefin simulada."""
import json
from datetime import date

import pytest
from lxml import etree
from pydantic import ValidationError

from app.models.config_store import get_config, save_config
from app.models.nota import Nota
from app.nfse.emitter import (
    EmissaoInvalidaError,
    EmissaoPayload,
    PrefeituraRecusouError,
    cancelar,
    emitir,
    sincronizar,
)
from app.nfse import nacional
from app.nfse.nacional import (
    LEIAUTE_NT009,
    NS,
    hoje_brasilia,
    leiaute_vigente,
    schema_dps,
    schema_evento,
)
from app.nfse.nacional.cliente import (
    SefinIndisponivelError,
    SefinRecusouError,
    compactar,
    descompactar,
)
from app.nfse.nacional.dps import montar_id_dps
from app.nfse.xsd_validator import validar
from tests.test_emitter import session  # noqa: F401  (fixture)
from tests.test_nacional_cliente import chave_teste, xml_nfse_fake


class SefinFake:
    """Sefin simulada. `emitir_efeitos`: lista de respostas ou excecoes, uma
    por chamada de emitir. `dps_convertidas`: Id da DPS -> chave."""

    def __init__(self, emitir_efeitos=None, evento_efeito=None):
        self.emitir_efeitos = list(emitir_efeitos or [])
        self.evento_efeito = evento_efeito
        self.dps_convertidas = {}
        self.enviadas = []
        self.consultas_dps = []
        self.eventos = []

    def emitir(self, dps_xml):
        self.enviadas.append(dps_xml)
        efeito = self.emitir_efeitos.pop(0)
        if isinstance(efeito, Exception):
            raise efeito
        return efeito

    def consultar_dps(self, id_dps):
        self.consultas_dps.append(id_dps)
        return self.dps_convertidas.get(id_dps)

    def consultar_nfse(self, chave):
        return {"chaveAcesso": chave, "nfseXmlGZipB64": compactar(xml_nfse_fake(chave, "21"))}

    def registrar_evento(self, chave, pedido_xml):
        self.eventos.append((chave, pedido_xml))
        if isinstance(self.evento_efeito, Exception):
            raise self.evento_efeito
        return {"eventoXmlGZipB64": compactar(b"<evento>ok</evento>")}


def resposta_autorizada(chave=None, numero="17"):
    chave = chave or chave_teste()
    return {"chaveAcesso": chave, "nfseXmlGZipB64": compactar(xml_nfse_fake(chave, numero)),
            "alertas": [{"codigo": "A001", "descricao": "Alerta de teste"}]}


@pytest.fixture
def cfg_nacional(session):  # noqa: F811
    cfg = get_config(session)
    cfg["prestador"] = {
        "cnpj": "11222333000181",
        "inscricao_municipal": "12345678",
        "razao_social": "EMPRESA EXEMPLO LTDA",
        "email": "contato@exemplo.com.br",
    }
    cfg["servicos"] = {
        "05762": {
            "descricao_padrao": "Treinamento",
            "aliquota": 0.02,
            "iss_retido": False,
            "c_loc_prestacao": "3550308",
            "c_trib_nac": "080201",
        }
    }
    cfg["modo_teste"] = False
    cfg["ambiente"] = "nacional"
    cfg["nacional"]["p_tot_trib_sn"] = 6.0
    save_config(session, cfg)
    return cfg


@pytest.fixture
def sefin(monkeypatch):
    estado = {"fake": SefinFake(), "homologacao": []}

    def criar(cert, key, homologacao):
        estado["homologacao"].append(homologacao)
        return estado["fake"]

    monkeypatch.setattr("app.nfse.nacional.emissor.criar_cliente", criar)
    return estado


def payload(**extra):
    dados = {
        "tomador": {"cpf_cnpj": "52998224725", "razao_social": "Fulano de Tal",
                    "email": "fulano@exemplo.com.br"},
        "servico": "05762",
        "valor": 999.0,
        "descricao": "Servicos de treinamento. Pedido #1",
        "ref_externa": "wc-1",
    }
    dados.update(extra)
    return EmissaoPayload(**dados)


def _dps(xml_bytes):
    return etree.fromstring(xml_bytes)


def _q(tag):
    return f"{{{NS}}}{tag}"


class TestEmissao:
    def test_autoriza_e_grava(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        sefin["fake"].emitir_efeitos = [resposta_autorizada()]
        r = emitir(payload(), session, None, cert, key)

        nota = r["nota"]
        assert r["teste"] is False
        assert nota.status == "autorizada"
        assert nota.ambiente == "nacional"
        assert nota.chave_acesso == chave_teste()
        assert nota.numero_nfse == "17"
        assert nota.codigo_verificacao is None
        assert nota.serie_dps == "00001" and nota.numero_dps == 1
        assert nota.competencia == hoje_brasilia().isoformat()
        assert nota.ref_externa == "wc-1"
        assert r["alertas"] == [{"codigo": "A001", "descricao": "Alerta de teste"}]
        assert sefin["homologacao"] == [False]
        assert get_config(session)["nacional"]["proximo_numero_dps"] == 2

        dps = _dps(sefin["fake"].enviadas[0])
        validar(dps, schema_dps(leiaute_vigente(False, hoje_brasilia())))
        assert dps.findtext(f".//{_q('tpAmb')}") == "1"
        assert dps.findtext(f".//{_q('IM')}") == "12345678"
        assert "<DPS" in nota.xml_enviado and "<NFSe" in nota.xml_retorno

    def test_competencia_informada(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        sefin["fake"].emitir_efeitos = [resposta_autorizada()]
        emitir(payload(competencia=date(2026, 11, 3)), session, None, cert, key)
        dps = _dps(sefin["fake"].enviadas[0])
        assert dps.findtext(f".//{_q('dCompet')}") == "2026-11-03"

    def test_competencia_futura_recusada(self):
        with pytest.raises(ValidationError):
            payload(competencia=date(2999, 1, 1))

    def test_sem_im_quando_desligada(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        cfg = get_config(session)
        cfg["nacional"]["informar_im"] = False
        save_config(session, cfg)
        sefin["fake"].emitir_efeitos = [resposta_autorizada()]
        emitir(payload(), session, None, cert, key)
        assert _dps(sefin["fake"].enviadas[0]).find(f".//{_q('IM')}") is None

    def test_im_do_cadastro_nacional_tem_prioridade(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        # O CNC guarda a IM como a prefeitura carregou (SP: 15 digitos com
        # zeros a esquerda), que pode diferir do CCM usado no municipal.
        cert, key = cert_e_chave
        cfg = get_config(session)
        cfg["nacional"]["inscricao_municipal"] = "000000012345678"
        save_config(session, cfg)
        sefin["fake"].emitir_efeitos = [resposta_autorizada()]
        emitir(payload(), session, None, cert, key)
        assert _dps(sefin["fake"].enviadas[0]).findtext(f".//{_q('IM')}") == "000000012345678"
        assert get_config(session)["prestador"]["inscricao_municipal"] == "12345678"

    def test_codigo_municipal_e_nbs_do_servico(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        cfg = get_config(session)
        cfg["servicos"]["05762"].update({"c_trib_mun": "003", "c_nbs": "122051900"})
        save_config(session, cfg)
        sefin["fake"].emitir_efeitos = [resposta_autorizada()]
        emitir(payload(), session, None, cert, key)
        dps = _dps(sefin["fake"].enviadas[0])
        assert dps.findtext(f".//{_q('cTribMun')}") == "003"
        assert dps.findtext(f".//{_q('cNBS')}") == "122051900"

    def test_mesma_ref_autorizada_e_idempotente(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        sefin["fake"].emitir_efeitos = [resposta_autorizada()]
        primeira = emitir(payload(), session, None, cert, key)
        segunda = emitir(payload(), session, None, cert, key)
        assert segunda["idempotente"] is True
        assert segunda["nota"].id == primeira["nota"].id
        assert len(sefin["fake"].enviadas) == 1

    def test_recusa_vira_erro_com_codigos(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        erros = [{"codigo": "E0310", "descricao": "Codigo de tributacao inexistente"}]
        sefin["fake"].emitir_efeitos = [SefinRecusouError(erros, 400)]
        with pytest.raises(PrefeituraRecusouError) as exc:
            emitir(payload(), session, None, cert, key)
        assert exc.value.origem == "nacional"
        assert exc.value.emissor == "Sistema Nacional"
        nota = session.query(Nota).one()
        assert nota.status == "erro"
        assert json.loads(nota.erros_json) == erros

    def test_reenvio_apos_recusa_reaproveita_numero(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        sefin["fake"].emitir_efeitos = [
            SefinRecusouError([{"codigo": "E0160", "descricao": "Simples divergente"}], 400),
            resposta_autorizada(),
        ]
        with pytest.raises(PrefeituraRecusouError):
            emitir(payload(), session, None, cert, key)
        r = emitir(payload(), session, None, cert, key)
        assert r["nota"].status == "autorizada"
        assert r["nota"].numero_dps == 1
        assert get_config(session)["nacional"]["proximo_numero_dps"] == 2
        assert session.query(Nota).count() == 1

    def test_falha_de_rede_e_recuperacao_sem_duplicar(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        fake = sefin["fake"]
        fake.emitir_efeitos = [SefinIndisponivelError("timeout")]
        with pytest.raises(SefinIndisponivelError):
            emitir(payload(), session, None, cert, key)
        nota = session.query(Nota).one()
        assert nota.status == "erro" and nota.numero_dps == 1

        # A DPS chegou a virar nota do lado do Sistema Nacional
        id_dps = montar_id_dps("3550308", "11222333000181", "00001", 1)
        fake.dps_convertidas[id_dps] = chave_teste()
        r = emitir(payload(), session, None, cert, key)

        assert r["idempotente"] is True
        assert r["nota"].status == "autorizada"
        assert r["nota"].chave_acesso == chave_teste()
        assert r["nota"].numero_nfse == "21"
        assert fake.consultas_dps == [id_dps]
        assert len(fake.enviadas) == 1
        assert get_config(session)["nacional"]["proximo_numero_dps"] == 2

    def test_falha_de_rede_e_reenvio_com_mesmo_numero(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        fake = sefin["fake"]
        fake.emitir_efeitos = [SefinIndisponivelError("timeout"), resposta_autorizada()]
        with pytest.raises(SefinIndisponivelError):
            emitir(payload(), session, None, cert, key)
        r = emitir(payload(), session, None, cert, key)
        assert r["nota"].status == "autorizada"
        primeira, segunda = (_dps(x) for x in fake.enviadas)
        assert primeira.findtext(f".//{_q('nDPS')}") == segunda.findtext(f".//{_q('nDPS')}") == "1"

    def test_e0014_recupera_nota_ja_gerada(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        fake = sefin["fake"]
        id_dps = montar_id_dps("3550308", "11222333000181", "00001", 1)
        fake.emitir_efeitos = [SefinRecusouError([{"codigo": "E0014", "descricao": "DPS ja convertida"}], 400)]
        fake.dps_convertidas[id_dps] = chave_teste()
        r = emitir(payload(), session, None, cert, key)
        assert r["idempotente"] is True
        assert r["nota"].status == "autorizada"

    def test_percentual_do_servico_tem_prioridade(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        # Cursos (8.02) so entram no Anexo III; consultoria (1.06) depende do
        # Fator R. Cada servico pode ter o proprio percentual nominal.
        cert, key = cert_e_chave
        cfg = get_config(session)
        cfg["servicos"]["05762"]["p_tot_trib_sn"] = 11.2
        save_config(session, cfg)
        sefin["fake"].emitir_efeitos = [resposta_autorizada()]
        emitir(payload(), session, None, cert, key)
        assert _dps(sefin["fake"].enviadas[0]).findtext(f".//{_q('pTotTribSN')}") == "11.20"

    def test_percentual_so_no_servico_basta(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        cfg = get_config(session)
        cfg["nacional"]["p_tot_trib_sn"] = None
        cfg["servicos"]["05762"]["p_tot_trib_sn"] = 6
        save_config(session, cfg)
        sefin["fake"].emitir_efeitos = [resposta_autorizada()]
        emitir(payload(), session, None, cert, key)
        assert _dps(sefin["fake"].enviadas[0]).findtext(f".//{_q('pTotTribSN')}") == "6.00"

    def test_sem_percentual_do_servico_usa_o_geral(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        sefin["fake"].emitir_efeitos = [resposta_autorizada()]
        emitir(payload(), session, None, cert, key)
        assert _dps(sefin["fake"].enviadas[0]).findtext(f".//{_q('pTotTribSN')}") == "6.00"

    def test_config_incompleta_nao_reserva_numero(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        cfg = get_config(session)
        cfg["nacional"]["p_tot_trib_sn"] = None
        del cfg["servicos"]["05762"]["c_trib_nac"]
        save_config(session, cfg)
        with pytest.raises(EmissaoInvalidaError) as exc:
            emitir(payload(), session, None, cert, key)
        detalhes = " ".join(exc.value.detalhes)
        assert "p_tot_trib_sn" in detalhes and "c_trib_nac" in detalhes
        assert get_config(session)["nacional"]["proximo_numero_dps"] == 1
        assert sefin["fake"].enviadas == []

    def test_so_me_epp(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        cfg = get_config(session)
        cfg["nacional"]["op_simp_nac"] = 2
        save_config(session, cfg)
        with pytest.raises(EmissaoInvalidaError, match="ME/EPP"):
            emitir(payload(), session, None, cert, key)

    def test_erro_anterior_no_municipal_e_substituido(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        session.add(Nota(ref_externa="wc-1", status="erro", ambiente="municipal",
                         numero_rps=1614, erros_json='[{"codigo": "1647"}]'))
        session.commit()
        sefin["fake"].emitir_efeitos = [resposta_autorizada()]
        r = emitir(payload(), session, None, cert, key)
        assert r["nota"].ambiente == "nacional"
        assert r["nota"].numero_rps is None
        assert session.query(Nota).count() == 1


class TestHomologacao:
    def test_modo_teste_vai_para_producao_restrita(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        cfg = get_config(session)
        cfg["modo_teste"] = True
        save_config(session, cfg)
        sefin["fake"].emitir_efeitos = [resposta_autorizada()]
        r = emitir(payload(), session, None, cert, key)

        assert r["teste"] is True
        assert sefin["homologacao"] == [True]
        assert r["nota"].ambiente == "nacional_homologacao"
        assert r["nota"].ref_externa == "homologacao:wc-1"
        nac = get_config(session)["nacional"]
        assert nac["proximo_numero_dps_homologacao"] == 2
        assert nac["proximo_numero_dps"] == 1
        assert _dps(sefin["fake"].enviadas[0]).findtext(f".//{_q('tpAmb')}") == "2"

    def test_producao_restrita_recebe_leiaute_nt009(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        cfg = get_config(session)
        cfg["modo_teste"] = True
        save_config(session, cfg)
        sefin["fake"].emitir_efeitos = [resposta_autorizada()]
        emitir(payload(), session, None, cert, key)
        dps = _dps(sefin["fake"].enviadas[0])
        validar(dps, schema_dps(LEIAUTE_NT009))
        assert dps.findtext(f".//{_q('finNFSe')}") == "0"

    def test_teste_nao_bloqueia_a_ref_em_producao(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        cfg = get_config(session)
        cfg["modo_teste"] = True
        save_config(session, cfg)
        sefin["fake"].emitir_efeitos = [resposta_autorizada(), resposta_autorizada()]
        emitir(payload(), session, None, cert, key)
        cfg["modo_teste"] = False
        save_config(session, cfg)
        r = emitir(payload(), session, None, cert, key)
        assert r.get("idempotente") is not True
        assert r["nota"].ambiente == "nacional"
        assert session.query(Nota).count() == 2


class TestLeiauteNaProducao:
    def test_producao_passa_para_nt009_na_data_de_corte(
        self, session, cfg_nacional, sefin, cert_e_chave, monkeypatch  # noqa: F811
    ):
        monkeypatch.setattr(nacional, "INICIO_NT009_PRODUCAO", date(2000, 1, 1))
        cert, key = cert_e_chave
        sefin["fake"].emitir_efeitos = [resposta_autorizada()]
        emitir(payload(), session, None, cert, key)
        dps = _dps(sefin["fake"].enviadas[0])
        assert dps.findtext(f".//{_q('tpAmb')}") == "1"
        validar(dps, schema_dps(LEIAUTE_NT009))

    def test_producao_fica_no_nt004_antes_da_data_de_corte(
        self, session, cfg_nacional, sefin, cert_e_chave, monkeypatch  # noqa: F811
    ):
        monkeypatch.setattr(nacional, "INICIO_NT009_PRODUCAO", date(2999, 1, 1))
        cert, key = cert_e_chave
        sefin["fake"].emitir_efeitos = [resposta_autorizada()]
        emitir(payload(), session, None, cert, key)
        dps = _dps(sefin["fake"].enviadas[0])
        assert dps.find(f".//{_q('finNFSe')}") is None


class TestCancelamento:
    def _autorizada(self, session, sefin, cert, key):  # noqa: F811
        sefin["fake"].emitir_efeitos = [resposta_autorizada()]
        return emitir(payload(), session, None, cert, key)["nota"]

    def test_cancela_por_evento(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        nota = self._autorizada(session, sefin, cert, key)
        nota = cancelar(nota, session, None, cert, key, motivo_codigo=2,
                        motivo="Servico nao foi prestado ao aluno")
        assert nota.status == "cancelada"
        assert nota.xml_evento == "<evento>ok</evento>"
        assert "<NFSe" in nota.xml_retorno

        chave, pedido = sefin["fake"].eventos[0]
        assert chave == chave_teste()
        root = etree.fromstring(pedido)
        validar(root, schema_evento(leiaute_vigente(False, hoje_brasilia())))
        assert root.findtext(f".//{_q('cMotivo')}") == "2"
        assert root.findtext(f".//{_q('tpAmb')}") == "1"

    def test_motivo_padrao(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        nota = self._autorizada(session, sefin, cert, key)
        cancelar(nota, session, None, cert, key)
        root = etree.fromstring(sefin["fake"].eventos[0][1])
        assert root.findtext(f".//{_q('xMotivo')}") == "Erro na emissao da nota"
        assert root.findtext(f".//{_q('cMotivo')}") == "1"

    @pytest.mark.parametrize("codigo,texto", [(3, None), (1, "curto")])
    def test_motivo_invalido(self, session, cfg_nacional, sefin, cert_e_chave, codigo, texto):  # noqa: F811
        cert, key = cert_e_chave
        nota = self._autorizada(session, sefin, cert, key)
        with pytest.raises(EmissaoInvalidaError):
            cancelar(nota, session, None, cert, key, motivo_codigo=codigo, motivo=texto)
        assert sefin["fake"].eventos == []

    def test_recusa_do_cancelamento(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        nota = self._autorizada(session, sefin, cert, key)
        sefin["fake"].evento_efeito = SefinRecusouError(
            [{"codigo": "E0822", "descricao": "Prazo de cancelamento expirou"}], 400
        )
        with pytest.raises(PrefeituraRecusouError) as exc:
            cancelar(nota, session, None, cert, key)
        assert exc.value.origem == "nacional"
        assert session.get(Nota, nota.id).status == "autorizada"

    def test_nota_de_homologacao_cancela_na_homologacao(self, session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
        cert, key = cert_e_chave
        cfg = get_config(session)
        cfg["modo_teste"] = True
        save_config(session, cfg)
        nota = self._autorizada(session, sefin, cert, key)
        cfg["modo_teste"] = False
        save_config(session, cfg)
        cancelar(nota, session, None, cert, key)
        assert sefin["homologacao"][-1] is True
        assert etree.fromstring(sefin["fake"].eventos[0][1]).findtext(f".//{_q('tpAmb')}") == "2"


def test_sincronizar_indisponivel_no_nacional(session, cfg_nacional, cert_e_chave):  # noqa: F811
    cert, key = cert_e_chave
    with pytest.raises(EmissaoInvalidaError, match="municipal"):
        sincronizar(date(2026, 11, 1), date(2026, 11, 14), session, None, cert, key)


def test_compactacao_do_dps_enviado(session, cfg_nacional, sefin, cert_e_chave):  # noqa: F811
    """O que o emissor entrega ao cliente e XML puro; o cliente compacta."""
    cert, key = cert_e_chave
    sefin["fake"].emitir_efeitos = [resposta_autorizada()]
    emitir(payload(), session, None, cert, key)
    enviado = sefin["fake"].enviadas[0]
    assert enviado.startswith(b"<?xml")
    assert descompactar(compactar(enviado)) == enviado
