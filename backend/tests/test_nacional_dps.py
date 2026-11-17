"""DPS e evento de cancelamento do Sistema Nacional, validados contra os XSDs
oficiais v1.01 e com a assinatura conferida."""
import base64
import hashlib
from datetime import date, datetime

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from lxml import etree

from app.nfse.nacional import (
    FUSO_BRASILIA,
    LEIAUTE_NT004,
    LEIAUTE_NT009,
    NS,
    SCHEMA_DPS,
    SCHEMA_EVENTO,
    leiaute_vigente,
    schema_dps,
    schema_evento,
)
from app.nfse.nacional.assinatura import DS, assinar
from app.nfse.nacional.dps import build_dps, montar_id_dps, serie_formatada, xml_bytes
from app.nfse.nacional.evento import build_pedido_cancelamento, montar_id_evento
from app.nfse.xsd_validator import XSDValidationError, validar

CHAVE = "3550308211222333000181000000000000126110000000001"[:49] + "7"


def dados_base(**extra) -> dict:
    dados = {
        "tp_amb": 2,
        "dh_emi": datetime(2026, 11, 14, 10, 30, 0, tzinfo=FUSO_BRASILIA),
        "serie": "1",
        "numero": 42,
        "competencia": date(2026, 11, 13),
        "c_loc_emi": "3550308",
        "prestador": {"cnpj": "11222333000181", "im": "12345678"},
        "reg_trib": {"op_simp_nac": 3, "reg_ap_trib_sn": 1, "reg_esp_trib": 0},
        "tomador": {
            "cpf_cnpj": "52998224725",
            "razao_social": "Fulano de Tal",
            "email": "fulano@exemplo.com.br",
            "endereco": None,
        },
        "servico": {
            "c_loc_prestacao": "3550308",
            "c_trib_nac": "080201",
            "descricao": "Servicos de treinamento. Pedido #1",
            "c_nbs": "",
        },
        "valor": 999.0,
        "p_tot_trib_sn": 6.0,
    }
    dados.update(extra)
    return dados


def _q(tag):
    return f"{{{NS}}}{tag}"


def _c14n_padrao(elemento) -> bytes:
    """C14N como um verificador padrao calcula: o elemento reparseado como
    documento isolado (sem os resets de namespace do c14n de subarvore)."""
    isolado = etree.fromstring(etree.tostring(elemento, with_tail=False))
    c14n = etree.tostring(isolado, method="c14n", exclusive=False, with_comments=False)
    assert b'xmlns=""' not in c14n
    return c14n


def conferir_assinatura(root, cert):
    """Verificacao do lado de quem recebe: digest da referencia e
    SignatureValue sobre o SignedInfo canonicalizado."""
    sig = root.find(f"{{{DS}}}Signature")
    assert sig is not None
    assert sig.prefix is None
    ref = sig.find(f".//{{{DS}}}Reference")
    alvo_id = ref.get("URI").lstrip("#")
    alvo = root.xpath(f"//*[@Id='{alvo_id}']")[0]
    digest = base64.b64encode(hashlib.sha256(_c14n_padrao(alvo)).digest()).decode()
    assert sig.findtext(f".//{{{DS}}}DigestValue") == digest

    signed_info = sig.find(f"{{{DS}}}SignedInfo")
    valor = base64.b64decode(sig.findtext(f"{{{DS}}}SignatureValue"))
    cert.public_key().verify(
        valor, _c14n_padrao(signed_info), padding.PKCS1v15(), hashes.SHA256()
    )


class TestIdentificadores:
    def test_id_dps_cnpj(self):
        id_dps = montar_id_dps("3550308", "11.222.333/0001-81", "1", 42)
        assert id_dps == "DPS3550308211222333000181" + "00001" + "000000000000042"
        assert len(id_dps) == 45

    def test_id_dps_cpf_completa_com_zeros(self):
        id_dps = montar_id_dps("3550308", "52998224725", "7", 1)
        assert id_dps[10] == "1"
        assert id_dps[11:25] == "00052998224725"

    @pytest.mark.parametrize("serie", ["0", "50000", "abc", ""])
    def test_serie_fora_da_faixa(self, serie):
        with pytest.raises(ValueError):
            serie_formatada(serie)

    def test_id_evento(self):
        assert montar_id_evento(CHAVE) == f"PRE{CHAVE}101101"
        assert len(montar_id_evento(CHAVE)) == 59


