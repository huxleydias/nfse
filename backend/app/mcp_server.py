"""Servidor MCP: expoe a emissao de NFS-e para LLMs.

Transporte Streamable HTTP em `/mcp`, autenticado com as mesmas chaves de
API da tela de Chaves (header `Authorization: Bearer nfse_...`). O servidor
roda stateless: cada chamada abre a propria sessao de banco, sem estado
compartilhado entre requisicoes.

As ferramentas chamam o mesmo nucleo da API REST, entao toda regra fiscal
(leiaute, modo teste, validacao XSD, idempotencia) vale igual aqui.

O servidor MCP e criado por fabrica, nao no import: o session manager do SDK
so pode rodar uma vez por instancia, e cada startup da aplicacao (inclusive
nos testes) precisa de uma instancia limpa.
"""
import os
from contextlib import asynccontextmanager
from datetime import date, timedelta

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.db import get_session
from app.core.security import (
    api_key_valida,
    extrair_bearer,
    token_do_ambiente_valido,
)
from app.models.nota import Nota
from app.nfse.cert_store import carregar_certificado
from app.nfse.emitter import (
    EmissaoInvalidaError,
    EmissaoPayload,
    PrefeituraRecusouError,
    RefEmAndamentoError,
    cancelar,
    emitir,
    sincronizar,
)
from app.nfse.pdf import montar_url_pdf
from app.nfse.signer import CertificadoError
from app.nfse.soap_client import PrefeituraIndisponivelError, SoapClient

INSTRUCOES = (
    "Emite, consulta e cancela Notas Fiscais de Servico Eletronicas na "
    "Prefeitura de Sao Paulo. ATENCAO: emitir_nota gera documento fiscal real "
    "quando o modo teste esta desligado, e cancelar_nota e irreversivel. "
    "Confirme os dados com o usuario antes de chamar essas duas. Use "
    "consultar_configuracao para saber se o modo teste esta ativo."
)


def _cliente(session):
    cert, key = carregar_certificado(session)
    return SoapClient(cert, key), cert, key


def _erro(mensagem: str) -> dict:
    return {"ok": False, "erro": mensagem}


def _com_pdf(session, nota: Nota) -> dict:
    dados = nota.to_dict()
    if nota.numero_nfse and nota.codigo_verificacao:
        from app.models.config_store import get_config

        inscricao = get_config(session)["prestador"]["inscricao_municipal"]
        dados["pdf_url"] = montar_url_pdf(
            inscricao, nota.numero_nfse, nota.codigo_verificacao
        )
    return dados


def consultar_configuracao() -> dict:
    session = get_session()
    try:
        from app.models.config_store import get_config

        cfg = get_config(session)
        return {
            "ok": True,
            "modo_teste": cfg.get("modo_teste", True),
            "emissao_gera_nota_real": not cfg.get("modo_teste", True),
            "layout": cfg.get("layout", 1),
            "prestador": cfg.get("prestador", {}),
            "serie_rps": cfg.get("serie_rps"),
            "proximo_numero_rps": cfg.get("proximo_numero_rps"),
            "servicos": [
                {
                    "codigo": codigo,
                    "descricao": servico.get("descricao_padrao", ""),
                    "aliquota_iss": servico.get("aliquota"),
                }
                for codigo, servico in cfg.get("servicos", {}).items()
            ],
        }
    finally:
        session.close()


def listar_notas(
    status: str | None = None,
    inicio: str | None = None,
    fim: str | None = None,
    limite: int = 20,
) -> dict:
    session = get_session()
    try:
        consulta = session.query(Nota).order_by(Nota.id.desc())
        if status:
            consulta = consulta.filter(Nota.status == status)
        if inicio:
            consulta = consulta.filter(Nota.criada_em >= inicio)
        if fim:
            consulta = consulta.filter(Nota.criada_em <= f"{fim}T23:59:59")
        notas = consulta.limit(max(1, min(limite, 100))).all()
        return {"ok": True, "total": len(notas), "notas": [n.to_dict() for n in notas]}
    finally:
        session.close()


def consultar_nota(nota_id: int) -> dict:
    session = get_session()
    try:
        nota = session.get(Nota, nota_id)
        if nota is None:
            return _erro(f"Nota {nota_id} nao encontrada")
        return {"ok": True, "nota": _com_pdf(session, nota)}
    finally:
        session.close()


