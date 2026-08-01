import pytest

from tests.test_api import PAYLOAD  # noqa: F401  (reaproveita as fixtures via conftest)


class TestModeloChave:
    def test_chave_tem_prefixo_e_hash(self, session_chaves):
        from app.models import api_key as modelo

        registro, chave = modelo.criar(session_chaves, "n8n")
        assert chave.startswith("nfse_")
        assert registro.prefixo == chave[:13]
        assert len(registro.prefixo) < len(chave)
        # O banco nunca guarda a chave em claro
        assert registro.hash != chave
        assert modelo.hash_chave(chave) == registro.hash

    def test_chaves_sao_unicas(self, session_chaves):
        from app.models import api_key as modelo

        _, a = modelo.criar(session_chaves, "a")
        _, b = modelo.criar(session_chaves, "b")
        assert a != b

    def test_validar_aceita_chave_ativa(self, session_chaves):
        from app.models import api_key as modelo

        _, chave = modelo.criar(session_chaves, "n8n")
        registro = modelo.validar(session_chaves, chave)
        assert registro is not None
        assert registro.ultimo_uso_em is not None

    def test_validar_recusa_chave_revogada(self, session_chaves):
        from app.models import api_key as modelo

        registro, chave = modelo.criar(session_chaves, "n8n")
        modelo.revogar(session_chaves, registro.id)
        assert modelo.validar(session_chaves, chave) is None

    def test_validar_recusa_chave_inexistente(self, session_chaves):
        from app.models import api_key as modelo

        assert modelo.validar(session_chaves, "nfse_naoexiste") is None
        assert modelo.validar(session_chaves, "") is None

    def test_revogar_e_idempotente(self, session_chaves):
        from app.models import api_key as modelo

        registro, _ = modelo.criar(session_chaves, "n8n")
        primeira = modelo.revogar(session_chaves, registro.id).revogada_em
        segunda = modelo.revogar(session_chaves, registro.id).revogada_em
        assert primeira == segunda


class TestApiChaves:
    def test_criar_mostra_a_chave_uma_vez(self, api_logada):
        r = api_logada.post("/api/chaves", json={"nome": "n8n"})
        assert r.status_code == 201
        corpo = r.json()
        assert corpo["valor"].startswith("nfse_")
        # A listagem nunca devolve o valor
        lista = api_logada.get("/api/chaves").json()["chaves"]
        assert len(lista) == 1
        assert "valor" not in lista[0]
        assert lista[0]["ativa"] is True

    def test_revogar(self, api_logada):
        criada = api_logada.post("/api/chaves", json={"nome": "n8n"}).json()["chave"]
        r = api_logada.delete(f"/api/chaves/{criada['id']}")
        assert r.status_code == 200
        assert r.json()["chave"]["ativa"] is False

    def test_revogar_inexistente(self, api_logada):
        assert api_logada.delete("/api/chaves/9999").status_code == 404

    def test_nome_obrigatorio(self, api_logada):
        assert api_logada.post("/api/chaves", json={"nome": ""}).status_code == 422

    def test_exige_sessao(self, api):
        assert api.get("/api/chaves").status_code == 401
        assert api.post("/api/chaves", json={"nome": "x"}).status_code == 401


class TestChaveAutenticaApi:
    def test_chave_criada_acessa_a_api(self, api_logada):
        chave = api_logada.post("/api/chaves", json={"nome": "n8n"}).json()["valor"]
        api_logada.cookies.clear()
        r = api_logada.get("/api/notas", headers={"Authorization": f"Bearer {chave}"})
        assert r.status_code == 200

    def test_chave_revogada_perde_acesso(self, api_logada):
        corpo = api_logada.post("/api/chaves", json={"nome": "n8n"}).json()
        api_logada.delete(f"/api/chaves/{corpo['chave']['id']}")
        api_logada.cookies.clear()
        r = api_logada.get(
            "/api/notas", headers={"Authorization": f"Bearer {corpo['valor']}"}
        )
        assert r.status_code == 401

    def test_token_do_ambiente_continua_valendo(self, api_logada):
        api_logada.cookies.clear()
        r = api_logada.get(
            "/api/notas",
            headers={"Authorization": "Bearer token-api-de-teste-com-32-chars-ok"},
        )
        assert r.status_code == 200


@pytest.fixture
def session_chaves(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "chave-de-teste-para-fernet-e-sessao")
    from app.core import db

    db.reset_engine_para_testes()
    db.init_db()
    s = db.get_session()
    yield s
    s.close()
    db.reset_engine_para_testes()
