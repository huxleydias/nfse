"""Testes do servidor MCP: autenticacao na borda e as ferramentas."""
import json


def _chamar_mcp(client, metodo, params=None, chave=None):
    cabecalhos = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if chave:
        cabecalhos["Authorization"] = f"Bearer {chave}"
    return client.post(
        "/mcp/",
        headers=cabecalhos,
        json={"jsonrpc": "2.0", "id": 1, "method": metodo, "params": params or {}},
    )


def _iniciar(client, chave):
    return _chamar_mcp(
        client,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "teste", "version": "1"},
        },
        chave,
    )


def _resultado(resposta):
    """Extrai o dict devolvido pela ferramenta.

    O SDK entrega o retorno como texto JSON em content[0].text, que e o
    formato que todo cliente MCP entende.
    """
    corpo = _corpo(resposta)
    assert "result" in corpo, corpo
    return json.loads(corpo["result"]["content"][0]["text"])


def _corpo(resposta):
    """A resposta pode vir como JSON puro ou como evento SSE."""
    texto = resposta.text
    if texto.startswith("event:") or texto.startswith("data:"):
        for linha in texto.splitlines():
            if linha.startswith("data:"):
                return json.loads(linha.removeprefix("data:").strip())
        raise AssertionError(f"SSE sem data: {texto[:200]}")
    return resposta.json()


class TestAutenticacaoMCP:
    def test_sem_chave_devolve_401(self, api):
        r = _chamar_mcp(api, "initialize")
        assert r.status_code == 401
        assert "Bearer" in r.headers.get("www-authenticate", "")

    def test_chave_invalida_devolve_401(self, api):
        r = _chamar_mcp(api, "initialize", chave="nfse_invalida")
        assert r.status_code == 401

    def test_erro_401_e_json_rpc(self, api):
        corpo = _chamar_mcp(api, "initialize").json()
        assert corpo["jsonrpc"] == "2.0"
        assert corpo["error"]["code"] == -32001
        assert "Chaves de API" in corpo["error"]["message"]

    def test_chave_revogada_devolve_401(self, api_logada):
        criada = api_logada.post("/api/chaves", json={"nome": "llm"}).json()
        api_logada.delete(f"/api/chaves/{criada['chave']['id']}")
        r = _iniciar(api_logada, criada["valor"])
        assert r.status_code == 401

    def test_chave_valida_inicializa(self, api_logada):
        chave = api_logada.post("/api/chaves", json={"nome": "llm"}).json()["valor"]
        r = _iniciar(api_logada, chave)
        assert r.status_code == 200, r.text
        corpo = _corpo(r)
        assert corpo["result"]["serverInfo"]["name"] == "nfse-sao-paulo"

    def test_token_do_ambiente_tambem_serve(self, api):
        r = _iniciar(api, "token-api-de-teste-com-32-chars-ok")
        assert r.status_code == 200


class TestFerramentasMCP:
    def test_lista_as_ferramentas(self, api_logada):
        chave = api_logada.post("/api/chaves", json={"nome": "llm"}).json()["valor"]
        _iniciar(api_logada, chave)
        r = _chamar_mcp(api_logada, "tools/list", chave=chave)
        assert r.status_code == 200, r.text
        nomes = {t["name"] for t in _corpo(r)["result"]["tools"]}
        assert nomes == {
            "consultar_configuracao",
            "atualizar_configuracao",
            "listar_notas",
            "consultar_nota",
            "emitir_nota",
            "cancelar_nota",
            "sincronizar_notas",
        }

    def test_emitir_avisa_que_gera_documento_real(self, api_logada):
        chave = api_logada.post("/api/chaves", json={"nome": "llm"}).json()["valor"]
        _iniciar(api_logada, chave)
        r = _chamar_mcp(api_logada, "tools/list", chave=chave)
        emitir = next(
            t for t in _corpo(r)["result"]["tools"] if t["name"] == "emitir_nota"
        )
        assert "DOCUMENTO FISCAL REAL" in emitir["description"]

    def test_consultar_configuracao_roda(self, api_configurada):
        chave = api_configurada.post("/api/chaves", json={"nome": "llm"}).json()["valor"]
        _iniciar(api_configurada, chave)
        r = _chamar_mcp(
            api_configurada,
            "tools/call",
            {"name": "consultar_configuracao", "arguments": {}},
            chave,
        )
        assert r.status_code == 200, r.text
        conteudo = _resultado(r)
        assert conteudo["ok"] is True
        assert conteudo["layout"] in (1, 2)
        assert "emissao_gera_nota_real" in conteudo

    def test_listar_notas_roda(self, api_configurada):
        api_configurada.post("/api/notas", json={
            "tomador": {"cpf_cnpj": "111.444.777-35", "razao_social": "Fulano"},
            "servico": "05762",
            "valor": 599.0,
            "descricao": "Servico de exemplo",
        })
        chave = api_configurada.post("/api/chaves", json={"nome": "llm"}).json()["valor"]
        _iniciar(api_configurada, chave)
        r = _chamar_mcp(
            api_configurada,
            "tools/call",
            {"name": "listar_notas", "arguments": {}},
            chave,
        )
        conteudo = _resultado(r)
        assert conteudo["ok"] is True
        assert conteudo["total"] == 1

    def test_consultar_nota_inexistente_devolve_erro_tratado(self, api_configurada):
        chave = api_configurada.post("/api/chaves", json={"nome": "llm"}).json()["valor"]
        _iniciar(api_configurada, chave)
        r = _chamar_mcp(
            api_configurada,
            "tools/call",
            {"name": "consultar_nota", "arguments": {"nota_id": 9999}},
            chave,
        )
        conteudo = _resultado(r)
        assert conteudo["ok"] is False
        assert "nao encontrada" in conteudo["erro"]


class TestFabricaServidor:
    def test_cada_servidor_e_uma_instancia_nova(self):
        from app.mcp_server import criar_servidor

        # O session manager do SDK so roda uma vez por instancia; a fabrica
        # existe para cada startup receber uma limpa.
        assert criar_servidor() is not criar_servidor()

    def test_todas_as_ferramentas_tem_titulo_e_descricao(self):
        from app.mcp_server import FERRAMENTAS

        for funcao, titulo, descricao in FERRAMENTAS:
            assert callable(funcao)
            assert titulo and len(descricao) > 40
