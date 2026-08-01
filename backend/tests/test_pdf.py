import pytest
import requests

from app.nfse.pdf import PdfIndisponivelError, baixar_pdf, montar_url_pdf


class RespostaFake:
    def __init__(self, ok=True, status_code=200, content=b"%PDF-1.7 conteudo"):
        self.ok = ok
        self.status_code = status_code
        self.content = content


class TestMontarUrl:
    def test_url_com_chave_da_nota(self):
        url = montar_url_pdf("66467799", "1594", "XLSH4APE")
        assert url.startswith(
            "https://nfe.prefeitura.sp.gov.br/contribuinte/notaprintpdf.aspx?"
        )
        assert "inscricao=66467799" in url
        assert "nf=1594" in url
        assert "verificacao=XLSH4APE" in url

    def test_limpa_pontuacao_da_inscricao(self):
        assert "inscricao=66467799" in montar_url_pdf("664.677-99", "1", "X")


class TestBaixarPdf:
    def test_pdf_valido(self, monkeypatch):
        monkeypatch.setattr(requests, "get", lambda *a, **kw: RespostaFake())
        assert baixar_pdf("66467799", "1594", "XLSH4APE").startswith(b"%PDF")

    def test_html_de_erro_com_status_200(self, monkeypatch):
        # A prefeitura devolve HTML com 200 quando a chave nao bate
        monkeypatch.setattr(
            requests, "get",
            lambda *a, **kw: RespostaFake(content=b"<html>erro</html>"),
        )
        with pytest.raises(PdfIndisponivelError) as exc:
            baixar_pdf("66467799", "1594", "ERRADO")
        assert "codigo" in str(exc.value)

    def test_http_erro(self, monkeypatch):
        monkeypatch.setattr(
            requests, "get",
            lambda *a, **kw: RespostaFake(ok=False, status_code=500),
        )
        with pytest.raises(PdfIndisponivelError):
            baixar_pdf("66467799", "1594", "XLSH4APE")

    def test_rede_fora(self, monkeypatch):
        def falha(*a, **kw):
            raise requests.exceptions.Timeout("timeout")

        monkeypatch.setattr(requests, "get", falha)
        with pytest.raises(PdfIndisponivelError):
            baixar_pdf("66467799", "1594", "XLSH4APE")