class TestDps:
    def test_dps_minima_valida_no_xsd(self, cert_e_chave):
        cert, key = cert_e_chave
        root = build_dps(dados_base())
        assinar(root, root[0], cert, key)
        validar(root, SCHEMA_DPS)

    def test_sem_prefixo_de_namespace(self, cert_e_chave):
        cert, key = cert_e_chave
        root = build_dps(dados_base())
        assinar(root, root[0], cert, key)
        xml = xml_bytes(root).decode()
        assert xml.startswith("<?xml version='1.0' encoding='UTF-8'?>")
        assert "<DPS xmlns=\"http://www.sped.fazenda.gov.br/nfse\" versao=\"1.01\">" in xml
        assert "ds:" not in xml and "ns0:" not in xml
        assert "<Signature xmlns=\"http://www.w3.org/2000/09/xmldsig#\">" in xml

    def test_campos_principais(self):
        root = build_dps(dados_base())
        inf = root.find(_q("infDPS"))
        assert inf.get("Id") == montar_id_dps("3550308", "11222333000181", "1", 42)
        assert inf.findtext(_q("tpAmb")) == "2"
        assert inf.findtext(_q("dhEmi")) == "2026-11-14T10:30:00-03:00"
        assert inf.findtext(_q("serie")) == "00001"
        assert inf.findtext(_q("nDPS")) == "42"
        assert inf.findtext(_q("dCompet")) == "2026-11-13"
        assert inf.findtext(_q("tpEmit")) == "1"
        prest = inf.find(_q("prest"))
        assert prest.findtext(_q("CNPJ")) == "11222333000181"
        assert prest.findtext(_q("IM")) == "12345678"
        assert prest.find(_q("xNome")) is None
        assert prest.find(_q("end")) is None
        assert prest.findtext(f"{_q('regTrib')}/{_q('opSimpNac')}") == "3"
        assert prest.findtext(f"{_q('regTrib')}/{_q('regApTribSN')}") == "1"
        assert inf.findtext(f"{_q('toma')}/{_q('CPF')}") == "52998224725"
        assert inf.findtext(f".//{_q('cTribNac')}") == "080201"
        assert inf.findtext(f".//{_q('vServ')}") == "999.00"
        assert inf.find(f".//{_q('pAliq')}") is None
        assert inf.findtext(f".//{_q('pTotTribSN')}") == "6.00"
        assert inf.find(_q("IBSCBS")) is None

    def test_sem_im_quando_nao_configurada(self, cert_e_chave):
        cert, key = cert_e_chave
        dados = dados_base(prestador={"cnpj": "11222333000181", "im": None})
        root = build_dps(dados)
        assert root.find(f".//{_q('IM')}") is None
        assinar(root, root[0], cert, key)
        validar(root, SCHEMA_DPS)

    def test_tomador_cnpj_com_endereco(self, cert_e_chave):
        cert, key = cert_e_chave
        tomador = {
            "cpf_cnpj": "11444777000161",
            "razao_social": "CLIENTE EXEMPLO LTDA",
            "email": "",
            "endereco": {
                "cep": "01310-100", "tipo_logradouro": "Av", "logradouro": "Paulista",
                "numero": "1000", "complemento": "Sala 1", "bairro": "Bela Vista",
                "codigo_municipio": "3550308", "uf": "SP",
            },
        }
        root = build_dps(dados_base(tomador=tomador))
        toma = root.find(f".//{_q('toma')}")
        assert toma.findtext(_q("CNPJ")) == "11444777000161"
        assert toma.findtext(f"{_q('end')}/{_q('endNac')}/{_q('CEP')}") == "01310100"
        assert toma.findtext(f"{_q('end')}/{_q('xLgr')}") == "Av Paulista"
        assert toma.find(_q("email")) is None
        assinar(root, root[0], cert, key)
        validar(root, SCHEMA_DPS)

    def test_endereco_incompleto_fica_de_fora(self):
        tomador = dict(dados_base()["tomador"], endereco={"cep": "01310100"})
        root = build_dps(dados_base(tomador=tomador))
        assert root.find(f".//{_q('toma')}/{_q('end')}") is None

    def test_nbs_quando_configurado(self, cert_e_chave):
        cert, key = cert_e_chave
        servico = dict(dados_base()["servico"], c_nbs="122051100")
        root = build_dps(dados_base(servico=servico))
        assert root.findtext(f".//{_q('cNBS')}") == "122051100"
        assinar(root, root[0], cert, key)
        validar(root, SCHEMA_DPS)

    def test_xsd_recusa_codigo_de_servico_invalido(self, cert_e_chave):
        cert, key = cert_e_chave
        servico = dict(dados_base()["servico"], c_trib_nac="05762")
        root = build_dps(dados_base(servico=servico))
        assinar(root, root[0], cert, key)
        with pytest.raises(XSDValidationError):
            validar(root, SCHEMA_DPS)


