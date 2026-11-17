"""Montagem da DPS (Declaracao de Prestacao de Servicos) v1.01.

Regras do Anexo I que moldam este builder:
- Sem prefixo de namespace no XML (E1228).
- Emitente prestador (tpEmit 1) nao informa nome nem endereco do prestador
  (E0121, E0128).
- ME/EPP com apuracao pelo Simples e sem retencao nao informa aliquota
  (E0625, E0631).
- ME/EPP nunca informa indTotTrib (E0712): o total aproximado de tributos vai
  em pTotTribSN.
- Leiaute NT 009: finNFSe (0, NFS-e regular) logo depois de tpEmit, que a NT
  004 nao tem, e xDescServ no fim de cServ (na NT 004 vem antes de cNBS).
"""
from datetime import date, datetime

from lxml import etree

from app.nfse.utils import so_digitos

from . import LEIAUTE_NT004, LEIAUTE_NT009, NS, VER_APLIC, VERSAO_LEIAUTE

TP_EMIT_PRESTADOR = "1"
FIN_NFSE_REGULAR = "0"
TRIB_ISSQN_TRIBUTAVEL = "1"
RET_ISSQN_NAO_RETIDO = "1"


def _el(parent, tag: str, text=None):
    el = etree.SubElement(parent, f"{{{NS}}}{tag}")
    if text is not None:
        el.text = str(text)
    return el


def dec2(valor: float) -> str:
    """Decimal com duas casas no formato dos tipos TSDec*V2 ("999.00")."""
    return f"{round(float(valor), 2):.2f}"


def serie_formatada(serie) -> str:
    """Serie da DPS com 5 digitos, como entra no Id e no XML."""
    digitos = so_digitos(str(serie))
    if not digitos or not 1 <= int(digitos) <= 49999:
        raise ValueError("Serie da DPS deve ser um numero de 1 a 49999")
    return str(int(digitos)).zfill(5)


def tipo_inscricao(doc: str) -> str:
    """1 para CPF, 2 para CNPJ (regra de formacao dos Ids)."""
    return "2" if len(so_digitos(doc)) == 14 else "1"


def montar_id_dps(c_loc_emi: str, doc_prestador: str, serie, numero: int) -> str:
    """"DPS" + municipio (7) + tipo de inscricao (1) + inscricao (14) +
    serie (5) + numero (15) = 45 posicoes."""
    doc = so_digitos(doc_prestador)
    return (
        f"DPS{so_digitos(c_loc_emi)}{tipo_inscricao(doc)}{doc.zfill(14)}"
        f"{serie_formatada(serie)}{int(numero):015d}"
    )


def _documento(parent, doc: str) -> None:
    doc = so_digitos(doc)
    _el(parent, "CNPJ" if len(doc) == 14 else "CPF", doc)


def _endereco_completo(endereco: dict | None) -> bool:
    """Endereco so entra na DPS com municipio, CEP, logradouro e bairro."""
    if not endereco:
        return False
    return bool(
        so_digitos(endereco.get("cep") or "")
        and so_digitos(endereco.get("codigo_municipio") or "")
        and (endereco.get("logradouro") or "").strip()
        and (endereco.get("bairro") or "").strip()
    )


def _endereco(parent, endereco: dict) -> None:
    end = _el(parent, "end")
    nac = _el(end, "endNac")
    _el(nac, "cMun", so_digitos(endereco["codigo_municipio"]))
    _el(nac, "CEP", so_digitos(endereco["cep"]))
    logradouro = " ".join(
        p for p in (endereco.get("tipo_logradouro", "").strip(),
                    endereco.get("logradouro", "").strip()) if p
    )
    _el(end, "xLgr", logradouro)
    _el(end, "nro", (endereco.get("numero") or "").strip() or "S/N")
    if (endereco.get("complemento") or "").strip():
        _el(end, "xCpl", endereco["complemento"].strip())
    _el(end, "xBairro", endereco["bairro"].strip())


