"""API REST e MCP com o ambiente nacional configurado (Sefin simulada)."""
import pytest

from app.nfse.nacional.cliente import SefinRecusouError
from tests.test_mcp import _chamar_mcp, _corpo, _iniciar, _resultado
from tests.test_nacional_cliente import chave_teste
from tests.test_nacional_emissor import SefinFake, resposta_autorizada

TOMADOR = {"cpf_cnpj": "529.982.247-25", "razao_social": "Fulano de Tal",
           "email": "fulano@exemplo.com.br"}


@pytest.fixture
def api_nacional(api_configurada, monkeypatch):
    api = api_configurada
    cfg = api.get("/api/config").json()
    cfg["servicos"]["05762"]["c_trib_nac"] = "080201"
    r = api.put("/api/config", json={
        "ambiente": "nacional",
        "servicos": cfg["servicos"],
        "nacional": {"p_tot_trib_sn": 6},
    })
    assert r.status_code == 200, r.text
    fake = SefinFake()
    monkeypatch.setattr("app.nfse.nacional.emissor.criar_cliente", lambda c, k, h: fake)
    api.sefin = fake
    return api


def _emitir(api, **extra):
    corpo = {
        "tomador": TOMADOR,
        "servico": "05762",
        "valor": 999.0,
        "descricao": "Servicos de treinamento. Pedido #1",
        "ref_externa": "wc-1",
    }
    corpo.update(extra)
    return api.post("/api/notas", json=corpo)


def _mcp(api, ferramenta, argumentos):
    chave = api.post("/api/chaves", json={"nome": "llm"}).json()["valor"]
    _iniciar(api, chave)
    r = _chamar_mcp(api, "tools/call", {"name": ferramenta, "arguments": argumentos}, chave)
    assert r.status_code == 200, r.text
    return _resultado(r)


class TestConfigNacional:
    def test_defaults_do_bloco_nacional(self, api_logada):
        cfg = api_logada.get("/api/config").json()
        assert cfg["ambiente"] == "municipal"
        assert cfg["nacional"]["serie_dps"] == "1"
        assert cfg["nacional"]["p_tot_trib_sn"] is None

    def test_mescla_bloco_nacional(self, api_nacional):
        api_nacional.put("/api/config", json={"nacional": {"informar_im": False}})
        nac = api_nacional.get("/api/config").json()["nacional"]
        assert nac["informar_im"] is False
        assert nac["p_tot_trib_sn"] == 6

    def test_im_nacional_salva(self, api_nacional):
        api_nacional.put("/api/config", json={"nacional": {"inscricao_municipal": "000000012345678"}})
        nac = api_nacional.get("/api/config").json()["nacional"]
        assert nac["inscricao_municipal"] == "000000012345678"

    def test_contador_nao_regride(self, api_nacional):
        api_nacional.put("/api/config", json={"nacional": {"proximo_numero_dps": 50}})
        api_nacional.put("/api/config", json={"nacional": {"proximo_numero_dps": 3}})
        assert api_nacional.get("/api/config").json()["nacional"]["proximo_numero_dps"] == 50

    @pytest.mark.parametrize("corpo", [
        {"ambiente": "estadual"},
        {"nacional": {"serie_dps": "50000"}},
        {"nacional": {"p_tot_trib_sn": 100}},
        {"nacional": {"c_loc_emi": "35503"}},
        {"nacional": {"informar_im": "sim"}},
        {"nacional": {"inscricao_municipal": "0000000123456789"}},
        {"nacional": {"inscricao_municipal": "123 456"}},
        {"servicos": {"05762": {"aliquota": 0.02, "c_trib_nac": "8021"}}},
        {"servicos": {"05762": {"aliquota": 0.02, "c_nbs": "12"}}},
        {"servicos": {"05762": {"aliquota": 0.02, "c_trib_mun": "12"}}},
        {"servicos": {"05762": {"aliquota": 0.02, "c_trib_mun": "000"}}},
        {"servicos": {"05762": {"aliquota": 0.02, "p_tot_trib_sn": 100}}},
        {"servicos": {"05762": {"aliquota": 0.02, "p_tot_trib_sn": "abc"}}},
    ])
    def test_valores_invalidos(self, api_logada, corpo):
        assert api_logada.put("/api/config", json=corpo).status_code == 422


