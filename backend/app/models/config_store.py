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
    # Onde a nota e emitida: "municipal" (webservice da prefeitura de SP) ou
    # "nacional" (Sefin Nacional). ME/EPP do Simples emitem so no nacional
    # para competencias a partir de 01/11/2026 (Resolucao CGSN 191/2026).
    "ambiente": "municipal",
    "nacional": {
        # Serie numerica da DPS: 1 a 49999 para aplicativo proprio
        "serie_dps": "1",
        # Contadores so avancam. Homologacao tem contador proprio para o
        # teste nao abrir lacuna na sequencia real.
        "proximo_numero_dps": 1,
        "proximo_numero_dps_homologacao": 1,
        # Municipio emissor (IBGE). 3550308 = Sao Paulo
        "c_loc_emi": "3550308",
        # Situacao no Simples: 1 nao optante, 2 MEI, 3 ME/EPP
        "op_simp_nac": 3,
        # Apuracao do Simples (so para ME/EPP): 1 federais e ISSQN pelo SN
        "reg_ap_trib_sn": 1,
        # Regime especial de tributacao: 0 nenhum
        "reg_esp_trib": 0,
        # Percentual aproximado de tributos do Simples (pTotTribSN). Sem valor
        # configurado a emissao nacional de ME/EPP e recusada antes de enviar.
        "p_tot_trib_sn": None,
        # Informar a inscricao municipal na DPS. So vale se o prestador tiver
        # registro complementar no CNC do municipio emissor.
        "informar_im": True,
    },
}

AMBIENTES = ("municipal", "nacional")

# Chaves de CONFIG_DEFAULT que sao dicionarios: config antiga ganha as
# subchaves novas sem perder o que ja estava gravado.
_BLOCOS_ANINHADOS = ("nacional",)

# Exemplo de servico em config["servicos"]:
# "05762": {
#   "descricao_padrao": "Servicos de instrucao e treinamento.",
#   "aliquota": 0.02, "iss_retido": False,
#   "nbs": "000000000", "c_class_trib": "000001", "c_ind_op": "000000",
#   "fin_nfse": 0, "ind_final": 1, "ind_dest": 0,
#   "c_loc_prestacao": "3550308",
#   "c_trib_nac": "080201", "c_nbs": ""
# }
# c_trib_nac (codigo de tributacao nacional, 6 digitos) e c_nbs (9 digitos,
# opcional) so sao usados no ambiente nacional.


def get_config(session) -> dict:
    row = session.get(ConfigRow, 1)
    if row is None:
        row = ConfigRow(id=1, dados=json.dumps(CONFIG_DEFAULT))
        session.add(row)
        session.commit()
    cfg = json.loads(row.dados)
    # Chaves novas ganham default sem quebrar config antiga
    for chave, valor in CONFIG_DEFAULT.items():
        if chave in _BLOCOS_ANINHADOS:
            atual = cfg.get(chave) if isinstance(cfg.get(chave), dict) else {}
            cfg[chave] = {**valor, **atual}
        else:
            cfg.setdefault(chave, valor)
    return cfg


def ambiente_config(cfg: dict) -> str:
    ambiente = cfg.get("ambiente", "municipal")
    return ambiente if ambiente in AMBIENTES else "municipal"


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


def alocar_numero_dps(session, homologacao: bool) -> int:
    """Aloca o proximo numero de DPS do ambiente nacional e incrementa.

    Producao e homologacao tem contadores separados. Numero recusado pelo
    Sistema Nacional nao vira NFS-e e e reaproveitado na nova tentativa da
    mesma ref_externa (ver emissor nacional).
    """
    cfg = get_config(session)
    chave = "proximo_numero_dps_homologacao" if homologacao else "proximo_numero_dps"
    numero = int(cfg["nacional"][chave])
    cfg["nacional"][chave] = numero + 1
    save_config(session, cfg)
    return numero
