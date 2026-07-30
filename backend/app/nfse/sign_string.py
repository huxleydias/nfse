"""String de assinatura do RPS, layout versao 2 (reforma tributaria).

Regra do manual NFe_Web_Service v3.3.7, quadro "Campos para assinatura do
RPS - versao 2.0". Diferencas da v1: inscricao com 12 posicoes (era 8),
ValorInicialCobrado ou ValorFinalCobrado no lugar de ValorServicos,
indicador de tomador aceita 4 (NIF) e campo 16 (NIF ou NaoNIF) no final.
"""
from datetime import date

from .utils import so_digitos, valor_centavos


def _indicador_doc(pessoa: dict) -> tuple[str, str]:
    """Retorna (indicador, documento com 14 posicoes)."""
    cnpj = so_digitos(pessoa.get("cnpj", ""))
    cpf = so_digitos(pessoa.get("cpf", ""))
    if cnpj:
        return "2", cnpj.zfill(14)
    if cpf:
        return "1", cpf.zfill(14)
    if pessoa.get("nif") or pessoa.get("nao_nif"):
        return "4", "0" * 14
    return "3", "0" * 14


def build_sign_string_v2(
    inscricao: str,
    serie: str,
    numero: int,
    data_emissao: date,
    tributacao: str,
    status: str,
    iss_retido: bool,
    valor_cobrado: float,
    deducoes: float,
    cod_servico: str,
    tomador: dict,
    intermediario: dict | None = None,
) -> str:
    partes = [
        so_digitos(inscricao).zfill(12),
        serie[:5].ljust(5),
        str(numero).zfill(12),
        data_emissao.strftime("%Y%m%d"),
        tributacao[0].upper(),
        status[0].upper(),
        "S" if iss_retido else "N",
        valor_centavos(valor_cobrado),
        valor_centavos(deducoes),
        so_digitos(cod_servico).zfill(5),
    ]

    ind_tomador, doc_tomador = _indicador_doc(tomador)
    partes.append(ind_tomador)
    partes.append(doc_tomador)

    if intermediario:
        ind_int, doc_int = _indicador_doc(intermediario)
        partes.append(ind_int)
        partes.append(doc_int)
        partes.append("S" if intermediario.get("iss_retido") else "N")

    if ind_tomador == "4":
        partes.append(tomador.get("nif") or tomador["nao_nif"])

    return "".join(partes)