def emitir_nota(
    cpf_cnpj: str,
    razao_social: str,
    valor: float,
    descricao: str,
    servico: str,
    email: str = "",
    ref_externa: str | None = None,
    endereco: dict | None = None,
) -> dict:
    session = get_session()
    try:
        try:
            payload = EmissaoPayload(
                tomador={
                    "cpf_cnpj": cpf_cnpj,
                    "razao_social": razao_social,
                    "email": email,
                    **({"endereco": endereco} if endereco else {}),
                },
                servico=servico,
                valor=valor,
                descricao=descricao,
                ref_externa=ref_externa,
            )
        except Exception as e:
            return _erro(f"Dados invalidos: {e}")

        try:
            client, cert, key = _cliente(session)
        except CertificadoError as e:
            return _erro(str(e))

        try:
            resultado = emitir(payload, session, client, cert, key)
        except RefEmAndamentoError:
            return _erro("Ja existe emissao em andamento com essa ref_externa")
        except EmissaoInvalidaError as e:
            return _erro("; ".join(e.detalhes))
        except PrefeituraRecusouError as e:
            return {
                "ok": False,
                "erro": "Prefeitura recusou a emissao",
                "erros_prefeitura": e.erros,
            }
        except PrefeituraIndisponivelError as e:
            return _erro(str(e))

        if resultado.get("teste"):
            return {
                "ok": True,
                "teste": True,
                "mensagem": "Modo teste ativo: pedido validado, nenhuma nota emitida",
                "resultado": resultado["resultado"],
            }

        return {
            "ok": True,
            "teste": False,
            "idempotente": resultado.get("idempotente", False),
            "nota": _com_pdf(session, resultado["nota"]),
        }
    finally:
        session.close()


def cancelar_nota(nota_id: int) -> dict:
    session = get_session()
    try:
        nota = session.get(Nota, nota_id)
        if nota is None:
            return _erro(f"Nota {nota_id} nao encontrada")
        if nota.status == "cancelada":
            return {
                "ok": True,
                "mensagem": "Nota ja estava cancelada",
                "nota": nota.to_dict(),
            }
        if nota.status != "autorizada":
            return _erro(f"Nota com status {nota.status} nao pode ser cancelada")

        try:
            client, cert, key = _cliente(session)
            nota = cancelar(nota, session, client, cert, key)
        except CertificadoError as e:
            return _erro(str(e))
        except PrefeituraRecusouError as e:
            return {
                "ok": False,
                "erro": "Prefeitura recusou o cancelamento",
                "erros_prefeitura": e.erros,
            }
        except PrefeituraIndisponivelError as e:
            return _erro(str(e))
        return {"ok": True, "nota": nota.to_dict()}
    finally:
        session.close()


def sincronizar_notas(inicio: str | None = None, fim: str | None = None) -> dict:
    session = get_session()
    try:
        hoje = date.today()
        try:
            dt_fim = date.fromisoformat(fim) if fim else hoje
            dt_inicio = (
                date.fromisoformat(inicio) if inicio else hoje - timedelta(days=90)
            )
        except ValueError:
            return _erro("Datas devem estar no formato AAAA-MM-DD")

        try:
            client, cert, key = _cliente(session)
            resultado = sincronizar(dt_inicio, dt_fim, session, client, cert, key)
        except CertificadoError as e:
            return _erro(str(e))
        except PrefeituraIndisponivelError as e:
            return _erro(str(e))
        return {"ok": True, **resultado}
    finally:
        session.close()


