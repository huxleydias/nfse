"""Vetores de teste oficiais do manual NFe_Web_Service v3.3.7 (pag. 48)."""
from datetime import date

from app.nfse.sign_string import build_sign_string_v2


BASE = dict(
    inscricao="123456789012",
    serie="RTNT",
    numero=1,
    data_emissao=date(2026, 1, 1),
    tributacao="T",
    status="N",
    iss_retido=False,
    valor_cobrado=20500.00,
    deducoes=5000.00,
    cod_servico="2658",
)


class TestVetoresOficiais:
    def test_cpf_com_intermediario(self):
        s = build_sign_string_v2(
            **BASE,
            tomador={"cpf": "13167474254"},
            intermediario={"cnpj": "09999999000106", "iss_retido": True},
        )
        assert s == (
            "123456789012RTNT 00000000000120260101TNN00000000205000"
            "0000000000500000026581000131674742542099999990001" "06S"
        )

    def test_cpf_sem_intermediario(self):
        s = build_sign_string_v2(**BASE, tomador={"cpf": "13167474254"})
        assert s == (
            "123456789012RTNT 00000000000120260101TNN00000000205000"
            "000000000050000002658100013167474254"
        )

    def test_nif_sem_intermediario(self):
        s = build_sign_string_v2(**BASE, tomador={"nif": "W123456789"})
        assert s == (
            "123456789012RTNT 00000000000120260101TNN00000000205000"
            "000000000050000002658400000000000000W123456789"
        )

    def test_nif_com_intermediario(self):
        s = build_sign_string_v2(
            **BASE,
            tomador={"nif": "W123456789"},
            intermediario={"cnpj": "09999999000106", "iss_retido": True},
        )
        assert s == (
            "123456789012RTNT 00000000000120260101TNN00000000205000"
            "000000000050000002658400000000000000209999999000106SW123456789"
        )

    def test_naonif_sem_intermediario(self):
        s = build_sign_string_v2(**BASE, tomador={"nao_nif": "2"})
        assert s == (
            "123456789012RTNT 00000000000120260101TNN00000000205000"
            "0000000000500000026584000000000000002"
        )

    def test_naonif_com_intermediario(self):
        s = build_sign_string_v2(
            **BASE,
            tomador={"nao_nif": "2"},
            intermediario={"cnpj": "09999999000106", "iss_retido": True},
        )
        assert s == (
            "123456789012RTNT 00000000000120260101TNN00000000205000"
            "000000000050000002658400000000000000209999999000106S2"
        )


class TestFormatacao:
    def test_cnpj_tomador_indicador_2(self):
        s = build_sign_string_v2(**BASE, tomador={"cnpj": "04891850000188"})
        assert s.endswith("2658" + "2" + "04891850000188")

    def test_tomador_nao_informado(self):
        s = build_sign_string_v2(**BASE, tomador={})
        assert s.endswith("2658" + "3" + "0" * 14)

    def test_inscricao_completa_com_zeros(self):
        s = build_sign_string_v2(**{**BASE, "inscricao": "66467799"}, tomador={})
        assert s.startswith("000066467799")

    def test_serie_menor_preenche_espacos(self):
        s = build_sign_string_v2(**{**BASE, "serie": "PM"}, tomador={})
        assert s[12:17] == "PM   "

    def test_iss_retido_s(self):
        s = build_sign_string_v2(**{**BASE, "iss_retido": True}, tomador={})
        assert s[39] == "S"
