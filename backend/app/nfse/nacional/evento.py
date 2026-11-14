"""Pedido de registro de evento: cancelamento de NFS-e (e101101)."""
from datetime import datetime

from lxml import etree

from app.nfse.utils import so_digitos

from . import NS, VER_APLIC, VERSAO_LEIAUTE
from .dps import _el

TIPO_CANCELAMENTO = "101101"
DESCRICAO_CANCELAMENTO = "Cancelamento de NFS-e"
MOTIVOS_CANCELAMENTO = {1: "Erro na Emissao", 2: "Servico nao Prestado", 9: "Outros"}
MOTIVO_PADRAO = "Erro na emissao da nota"


def montar_id_evento(chave_acesso: str, tipo_evento: str = TIPO_CANCELAMENTO) -> str:
    """"PRE" + chave de acesso (50) + tipo do evento (6)."""
    return f"PRE{so_digitos(chave_acesso)}{tipo_evento}"


def build_pedido_cancelamento(tp_amb: int, dh_evento: datetime, doc_autor: str,
                              chave_acesso: str, c_motivo: int,
                              x_motivo: str) -> etree._Element:
    root = etree.Element(f"{{{NS}}}pedRegEvento", nsmap={None: NS})
    root.set("versao", VERSAO_LEIAUTE)
    inf = _el(root, "infPedReg")
    inf.set("Id", montar_id_evento(chave_acesso))
    _el(inf, "tpAmb", tp_amb)
    _el(inf, "verAplic", VER_APLIC)
    _el(inf, "dhEvento", dh_evento.isoformat(timespec="seconds"))
    doc = so_digitos(doc_autor)
    _el(inf, "CNPJAutor" if len(doc) == 14 else "CPFAutor", doc)
    _el(inf, "chNFSe", so_digitos(chave_acesso))
    evento = _el(inf, f"e{TIPO_CANCELAMENTO}")
    _el(evento, "xDesc", DESCRICAO_CANCELAMENTO)
    _el(evento, "cMotivo", int(c_motivo))
    _el(evento, "xMotivo", x_motivo)
    return root
