"""Migracao do banco existente e defaults da configuracao nacional."""
import json
import sqlite3

from app.models.config_store import (
    CONFIG_DEFAULT,
    alocar_numero_dps,
    ambiente_config,
    get_config,
    save_config,
)
from app.models.nota import Nota
from tests.test_emitter import session  # noqa: F401  (fixture)

ESQUEMA_ANTIGO = """
CREATE TABLE notas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_externa VARCHAR(120),
    numero_rps INTEGER,
    serie_rps VARCHAR(5),
    numero_nfse VARCHAR(20),
    codigo_verificacao VARCHAR(20),
    tomador_nome VARCHAR(120),
    tomador_doc VARCHAR(14),
    valor FLOAT,
    codigo_servico VARCHAR(5),
    status VARCHAR(20),
    xml_enviado TEXT,
    xml_retorno TEXT,
    erros_json TEXT,
    criada_em VARCHAR(40),
    atualizada_em VARCHAR(40),
    CONSTRAINT uq_notas_ref_externa UNIQUE (ref_externa)
);
CREATE TABLE config (id INTEGER PRIMARY KEY, dados TEXT);
"""


def test_banco_antigo_ganha_colunas_sem_perder_notas(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "chave-de-teste-para-fernet-e-sessao")
    conn = sqlite3.connect(tmp_path / "nfse.db")
    conn.executescript(ESQUEMA_ANTIGO)
    conn.execute(
        "INSERT INTO notas (ref_externa, numero_nfse, codigo_verificacao, valor, status, "
        "criada_em, atualizada_em) VALUES ('wc-antiga', '123', 'ABCD1234', 599.0, "
        "'autorizada', '2026-10-01', '2026-10-01')"
    )
    conn.execute("INSERT INTO config (id, dados) VALUES (1, ?)",
                 (json.dumps({"layout": 1, "modo_teste": False}),))
    conn.commit()
    conn.close()

    from app.core import db
    db.reset_engine_para_testes()
    db.init_db()
    db.init_db()  # idempotente
    s = db.get_session()
    try:
        nota = s.query(Nota).one()
        assert nota.ref_externa == "wc-antiga"
        assert nota.numero_nfse == "123"
        assert nota.ambiente == "municipal"
        assert nota.chave_acesso is None and nota.numero_dps is None

        cfg = get_config(s)
        assert cfg["modo_teste"] is False
        assert cfg["ambiente"] == "municipal"
        assert cfg["nacional"]["proximo_numero_dps"] == 1
    finally:
        s.close()
        db.reset_engine_para_testes()

    colunas = {linha[1] for linha in sqlite3.connect(tmp_path / "nfse.db").execute(
        "PRAGMA table_info(notas)")}
    assert {"ambiente", "chave_acesso", "serie_dps", "numero_dps", "competencia",
            "xml_evento"} <= colunas


def test_bloco_nacional_parcial_recebe_defaults(session):  # noqa: F811
    cfg = get_config(session)
    cfg["nacional"] = {"p_tot_trib_sn": 6.0}
    save_config(session, cfg)
    nac = get_config(session)["nacional"]
    assert nac["p_tot_trib_sn"] == 6.0
    assert nac["serie_dps"] == "1"
    assert nac["c_loc_emi"] == "3550308"


def test_default_nao_e_alterado_por_quem_le(session):  # noqa: F811
    cfg = get_config(session)
    cfg["nacional"]["p_tot_trib_sn"] = 9.0
    assert CONFIG_DEFAULT["nacional"]["p_tot_trib_sn"] is None


def test_contadores_separados(session):  # noqa: F811
    assert alocar_numero_dps(session, homologacao=False) == 1
    assert alocar_numero_dps(session, homologacao=False) == 2
    assert alocar_numero_dps(session, homologacao=True) == 1
    nac = get_config(session)["nacional"]
    assert nac["proximo_numero_dps"] == 3
    assert nac["proximo_numero_dps_homologacao"] == 2


def test_ambiente_invalido_cai_no_municipal():
    assert ambiente_config({"ambiente": "outro"}) == "municipal"
    assert ambiente_config({}) == "municipal"
    assert ambiente_config({"ambiente": "nacional"}) == "nacional"
