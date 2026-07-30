from app.nfse.utils import valor_centavos, so_digitos, validar_cpf, validar_cnpj


class TestValorCentavos:
    def test_exemplo_manual_com_centavos(self):
        assert valor_centavos(500.85) == "000000000050085"

    def test_exemplo_manual_sem_centavos(self):
        assert valor_centavos(500.00) == "000000000050000"

    def test_exemplo_assinatura_v2(self):
        assert valor_centavos(20500.00) == "000000002050000"

    def test_deducao_exemplo_v2(self):
        assert valor_centavos(5000.00) == "000000000500000"

    def test_arredondamento_float(self):
        assert valor_centavos(599.90) == "000000000059990"


class TestSoDigitos:
    def test_cnpj_formatado(self):
        assert so_digitos("37.624.983/0001-47") == "37624983000147"

    def test_vazio_e_none(self):
        assert so_digitos("") == ""
        assert so_digitos(None) == ""


class TestValidarCpf:
    def test_valido(self):
        assert validar_cpf("111.444.777-35")

    def test_invalido(self):
        assert not validar_cpf("111.444.777-36")

    def test_repetido(self):
        assert not validar_cpf("11111111111")

    def test_curto(self):
        assert not validar_cpf("123")


class TestValidarCnpj:
    def test_valido(self):
        assert validar_cnpj("37.624.983/0001-47")

    def test_invalido(self):
        assert not validar_cnpj("37.624.983/0001-48")

    def test_repetido(self):
        assert not validar_cnpj("11111111111111")