class TestLeiaute:
    """NT 004 na producao ate 30/11/2026; NT 009 na producao restrita desde
    20/10/2026 e na producao a partir de 01/12/2026."""

    def test_homologacao_usa_nt009(self):
        assert leiaute_vigente(True, date(2026, 11, 17)) == LEIAUTE_NT009

    def test_producao_usa_nt004_ate_30_11(self):
        assert leiaute_vigente(False, date(2026, 11, 30)) == LEIAUTE_NT004

    def test_producao_usa_nt009_a_partir_de_01_12(self):
        assert leiaute_vigente(False, date(2026, 12, 1)) == LEIAUTE_NT009

    def test_dps_nt009_tem_finnfse_depois_de_tpemit(self, cert_e_chave):
        cert, key = cert_e_chave
        root = build_dps(dados_base(leiaute=LEIAUTE_NT009))
        assinar(root, root[0], cert, key)
        validar(root, schema_dps(LEIAUTE_NT009))
        inf = root.find(_q("infDPS"))
        tags = [etree.QName(e).localname for e in inf]
        assert tags[tags.index("tpEmit") + 1] == "finNFSe"
        assert inf.findtext(_q("finNFSe")) == "0"

    def test_dps_nt004_sem_finnfse(self):
        root = build_dps(dados_base(leiaute=LEIAUTE_NT004))
        assert root.find(f".//{_q('finNFSe')}") is None
        validar(root, schema_dps(LEIAUTE_NT004))

    def test_dps_nt004_recusada_no_xsd_nt009(self):
        with pytest.raises(XSDValidationError):
            validar(build_dps(dados_base()), schema_dps(LEIAUTE_NT009))

    def test_evento_valido_no_xsd_nt009(self, cert_e_chave):
        cert, key = cert_e_chave
        root = build_pedido_cancelamento(
            2, datetime(2026, 11, 17, 11, 0, tzinfo=FUSO_BRASILIA),
            "11222333000181", CHAVE, 1, "Erro na emissao da nota",
        )
        assinar(root, root[0], cert, key)
        validar(root, schema_evento(LEIAUTE_NT009))


class TestAssinatura:
    def test_assinatura_confere(self, cert_e_chave):
        cert, key = cert_e_chave
        root = build_dps(dados_base())
        assinar(root, root[0], cert, key)
        conferir_assinatura(root, cert)

    def test_assinatura_sobrevive_a_serializacao(self, cert_e_chave):
        cert, key = cert_e_chave
        root = build_dps(dados_base())
        assinar(root, root[0], cert, key)
        reparse = etree.fromstring(xml_bytes(root))
        conferir_assinatura(reparse, cert)

    def test_assinatura_independente_signxml(self, cert_e_chave):
        signxml = pytest.importorskip("signxml")
        from cryptography.hazmat.primitives.serialization import Encoding

        cert, key = cert_e_chave
        root = build_dps(dados_base())
        assinar(root, root[0], cert, key)
        resultado = signxml.XMLVerifier().verify(
            xml_bytes(root),
            x509_cert=cert.public_bytes(Encoding.PEM).decode(),
            id_attribute="Id",
        )
        assert resultado.signed_xml is not None

    def test_elemento_sem_id(self, cert_e_chave):
        cert, key = cert_e_chave
        root = etree.Element(_q("DPS"), nsmap={None: NS})
        filho = etree.SubElement(root, _q("infDPS"))
        with pytest.raises(ValueError):
            assinar(root, filho, cert, key)


class TestEventoCancelamento:
    def test_pedido_valido_no_xsd(self, cert_e_chave):
        cert, key = cert_e_chave
        root = build_pedido_cancelamento(
            2, datetime(2026, 11, 14, 11, 0, tzinfo=FUSO_BRASILIA),
            "11222333000181", CHAVE, 1, "Erro na emissao da nota",
        )
        assinar(root, root[0], cert, key)
        validar(root, SCHEMA_EVENTO)
        conferir_assinatura(root, cert)
        inf = root.find(_q("infPedReg"))
        assert inf.get("Id") == f"PRE{CHAVE}101101"
        assert inf.findtext(_q("CNPJAutor")) == "11222333000181"
        assert inf.findtext(f"{_q('e101101')}/{_q('xDesc')}") == "Cancelamento de NFS-e"

    def test_motivo_curto_reprovado_no_xsd(self, cert_e_chave):
        cert, key = cert_e_chave
        root = build_pedido_cancelamento(
            2, datetime(2026, 11, 14, 11, 0, tzinfo=FUSO_BRASILIA),
            "11222333000181", CHAVE, 1, "curto",
        )
        assinar(root, root[0], cert, key)
        with pytest.raises(XSDValidationError):
            validar(root, SCHEMA_EVENTO)
