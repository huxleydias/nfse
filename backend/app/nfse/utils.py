"""Utilitarios de formatacao de valores e validacao de documentos."""


def valor_centavos(valor: float, tamanho: int = 15) -> str:
    """Formata valor em reais como centavos com zeros a esquerda.

    Exemplos do manual: R$ 500,85 -> 000000000050085; R$ 500,00 -> 000000000050000.
    """
    centavos = round(valor * 100)
    return str(centavos).zfill(tamanho)


def so_digitos(s: str) -> str:
    """Remove tudo que nao for digito."""
    return "".join(c for c in (s or "") if c.isdigit())


def _digito_cpf(digitos: str, pesos: range) -> int:
    soma = sum(int(d) * p for d, p in zip(digitos, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def validar_cpf(cpf: str) -> bool:
    cpf = so_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    d1 = _digito_cpf(cpf[:9], range(10, 1, -1))
    d2 = _digito_cpf(cpf[:10], range(11, 1, -1))
    return cpf[9] == str(d1) and cpf[10] == str(d2)


def _digito_cnpj(digitos: str, pesos: list[int]) -> int:
    soma = sum(int(d) * p for d, p in zip(digitos, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def validar_cnpj(cnpj: str) -> bool:
    cnpj = so_digitos(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    d1 = _digito_cnpj(cnpj[:12], pesos1)
    d2 = _digito_cnpj(cnpj[:13], pesos2)
    return cnpj[12] == str(d1) and cnpj[13] == str(d2)
