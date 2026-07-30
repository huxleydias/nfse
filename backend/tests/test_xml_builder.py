from datetime import date

from app.nfse.xml_builder import build_pedido_envio_rps, _dec, _aliquota


PRESTADOR = {"cnpj": "37.624.983/0001-47", "inscricao_municipal": "66467799"}

FISCAL = {
    "nbs": "000000000",
    "c_class_trib": "000001",
    "c_ind_op": "000000",
    "fin_nfse": 0,
    "ind_final": 1,
    "ind_dest": 0,
    "exigibilidade_suspensa": 0,
    "valor_ipi": 0.0,
}


def rps_base(**overrides):
    d = {
        "serie": "PM",
        "numero": 8,
        "data_emissao": date(2026, 7, 30),
        "status": "N",
        "tributacao": "T",
        "iss_retido": False,
        "valor": 599.0,
        "deducoes": 0.0,
        "valores_retencao": {},
        "codigo_servico": "05762",
        "aliquota": 0.02,
        "discriminacao": "Curso IA para Designers - Pedido #999",
        "tomador": {
            "cpf_cnpj": "111.444.777-35",
            "razao_social": "Fulano de Tal",
            "email": "fulano@example.com",
        },
        "fiscal": FISCAL,
    }
    d.update(overrides)
    return d


def texto(root, tag):
    el = root.find(f".//{tag}")
    return el.text if el is not None else None


class TestBuildPedido:
    def test_cabecalho_versao_2(self):
        root = build_pedido_envio_rps(PRESTADOR, rps_base(), "QUJD")
        cab = root.find("Cabecalho")
        assert cab.get("Versao") == "2"
        assert texto(root, "CPFCNPJRemetente/CNPJ") == "37624983000147"

    def test_campos_v2_presentes(self):
        root = build_pedido_envio_rps(PRESTADOR, rps_base(), "QUJD")
        assert texto(root, "ValorInicialCobrado") == "599.00"
        assert texto(root, "ValorFinalCobrado") == "599.00"
        assert texto(root, "ValorIPI") == "0.00"
        assert texto(root, "ExigibilidadeSuspensa") == "0"
        assert texto(root, "NBS") == "000000000"
        assert texto(root, "IBSCBS/finNFSe") == "0"
        assert texto(root, "IBSCBS/cIndOp") == "000000"
        assert texto(root, "IBSCBS/valores/trib/gIBSCBS/cClassTrib") == "000001"

    def test_sem_valor_servicos_da_v1(self):
        root = build_pedido_envio_rps(PRESTADOR, rps_base(), "QUJD")
        assert root.find(".//ValorServicos") is None
        assert root.find(".//CodigoTributarioMunicipio") is None

    def test_tomador_cpf(self):
        root = build_pedido_envio_rps(PRESTADOR, rps_base(), "QUJD")
        assert texto(root, "CPFCNPJTomador/CPF") == "11144477735"
        assert root.find(".//CPFCNPJTomador/CNPJ") is None
        assert root.find(".//EnderecoTomador") is None

    def test_tomador_cnpj_com_endereco(self):
        rps = rps_base(tomador={
            "cpf_cnpj": "04.891.850/0001-88",
            "razao_social": "Empresa X LTDA",
            "endereco": {
                "logradouro": "Av Paulista",
                "numero": "1000",
                "bairro": "Bela Vista",
                "codigo_municipio": "3550308",
                "uf": "sp",
                "cep": "01310-100",
            },
        })
        root = build_pedido_envio_rps(PRESTADOR, rps, "QUJD")
        assert texto(root, "CPFCNPJTomador/CNPJ") == "04891850000188"
        assert texto(root, "EnderecoTomador/UF") == "SP"
        assert texto(root, "EnderecoTomador/CEP") == "01310100"

    def test_assinatura_rps_no_campo(self):
        root = build_pedido_envio_rps(PRESTADOR, rps_base(), "QUJDMTIz")
        assert texto(root, "RPS/Assinatura") == "QUJDMTIz"

    def test_ordem_elementos_rps(self):
        root = build_pedido_envio_rps(PRESTADOR, rps_base(), "QUJD")
        tags = [el.tag for el in root.find("RPS")]
        assert tags.index("Assinatura") < tags.index("ChaveRPS")
        assert tags.index("Discriminacao") < tags.index("ValorInicialCobrado")
        assert tags.index("NBS") < tags.index("IBSCBS")
        assert tags[-1] == "IBSCBS"


class TestFormatos:
    def test_dec_zero(self):
        assert _dec(0.0) == "0.00"

    def test_dec_valor(self):
        assert _dec(1234.5) == "1234.50"

    def test_aliquota_2_por_cento(self):
        assert _aliquota(0.02) == "0.02"

    def test_aliquota_5_por_cento(self):
        assert _aliquota(0.05) == "0.05"
