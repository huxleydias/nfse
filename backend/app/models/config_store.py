"""Config da aplicacao em linha unica JSON no banco (chave/valor)."""
import json

from sqlalchemy import Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ConfigRow(Base):
    __tablename__ = "config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dados: Mapped[str] = mapped_column(Text, default="{}")


CONFIG_DEFAULT = {
    "prestador": {
        "cnpj": "",
        "inscricao_municipal": "",
        "razao_social": "",
        "email": "",
    },
    "servicos": {},
    "serie_rps": "PM",
    "proximo_numero_rps": 8,
    "modo_teste": True,
    "tributacao": "T",
    # 1 = layout pre reforma (obrigatorio para optantes do Simples Nacional
    # ate a reforma valer para o regime). 2 = layout da reforma IBS/CBS.
    "layout": 1,
}

# Exemplo de servico em config["servicos"]:
# "05762": {
#   "descricao_padrao": "Servicos de instrucao e treinamento.",
#   "aliquota": 0.02, "iss_retido": False,
#   "nbs": "000000000", "c_class_trib": "000001", "c_ind_op": "000000",
#   "fin_nfse": 0, "ind_final": 1, "ind_dest": 0,
#   "c_loc_prestacao": "3550308"
# }


def get_config(session) -> dict:
    row = session.get(ConfigRow, 1)
    if row is None:
        row = ConfigRow(id=1, dados=json.dumps(CONFIG_DEFAULT))
        session.add(row)
        session.commit()
    cfg = json.loads(row.dados)
    # Chaves novas ganham default sem quebrar config antiga
    for chave, valor in CONFIG_DEFAULT.items():
        cfg.setdefault(chave, valor)
    return cfg


def save_config(session, cfg: dict) -> None:
    row = session.get(ConfigRow, 1)
    if row is None:
        row = ConfigRow(id=1)
        session.add(row)
    row.dados = json.dumps(cfg, ensure_ascii=False)
    session.commit()


def alocar_numero_rps(session) -> int:
    """Aloca o proximo numero de RPS e incrementa o contador.

    Numero queimado em falha posterior e aceitavel: a prefeitura tolera
    lacunas na numeracao.
    """
    cfg = get_config(session)
    numero = int(cfg["proximo_numero_rps"])
    cfg["proximo_numero_rps"] = numero + 1
    save_config(session, cfg)
    return numero
