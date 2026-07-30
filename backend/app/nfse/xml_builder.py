"""Monta o XML PedidoEnvioRPS layout versao 2 (reforma tributaria IBS/CBS).

Ordem dos elementos segue a sequencia exata do tpRPS no TiposNFe_v02.xsd.
Root no namespace da prefeitura; filhos sem namespace (elementFormDefault
unqualified nos XSDs oficiais).
"""
from datetime import date

from lxml import etree

from .utils import so_digitos

NFE_NS = "http://www.prefeitura.sp.gov.br/nfe"


def _dec(valor: float) -> str:
    """Formata decimal conforme tpValor: 2 casas, sem zeros a esquerda."""
    texto = f"{valor:.2f}"
    if texto.startswith("0") and texto != "0.00" and not texto.startswith("0."):
        texto = texto.lstrip("0")
    return texto


def _aliquota(valor: float) -> str:
    """Formata aliquota como fracao (ex.: 0.02 para 2%), ate 4 casas."""
    texto = f"{valor:.4f}".rstrip("0")
    if texto.endswith("."):
        texto += "0"
    return texto


def _el(parent, tag: str, text=None):
    el = etree.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el


def build_pedido_envio_rps(prestador: dict, rps: dict, assinatura_b64: str) -> etree._Element:
    """Monta o elemento PedidoEnvioRPS completo (sem a ds:Signature, que e
    adicionada pelo signer.sign_xml_enveloped)."""
    root = etree.Element(f"{{{NFE_NS}}}PedidoEnvioRPS", nsmap={"p1": NFE_NS})

    cab = _el(root, "Cabecalho")
    cab.set("Versao", "2")
    remetente = _el(cab, "CPFCNPJRemetente")
    _el(remetente, "CNPJ", so_digitos(prestador["cnpj"]))

    rps_el = _el(root, "RPS")
    _el(rps_el, "Assinatura", assinatura_b64)

    chave = _el(rps_el, "ChaveRPS")
    _el(chave, "InscricaoPrestador", so_digitos(prestador["inscricao_municipal"]))
    _el(chave, "SerieRPS", rps["serie"])
    _el(chave, "NumeroRPS", rps["numero"])

    _el(rps_el, "TipoRPS", "RPS")
    data: date = rps["data_emissao"]
    _el(rps_el, "DataEmissao", data.isoformat())
    _el(rps_el, "StatusRPS", rps.get("status", "N"))
    _el(rps_el, "TributacaoRPS", rps.get("tributacao", "T"))

    ret = rps.get("valores_retencao", {})
    _el(rps_el, "ValorDeducoes", _dec(rps.get("deducoes", 0.0)))
    _el(rps_el, "ValorPIS", _dec(ret.get("pis", 0.0)))
    _el(rps_el, "ValorCOFINS", _dec(ret.get("cofins", 0.0)))
    _el(rps_el, "ValorINSS", _dec(ret.get("inss", 0.0)))
    _el(rps_el, "ValorIR", _dec(ret.get("ir", 0.0)))
    _el(rps_el, "ValorCSLL", _dec(ret.get("csll", 0.0)))

    _el(rps_el, "CodigoServico", so_digitos(rps["codigo_servico"]))
    _el(rps_el, "AliquotaServicos", _aliquota(rps["aliquota"]))
    _el(rps_el, "ISSRetido", "true" if rps.get("iss_retido") else "false")

    tomador = rps["tomador"]
    doc = so_digitos(tomador.get("cpf_cnpj", ""))
    if doc:
        cpfcnpj = _el(rps_el, "CPFCNPJTomador")
        _el(cpfcnpj, "CNPJ" if len(doc) == 14 else "CPF", doc)

    if tomador.get("razao_social"):
        _el(rps_el, "RazaoSocialTomador", tomador["razao_social"][:75])

    endereco = tomador.get("endereco") or {}
    if endereco.get("logradouro"):
        end_el = _el(rps_el, "EnderecoTomador")
        if endereco.get("tipo_logradouro"):
            _el(end_el, "TipoLogradouro", endereco["tipo_logradouro"][:3])
        _el(end_el, "Logradouro", endereco["logradouro"][:50])
        if endereco.get("numero"):
            _el(end_el, "NumeroEndereco", endereco["numero"][:10])
        if endereco.get("complemento"):
            _el(end_el, "ComplementoEndereco", endereco["complemento"][:30])
        if endereco.get("bairro"):
            _el(end_el, "Bairro", endereco["bairro"][:30])
        if endereco.get("codigo_municipio"):
            _el(end_el, "Cidade", so_digitos(endereco["codigo_municipio"]))
        if endereco.get("uf"):
            _el(end_el, "UF", endereco["uf"][:2].upper())
        if endereco.get("cep"):
            _el(end_el, "CEP", so_digitos(endereco["cep"]))

    if tomador.get("email"):
        _el(rps_el, "EmailTomador", tomador["email"][:75])

    _el(rps_el, "Discriminacao", rps["discriminacao"][:2000])

    # xs:choice no XSD: ValorInicialCobrado OU ValorFinalCobrado.
    # Usamos ValorFinalCobrado: valor total da nota com tributos por dentro
    # (calculo do fim para o inicio), que e como a PunkMetrics cobra.
    _el(rps_el, "ValorFinalCobrado", _dec(rps["valor"]))

    fiscal = rps["fiscal"]
    _el(rps_el, "ValorIPI", _dec(fiscal.get("valor_ipi", 0.0)))
    _el(rps_el, "ExigibilidadeSuspensa", fiscal.get("exigibilidade_suspensa", 0))
    _el(rps_el, "NBS", fiscal["nbs"])

    # Grupo gpPrestacao (obrigatorio): local da prestacao do servico.
    # cLocPrestacao = codigo IBGE do municipio (3550308 = Sao Paulo).
    _el(rps_el, "cLocPrestacao", so_digitos(str(fiscal.get("c_loc_prestacao", "3550308"))))

    ibscbs = _el(rps_el, "IBSCBS")
    _el(ibscbs, "finNFSe", fiscal.get("fin_nfse", 0))
    _el(ibscbs, "indFinal", fiscal.get("ind_final", 1))
    _el(ibscbs, "cIndOp", fiscal["c_ind_op"])
    _el(ibscbs, "indDest", fiscal.get("ind_dest", 0))
    valores = _el(ibscbs, "valores")
    trib = _el(valores, "trib")
    gibscbs = _el(trib, "gIBSCBS")
    _el(gibscbs, "cClassTrib", fiscal["c_class_trib"])

    return root


def xml_to_string(root: etree._Element) -> str:
    return etree.tostring(root, encoding="unicode")
