"""Parser dos retornos do webservice da prefeitura."""
from lxml import etree

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"


class RespostaInvalidaError(Exception):
    pass


def _fromstring(xml: str) -> etree._Element:
    try:
        return etree.fromstring(xml.encode("utf-8"))
    except etree.XMLSyntaxError as e:
        raise RespostaInvalidaError(f"XML invalido na resposta: {e}") from e


def extrair_retorno_soap(response_text: str) -> str:
    """Extrai o XML de retorno de dentro do envelope SOAP de resposta.

    O ASMX devolve o retorno como texto escapado dentro de RetornoXML (ou
    do elemento *Result). O .text do lxml ja vem desescapado.
    """
    root = _fromstring(response_text)
    for el in root.iter():
        tag = etree.QName(el).localname if isinstance(el.tag, str) else ""
        if tag in ("RetornoXML",) or tag.endswith("Result"):
            if el.text and el.text.strip():
                return el.text.strip()
    raise RespostaInvalidaError("Envelope SOAP sem RetornoXML/Result")


def _sucesso(retorno: etree._Element) -> bool:
    el = retorno.find(".//Sucesso")
    return el is not None and (el.text or "").strip().lower() == "true"


def _eventos(retorno: etree._Element, tag: str) -> list[dict]:
    out = []
    for ev in retorno.findall(f".//{tag}"):
        out.append({
            "codigo": ev.findtext("Codigo", "").strip(),
            "descricao": ev.findtext("Descricao", "").strip(),
        })
    return out


def parse_retorno_envio(xml_str: str) -> dict:
    """Parseia RetornoEnvioRPS (ou o retorno do TesteEnvioRPS)."""
    retorno = _fromstring(xml_str)
    resultado = {
        "sucesso": _sucesso(retorno),
        "erros": _eventos(retorno, "Erro"),
        "alertas": _eventos(retorno, "Alerta"),
        "numero_nfse": None,
        "codigo_verificacao": None,
        "numero_rps": None,
        "serie_rps": None,
    }
    chave = retorno.find(".//ChaveNFeRPS")
    if chave is not None:
        nfe = chave.find("ChaveNFe")
        if nfe is not None:
            resultado["numero_nfse"] = nfe.findtext("NumeroNFe")
            resultado["codigo_verificacao"] = nfe.findtext("CodigoVerificacao")
        rps = chave.find("ChaveRPS")
        if rps is not None:
            resultado["numero_rps"] = rps.findtext("NumeroRPS")
            resultado["serie_rps"] = rps.findtext("SerieRPS")
    return resultado


def parse_retorno_cancelamento(xml_str: str) -> dict:
    retorno = _fromstring(xml_str)
    return {
        "sucesso": _sucesso(retorno),
        "erros": _eventos(retorno, "Erro"),
        "alertas": _eventos(retorno, "Alerta"),
    }


def parse_retorno_consulta(xml_str: str) -> list[dict]:
    """Parseia RetornoConsulta (ConsultaNFe / ConsultaNFePeriodo).

    Retorna uma entrada por NFe encontrada.
    """
    retorno = _fromstring(xml_str)
    notas = []
    for nfe in retorno.findall(".//NFe"):
        chave = nfe.find("ChaveNFe")
        tomador_doc = ""
        cpfcnpj = nfe.find("CPFCNPJTomador")
        if cpfcnpj is not None:
            tomador_doc = (cpfcnpj.findtext("CNPJ") or cpfcnpj.findtext("CPF") or "")
        valor = (
            nfe.findtext("ValorFinalCobrado")
            or nfe.findtext("ValorInicialCobrado")
            or nfe.findtext("ValorServicos")
            or "0"
        )
        notas.append({
            "numero_nfse": chave.findtext("NumeroNFe") if chave is not None else None,
            "codigo_verificacao": chave.findtext("CodigoVerificacao") if chave is not None else None,
            "data_emissao": nfe.findtext("DataEmissaoNFe"),
            "status": nfe.findtext("StatusNFe"),
            "valor": float(valor),
            "codigo_servico": nfe.findtext("CodigoServico"),
            "tomador_nome": nfe.findtext("RazaoSocialTomador"),
            "tomador_doc": tomador_doc,
            "discriminacao": nfe.findtext("Discriminacao"),
            "numero_rps": (nfe.find("ChaveRPS").findtext("NumeroRPS")
                           if nfe.find("ChaveRPS") is not None else None),
        })
    return notas