FERRAMENTAS = [
    (
        consultar_configuracao,
        "Consultar configuracao",
        "Mostra como o emissor esta configurado: prestador, leiaute do XML, se o "
        "modo teste esta ativo e quais codigos de servico existem. Chame antes de "
        "emitir para saber se a emissao sera real ou simulada.",
    ),
    (
        listar_notas,
        "Listar notas",
        "Lista as notas gravadas no sistema, da mais recente para a mais antiga. "
        "Filtros opcionais por status (autorizada, cancelada, erro) e por periodo "
        "de criacao no formato AAAA-MM-DD.",
    ),
    (
        consultar_nota,
        "Consultar nota",
        "Detalha uma nota pelo id interno, incluindo o link do PDF oficial da "
        "prefeitura quando a nota esta autorizada.",
    ),
    (
        emitir_nota,
        "Emitir nota",
        "Emite uma NFS-e. Com o modo teste ativo o pedido e apenas validado na "
        "prefeitura e nenhuma nota e gerada. Com o modo teste desligado isso cria "
        "um DOCUMENTO FISCAL REAL: confirme valor, tomador e descricao com o "
        "usuario antes de chamar. Tomador pessoa juridica precisa de endereco. "
        "Use ref_externa (ex.: numero do pedido) para evitar nota duplicada em "
        "caso de repeticao.",
    ),
    (
        cancelar_nota,
        "Cancelar nota",
        "Cancela na prefeitura uma nota autorizada. Acao irreversivel: confirme "
        "com o usuario antes de chamar.",
    ),
    (
        sincronizar_notas,
        "Sincronizar com a prefeitura",
        "Busca na prefeitura as notas emitidas num periodo e atualiza o banco "
        "local. Util para trazer notas emitidas fora deste sistema. Datas no "
        "formato AAAA-MM-DD; sem datas usa os ultimos 90 dias.",
    ),
]


def criar_servidor() -> MCPServer:
    servidor = MCPServer(
        name="nfse-sao-paulo",
        title="NFS-e Sao Paulo",
        instructions=INSTRUCOES,
        version="1.0.0",
    )
    for funcao, titulo, descricao in FERRAMENTAS:
        servidor.tool(title=titulo, description=descricao)(funcao)
    return servidor


class MontagemMCP:
    """Delegador do app MCP, com autenticacao por chave de API.

    O app real so existe depois do startup (o session manager precisa de um
    task group vivo). Enquanto nao existe, responde 503 em vez de estourar.
    """

    def __init__(self):
        self._app: ASGIApp | None = None

    def definir(self, app: ASGIApp | None) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            if self._app is not None:
                await self._app(scope, receive, send)
            return

        if self._app is None:
            await self._resposta(
                scope, receive, send, 503, -32000, "Servidor MCP ainda iniciando"
            )
            return

        cabecalhos = {
            chave.decode().lower(): valor.decode()
            for chave, valor in scope.get("headers", [])
        }
        recebido = extrair_bearer(cabecalhos.get("authorization"))
        autorizado = bool(recebido) and (
            token_do_ambiente_valido(recebido) or api_key_valida(recebido)
        )
        if not autorizado:
            await self._resposta(
                scope,
                receive,
                send,
                401,
                -32001,
                "Nao autenticado. Envie o header Authorization: Bearer <chave>, "
                "criada na tela Chaves de API.",
            )
            return

        await self._app(scope, receive, send)

    @staticmethod
    async def _resposta(scope, receive, send, status, codigo, mensagem):
        cabecalhos = {"WWW-Authenticate": "Bearer"} if status == 401 else None
        resposta = JSONResponse(
            {
                "jsonrpc": "2.0",
                "error": {"code": codigo, "message": mensagem},
                "id": None,
            },
            status_code=status,
            headers=cabecalhos,
        )
        await resposta(scope, receive, send)


montagem_mcp = MontagemMCP()


def _seguranca_de_transporte() -> TransportSecuritySettings:
    """Protecao contra DNS rebinding do SDK.

    Ela valida o header Host contra uma allowlist, e a lista vazia do default
    recusa tudo que nao seja localhost: em producao atras de um dominio
    proprio, isso derruba toda chamada MCP. Informe os dominios em
    MCP_ALLOWED_HOSTS (separados por virgula). Sem a variavel a protecao fica
    desligada e a autenticacao por chave de API segue sendo a barreira, que e
    o que realmente protege este servidor: nao ha cookie de sessao envolvido,
    entao nao existe o ataque de rebinding que ela previne.
    """
    hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if hosts:
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts,
            allowed_origins=[f"https://{h}" for h in hosts],
        )
    return TransportSecuritySettings(enable_dns_rebinding_protection=False)


@asynccontextmanager
async def ciclo_de_vida_mcp():
    """Sobe um servidor MCP limpo e o publica no delegador enquanto a
    aplicacao estiver de pe."""
    servidor = criar_servidor()
    app = servidor.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=_seguranca_de_transporte(),
    )
    async with servidor.session_manager.run():
        montagem_mcp.definir(app)
        try:
            yield
        finally:
            montagem_mcp.definir(None)
