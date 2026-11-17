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
from app.nfse.nacional import AMBIENTE_HOMOLOGACAO, url_consulta_publica
from app.nfse.nacional.emissor import percentual_sn
from app.nfse.parser import RespostaInvalidaError
from app.nfse.pdf import montar_url_pdf
from app.nfse.signer import CertificadoError
from app.nfse.soap_client import PrefeituraIndisponivelError, SoapClient
from app.nfse.xsd_validator import XSDValidationError

INSTRUCOES = (
    "Emite, consulta e cancela Notas Fiscais de Servico Eletronicas. O "
    "ambiente vem da configuracao: municipal (webservice da Prefeitura de Sao "
    "Paulo) ou nacional (Sistema Nacional NFS-e, obrigatorio para ME/EPP do "
    "Simples a partir de 01/11/2026). ATENCAO: emitir_nota gera documento "
    "fiscal real quando o modo teste esta desligado, e cancelar_nota e "
    "irreversivel. Confirme os dados com o usuario antes de chamar essas duas. "
    "Use consultar_configuracao para saber o ambiente e se o modo teste esta "
    "ativo."
)


def _cliente(session):
    cert, key = carregar_certificado(session)
    return SoapClient(cert, key), cert, key


def _erro(mensagem: str) -> dict:
    return {"ok": False, "erro": mensagem}