class TestApiNacional:
    def test_emite_com_link_oficial(self, api_nacional):
        api_nacional.sefin.emitir_efeitos = [resposta_autorizada()]
        r = _emitir(api_nacional, competencia="2026-11-03")
        assert r.status_code == 200, r.text
        nota = r.json()["nota"]
        assert r.json()["teste"] is False
        assert nota["ambiente"] == "nacional"
        assert nota["chave_acesso"] == chave_teste()
        assert nota["competencia"] == "2026-11-03"
        assert nota["pdf_url"] == (
            f"https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave={chave_teste()}"
        )

        pdf = api_nacional.get(f"/api/notas/{nota['id']}/pdf", follow_redirects=False)
        assert pdf.status_code == 307
        assert pdf.headers["location"] == nota["pdf_url"]

        lista = api_nacional.get("/api/notas").json()["notas"]
        assert lista[0]["pdf_url"] == nota["pdf_url"]

    def test_recusa_identifica_o_emissor(self, api_nacional):
        api_nacional.sefin.emitir_efeitos = [
            SefinRecusouError([{"codigo": "E0310", "descricao": "Codigo inexistente"}], 400)
        ]
        r = _emitir(api_nacional)
        assert r.status_code == 400
        assert r.json()["detail"]["emissor"] == "Sistema Nacional"
        assert r.json()["detail"]["erros_prefeitura"][0]["codigo"] == "E0310"

    def test_config_incompleta_vira_422(self, api_nacional):
        api_nacional.put("/api/config", json={"nacional": {"p_tot_trib_sn": None}})
        r = _emitir(api_nacional)
        assert r.status_code == 422
        assert any("p_tot_trib_sn" in d for d in r.json()["detail"])

    def test_cancela_com_motivo(self, api_nacional):
        api_nacional.sefin.emitir_efeitos = [resposta_autorizada()]
        nota_id = _emitir(api_nacional).json()["nota"]["id"]
        r = api_nacional.delete(
            f"/api/notas/{nota_id}",
            params={"motivo_codigo": 2, "motivo": "Servico nao foi prestado ao aluno"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["nota"]["status"] == "cancelada"
        assert len(api_nacional.sefin.eventos) == 1

    def test_motivo_curto_vira_409(self, api_nacional):
        api_nacional.sefin.emitir_efeitos = [resposta_autorizada()]
        nota_id = _emitir(api_nacional).json()["nota"]["id"]
        r = api_nacional.delete(f"/api/notas/{nota_id}", params={"motivo": "curto"})
        assert r.status_code == 409

    def test_sync_indisponivel_no_nacional(self, api_nacional):
        r = api_nacional.post("/api/notas/sync", json={"inicio": "2026-11-01", "fim": "2026-11-14"})
        assert r.status_code == 409

    def test_modo_teste_emite_na_homologacao(self, api_nacional):
        api_nacional.put("/api/config", json={"modo_teste": True})
        api_nacional.sefin.emitir_efeitos = [resposta_autorizada()]
        r = _emitir(api_nacional)
        assert r.status_code == 200
        assert r.json()["teste"] is True
        nota = r.json()["nota"]
        assert nota["ambiente"] == "nacional_homologacao"
        assert "producaorestrita" in nota["pdf_url"]


class TestMcpNacional:
    def test_configuracao_mostra_o_ambiente(self, api_nacional):
        conteudo = _mcp(api_nacional, "consultar_configuracao", {})
        assert conteudo["ambiente"] == "nacional"
        assert conteudo["destino_da_emissao"] == "Sistema Nacional (nota real)"
        assert conteudo["nacional"]["p_tot_trib_sn"] == 6
        assert conteudo["servicos"][0]["codigo_tributacao_nacional"] == "080201"
        assert conteudo["servicos"][0]["percentual_tributos_sn"] == 6

    def test_configuracao_mostra_percentual_do_servico(self, api_nacional):
        cfg = api_nacional.get("/api/config").json()
        cfg["servicos"]["05762"]["p_tot_trib_sn"] = 11.2
        assert api_nacional.put("/api/config", json={"servicos": cfg["servicos"]}).status_code == 200
        servico = _mcp(api_nacional, "consultar_configuracao", {})["servicos"][0]
        assert servico["percentual_tributos_sn"] == 11.2

    def test_emitir_nota_nacional(self, api_nacional):
        api_nacional.sefin.emitir_efeitos = [resposta_autorizada()]
        conteudo = _mcp(api_nacional, "emitir_nota", {
            "cpf_cnpj": "52998224725", "razao_social": "Fulano de Tal",
            "valor": 999.0, "descricao": "Servicos de treinamento. Pedido #1",
            "servico": "05762", "ref_externa": "wc-1", "competencia": "2026-11-03",
        })
        assert conteudo["ok"] is True
        assert conteudo["teste"] is False
        assert conteudo["nota"]["chave_acesso"] == chave_teste()
        assert conteudo["nota"]["pdf_url"].startswith("https://www.nfse.gov.br/ConsultaPublica/")
        assert conteudo["alertas"][0]["codigo"] == "A001"

    def test_emitir_nota_recusada(self, api_nacional):
        api_nacional.sefin.emitir_efeitos = [
            SefinRecusouError([{"codigo": "E0160", "descricao": "Simples divergente"}], 400)
        ]
        conteudo = _mcp(api_nacional, "emitir_nota", {
            "cpf_cnpj": "52998224725", "razao_social": "Fulano", "valor": 10.0,
            "descricao": "Teste", "servico": "05762",
        })
        assert conteudo["ok"] is False
        assert conteudo["erro"] == "Sistema Nacional recusou a emissao"
        assert conteudo["erros_prefeitura"][0]["codigo"] == "E0160"

    def test_competencia_invalida(self, api_nacional):
        conteudo = _mcp(api_nacional, "emitir_nota", {
            "cpf_cnpj": "52998224725", "razao_social": "Fulano", "valor": 10.0,
            "descricao": "Teste", "servico": "05762", "competencia": "2999-01-01",
        })
        assert conteudo["ok"] is False
        assert "Dados invalidos" in conteudo["erro"]

    def test_emitir_em_modo_teste_avisa(self, api_nacional):
        api_nacional.put("/api/config", json={"modo_teste": True})
        api_nacional.sefin.emitir_efeitos = [resposta_autorizada()]
        conteudo = _mcp(api_nacional, "emitir_nota", {
            "cpf_cnpj": "52998224725", "razao_social": "Fulano", "valor": 10.0,
            "descricao": "Teste", "servico": "05762", "ref_externa": "teste-1",
        })
        assert conteudo["ok"] is True and conteudo["teste"] is True
        assert "producao restrita" in conteudo["mensagem"]
        assert conteudo["nota"]["ref_externa"] == "homologacao:teste-1"

    def test_cancelar_nota_nacional(self, api_nacional):
        api_nacional.sefin.emitir_efeitos = [resposta_autorizada()]
        nota_id = _emitir(api_nacional).json()["nota"]["id"]
        conteudo = _mcp(api_nacional, "cancelar_nota", {
            "nota_id": nota_id, "motivo_codigo": 1, "motivo": "Erro na emissao da nota",
        })
        assert conteudo["ok"] is True
        assert conteudo["nota"]["status"] == "cancelada"

    def test_cancelar_motivo_invalido(self, api_nacional):
        api_nacional.sefin.emitir_efeitos = [resposta_autorizada()]
        nota_id = _emitir(api_nacional).json()["nota"]["id"]
        conteudo = _mcp(api_nacional, "cancelar_nota", {"nota_id": nota_id, "motivo_codigo": 5})
        assert conteudo["ok"] is False
        assert "motivo_codigo" in conteudo["erro"]

    def test_sincronizar_indisponivel(self, api_nacional):
        conteudo = _mcp(api_nacional, "sincronizar_notas", {})
        assert conteudo["ok"] is False
        assert "municipal" in conteudo["erro"]

    def test_schemas_das_ferramentas(self, api_logada):
        chave = api_logada.post("/api/chaves", json={"nome": "llm"}).json()["valor"]
        _iniciar(api_logada, chave)
        ferramentas = {
            t["name"]: t for t in _corpo(_chamar_mcp(api_logada, "tools/list", chave=chave))["result"]["tools"]
        }
        assert "competencia" in ferramentas["emitir_nota"]["inputSchema"]["properties"]
        props = ferramentas["cancelar_nota"]["inputSchema"]["properties"]
        assert {"motivo_codigo", "motivo"} <= set(props)
        assert "nacional" in ferramentas["consultar_configuracao"]["description"]