def build_dps(dados: dict) -> etree._Element:
    """Monta a DPS sem assinatura.

    dados: tp_amb (1 producao, 2 homologacao), dh_emi (datetime com fuso),
    serie, numero, competencia (date), c_loc_emi, prestador {cnpj, im},
    reg_trib {op_simp_nac, reg_ap_trib_sn, reg_esp_trib},
    tomador {cpf_cnpj, razao_social, email, endereco}, servico
    {c_loc_prestacao, c_trib_nac, c_trib_mun, descricao, c_nbs}, valor, p_tot_trib_sn,
    leiaute (LEIAUTE_NT004 por padrao).
    """
    prestador = dados["prestador"]
    id_dps = montar_id_dps(
        dados["c_loc_emi"], prestador["cnpj"], dados["serie"], dados["numero"]
    )

    root = etree.Element(f"{{{NS}}}DPS", nsmap={None: NS})
    root.set("versao", VERSAO_LEIAUTE)
    inf = _el(root, "infDPS")
    inf.set("Id", id_dps)

    dh_emi: datetime = dados["dh_emi"]
    competencia: date = dados["competencia"]
    _el(inf, "tpAmb", dados["tp_amb"])
    _el(inf, "dhEmi", dh_emi.isoformat(timespec="seconds"))
    _el(inf, "verAplic", VER_APLIC)
    _el(inf, "serie", serie_formatada(dados["serie"]))
    _el(inf, "nDPS", int(dados["numero"]))
    _el(inf, "dCompet", competencia.isoformat())
    _el(inf, "tpEmit", TP_EMIT_PRESTADOR)
    if dados.get("leiaute", LEIAUTE_NT004) == LEIAUTE_NT009:
        _el(inf, "finNFSe", FIN_NFSE_REGULAR)
    _el(inf, "cLocEmi", so_digitos(dados["c_loc_emi"]))

    prest = _el(inf, "prest")
    _documento(prest, prestador["cnpj"])
    if prestador.get("im"):
        _el(prest, "IM", str(prestador["im"]).strip())
    reg = _el(prest, "regTrib")
    op_simp_nac = str(dados["reg_trib"]["op_simp_nac"])
    _el(reg, "opSimpNac", op_simp_nac)
    if op_simp_nac == "3":
        _el(reg, "regApTribSN", dados["reg_trib"]["reg_ap_trib_sn"])
    _el(reg, "regEspTrib", dados["reg_trib"].get("reg_esp_trib", 0))

    tomador = dados["tomador"]
    toma = _el(inf, "toma")
    _documento(toma, tomador["cpf_cnpj"])
    _el(toma, "xNome", tomador["razao_social"].strip())
    if _endereco_completo(tomador.get("endereco")):
        _endereco(toma, tomador["endereco"])
    if (tomador.get("email") or "").strip():
        _el(toma, "email", tomador["email"].strip())

    servico = dados["servico"]
    serv = _el(inf, "serv")
    loc = _el(serv, "locPrest")
    _el(loc, "cLocPrestacao", so_digitos(servico["c_loc_prestacao"]))
    cserv = _el(serv, "cServ")
    _el(cserv, "cTribNac", so_digitos(servico["c_trib_nac"]))
    if so_digitos(servico.get("c_trib_mun") or ""):
        _el(cserv, "cTribMun", so_digitos(servico["c_trib_mun"]))
    nbs = so_digitos(servico.get("c_nbs") or "")
    # NT 009 move xDescServ para depois de cNBS
    if dados.get("leiaute", LEIAUTE_NT004) == LEIAUTE_NT009:
        if nbs:
            _el(cserv, "cNBS", nbs)
        _el(cserv, "xDescServ", servico["descricao"])
    else:
        _el(cserv, "xDescServ", servico["descricao"])
        if nbs:
            _el(cserv, "cNBS", nbs)

    valores = _el(inf, "valores")
    vserv = _el(valores, "vServPrest")
    _el(vserv, "vServ", dec2(dados["valor"]))
    trib = _el(valores, "trib")
    trib_mun = _el(trib, "tribMun")
    _el(trib_mun, "tribISSQN", TRIB_ISSQN_TRIBUTAVEL)
    _el(trib_mun, "tpRetISSQN", RET_ISSQN_NAO_RETIDO)
    tot = _el(trib, "totTrib")
    _el(tot, "pTotTribSN", dec2(dados["p_tot_trib_sn"]))

    return root


def xml_bytes(root: etree._Element) -> bytes:
    """Serializa em UTF-8 com declaracao (E1229 exige UTF-8)."""
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")
