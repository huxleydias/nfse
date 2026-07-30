from datetime import datetime, timezone

from sqlalchemy import Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _agora():
    return datetime.now(timezone.utc).isoformat()


class Nota(Base):
    __tablename__ = "notas"
    __table_args__ = (UniqueConstraint("ref_externa", name="uq_notas_ref_externa"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ref_externa: Mapped[str | None] = mapped_column(String(120), nullable=True)
    numero_rps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    serie_rps: Mapped[str | None] = mapped_column(String(5), nullable=True)
    numero_nfse: Mapped[str | None] = mapped_column(String(20), nullable=True)
    codigo_verificacao: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tomador_nome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tomador_doc: Mapped[str | None] = mapped_column(String(14), nullable=True)
    valor: Mapped[float] = mapped_column(Float, default=0.0)
    codigo_servico: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # autorizada | cancelada | erro | processando
    status: Mapped[str] = mapped_column(String(20), default="processando")
    xml_enviado: Mapped[str | None] = mapped_column(Text, nullable=True)
    xml_retorno: Mapped[str | None] = mapped_column(Text, nullable=True)
    erros_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    criada_em: Mapped[str] = mapped_column(String(40), default=_agora)
    atualizada_em: Mapped[str] = mapped_column(String(40), default=_agora, onupdate=_agora)

    def to_dict(self, com_xml: bool = False) -> dict:
        d = {
            "id": self.id,
            "ref_externa": self.ref_externa,
            "numero_rps": self.numero_rps,
            "serie_rps": self.serie_rps,
            "numero_nfse": self.numero_nfse,
            "codigo_verificacao": self.codigo_verificacao,
            "tomador_nome": self.tomador_nome,
            "tomador_doc": self.tomador_doc,
            "valor": self.valor,
            "codigo_servico": self.codigo_servico,
            "status": self.status,
            "erros_json": self.erros_json,
            "criada_em": self.criada_em,
            "atualizada_em": self.atualizada_em,
        }
        if com_xml:
            d["xml_enviado"] = self.xml_enviado
            d["xml_retorno"] = self.xml_retorno
        return d