def _com_pdf(session, nota: Nota) -> dict:
    dados = nota.to_dict()
    if nota.chave_acesso:
        # Nacional: link da Consulta Publica, onde o DANFSe oficial e baixado
        dados["pdf_url"] = url_consulta_publica(
            nota.chave_acesso, homologacao=nota.ambiente == AMBIENTE_HOMOLOGACAO
        )
    elif nota.numero_nfse and nota.codigo_verificacao:
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

        from app.models.config_store import ambiente_config

        cfg = get_config(session)
        modo_teste = cfg.get("modo_teste", True)
        ambiente = ambiente_config(cfg)
        nacional = cfg.get("nacional", {})
        if ambiente == "nacional":
            onde = (
                "producao restrita do Sistema Nacional (sem valor fiscal)"
                if modo_teste else "Sistema Nacional (nota real)"
            )
        else:
            onde = (
                "validacao na Prefeitura, nenhuma nota gerada"
                if modo_teste else "Prefeitura de Sao Paulo (nota real)"
            )
        return {
            "ok": True,
            "ambiente": ambiente,
            "modo_teste": modo_teste,
            "emissao_gera_nota_real": not modo_teste,
            "destino_da_emissao": onde,
            "layout": cfg.get("layout", 1),
            "prestador": cfg.get("prestador", {}),
            "serie_rps": cfg.get("serie_rps"),
            "proximo_numero_rps": cfg.get("proximo_numero_rps"),
            "nacional": {
                "serie_dps": nacional.get("serie_dps"),
                "proximo_numero_dps": nacional.get("proximo_numero_dps"),
                "proximo_numero_dps_homologacao": nacional.get("proximo_numero_dps_homologacao"),
                "op_simp_nac": nacional.get("op_simp_nac"),
                "reg_ap_trib_sn": nacional.get("reg_ap_trib_sn"),
                "p_tot_trib_sn": nacional.get("p_tot_trib_sn"),
                "informar_im": nacional.get("informar_im"),
                "inscricao_municipal": nacional.get("inscricao_municipal") or None,
            },
            "servicos": [
                {
                    "codigo": codigo,
                    "descricao": servico.get("descricao_padrao", ""),
                    "aliquota_iss": servico.get("aliquota"),
                    "codigo_tributacao_nacional": servico.get("c_trib_nac"),
                    "codigo_tributacao_municipal": servico.get("c_trib_mun") or None,
                    "nbs": servico.get("c_nbs") or None,
                    # Percentual que vai no pTotTribSN: o do servico ou o geral
                    "percentual_tributos_sn": percentual_sn(cfg, servico),
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
    competencia: str | None = None,
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
                competencia=competencia or None,
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
                "erro": f"{e.emissor} recusou a emissao",
                "erros_prefeitura": e.erros,
            }
        except XSDValidationError as e:
            return {"ok": False, "erro": "XML fora do schema oficial", "erros_xsd": e.erros}
        except (PrefeituraIndisponivelError, RespostaInvalidaError) as e:
            return _erro(str(e))

        if resultado.get("teste") and "nota" not in resultado:
            return {
                "ok": True,
                "teste": True,
                "mensagem": "Modo teste ativo: pedido validado, nenhuma nota emitida",
                "resultado": resultado["resultado"],
            }

        resposta = {
            "ok": True,
            "teste": bool(resultado.get("teste")),
            "idempotente": resultado.get("idempotente", False),
            "nota": _com_pdf(session, resultado["nota"]),
        }
        if resultado.get("teste"):
            resposta["mensagem"] = (
                "Modo teste ativo: nota emitida na producao restrita do Sistema "
                "Nacional, sem valor fiscal"
            )
        if resultado.get("alertas"):
            resposta["alertas"] = resultado["alertas"]
        return resposta
    finally:
        session.close()


def cancelar_nota(nota_id: int, motivo_codigo: int = 1, motivo: str | None = None) -> dict:
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
            nota = cancelar(nota, session, client, cert, key, motivo_codigo, motivo)
        except CertificadoError as e:
            return _erro(str(e))
        except EmissaoInvalidaError as e:
            return _erro("; ".join(e.detalhes))
        except PrefeituraRecusouError as e:
            return {
                "ok": False,
                "erro": f"{e.emissor} recusou o cancelamento",
                "erros_prefeitura": e.erros,
            }
        except XSDValidationError as e:
            return {"ok": False, "erro": "XML fora do schema oficial", "erros_xsd": e.erros}
        except (PrefeituraIndisponivelError, RespostaInvalidaError) as e:
            return _erro(str(e))
        return {"ok": True, "nota": _com_pdf(session, nota)}
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
        except EmissaoInvalidaError as e:
            return _erro("; ".join(e.detalhes))
        except PrefeituraIndisponivelError as e:
            return _erro(str(e))
        return {"ok": True, **resultado}
    finally:
        session.close()


FERRAMENTAS = [
    (
        consultar_configuracao,
        "Consultar configuracao",
        "Mostra como o emissor esta configurado: ambiente (municipal ou "
        "nacional), prestador, leiaute do XML, se o modo teste esta ativo e "
        "quais codigos de servico existem. Chame antes de emitir para saber "
        "onde a nota sai e se a emissao sera real ou de teste.",
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
        "Detalha uma nota pelo id interno, incluindo o link do PDF oficial "
        "quando a nota esta autorizada (portal da prefeitura no municipal, "
        "Consulta Publica no nacional).",
    ),
    (
        emitir_nota,
        "Emitir nota",
        "Emite uma NFS-e no ambiente configurado. Com o modo teste ativo: no "
        "municipal o pedido so e validado na prefeitura; no nacional a nota sai "
        "na producao restrita, sem valor fiscal. Com o modo teste desligado isso "
        "cria um DOCUMENTO FISCAL REAL: confirme valor, tomador e descricao com "
        "o usuario antes de chamar. Tomador pessoa juridica precisa de endereco "
        "no municipal. competencia (AAAA-MM-DD, opcional, padrao hoje) e a data "
        "do servico no nacional. Use ref_externa (ex.: numero do pedido) para "
        "evitar nota duplicada em caso de repeticao.",
    ),
    (
        cancelar_nota,
        "Cancelar nota",
        "Cancela uma nota autorizada no ambiente em que ela saiu. No nacional "
        "aceita motivo_codigo (1 erro na emissao, 2 servico nao prestado, 9 "
        "outros) e motivo (15 a 255 caracteres). Acao irreversivel: confirme "
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
        title="NFS-e (Sao Paulo e Sistema Nacional)",
        instructions=INSTRUCOES,
        version="1.1.0",
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
