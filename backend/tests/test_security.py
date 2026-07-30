import bcrypt
import pytest
from fastapi import HTTPException


@pytest.fixture(autouse=True)
def env(monkeypatch):
    hash_ = bcrypt.hashpw(b"senha-forte", bcrypt.gensalt()).decode()
    monkeypatch.setenv("SECRET_KEY", "chave-de-teste-para-fernet-e-sessao")
    monkeypatch.setenv("ADMIN_USER", "huxley")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", hash_)
    monkeypatch.setenv("API_TOKEN", "token-api-de-teste-com-32-chars-ok")


class TestLogin:
    def test_senha_certa(self):
        from app.core.security import verificar_login
        assert verificar_login("huxley", "senha-forte")

    def test_senha_errada(self):
        from app.core.security import verificar_login
        assert not verificar_login("huxley", "senha-errada")

    def test_user_errado(self):
        from app.core.security import verificar_login
        assert not verificar_login("outro", "senha-forte")

    def test_sem_hash_configurado(self, monkeypatch):
        from app.core.security import verificar_login
        monkeypatch.setenv("ADMIN_PASSWORD_HASH", "")
        assert not verificar_login("huxley", "senha-forte")


class TestSessao:
    def test_roundtrip(self):
        from app.core.security import criar_sessao, validar_sessao
        assert validar_sessao(criar_sessao("huxley"))

    def test_token_adulterado(self):
        from app.core.security import criar_sessao, validar_sessao
        assert not validar_sessao(criar_sessao("huxley") + "x")

    def test_lixo(self):
        from app.core.security import validar_sessao
        assert not validar_sessao("qualquer-coisa")


class TestBearerOuSessao:
    def test_bearer_valido(self):
        from app.core.security import bearer_ou_sessao
        bearer_ou_sessao(authorization="Bearer token-api-de-teste-com-32-chars-ok",
                         nfse_sessao=None)

    def test_bearer_invalido(self):
        from app.core.security import bearer_ou_sessao
        with pytest.raises(HTTPException) as exc:
            bearer_ou_sessao(authorization="Bearer errado", nfse_sessao=None)
        assert exc.value.status_code == 401

    def test_sessao_valida(self):
        from app.core.security import bearer_ou_sessao, criar_sessao
        bearer_ou_sessao(authorization=None, nfse_sessao=criar_sessao("huxley"))

    def test_nada(self):
        from app.core.security import bearer_ou_sessao
        with pytest.raises(HTTPException):
            bearer_ou_sessao(authorization=None, nfse_sessao=None)


class TestRateLimiter:
    def test_bloqueia_sexta_tentativa(self):
        from app.core.security import RateLimiter
        rl = RateLimiter(max_tentativas=5, janela_seg=60)
        for _ in range(5):
            assert rl.permitir("1.2.3.4")
        assert not rl.permitir("1.2.3.4")

    def test_chaves_independentes(self):
        from app.core.security import RateLimiter
        rl = RateLimiter(max_tentativas=1, janela_seg=60)
        assert rl.permitir("a")
        assert rl.permitir("b")
        assert not rl.permitir("a")
