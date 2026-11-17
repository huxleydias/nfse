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
from app.models.config_edicao import ConfigInvalida, aplicar, numero
from app.models.config_store import CONFIG_DEFAULT, SERVICO_PADRAO
from app.nfse.nacional.emissor import percentual_sn
from app.nfse.utils import so_digitos
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
    "ativo, e atualizar_configuracao para mudar qualquer campo, menos o modo "
    "teste e o certificado."
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


def _visao_config(cfg: dict) -> dict:
    """Config em valores simples: porcentagens em porcentagem, nomes claros.
    E o mesmo formato que atualizar_configuracao aceita."""
    from app.models.config_store import ambiente_config

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
    servicos = []
    for codigo, servico in cfg.get("servicos", {}).items():
        aliquota = servico.get("aliquota")
        servicos.append({
            "codigo": codigo,
            "descricao": servico.get("descricao_padrao", ""),
            "aliquota_iss_percentual": (
                round(float(aliquota) * 100, 4) if aliquota not in (None, "") else None
            ),
            "iss_retido": bool(servico.get("iss_retido", False)),
            "local_prestacao": servico.get("c_loc_prestacao") or None,
            "codigo_tributacao_nacional": servico.get("c_trib_nac") or None,
            "codigo_tributacao_municipal": servico.get("c_trib_mun") or None,
            "nbs": servico.get("c_nbs") or None,
            # Percentual proprio do servico (None usa o geral) e o que vai de
            # fato no pTotTribSN
            "percentual_tributos_sn_servico": servico.get("p_tot_trib_sn"),
            "percentual_tributos_sn": percentual_sn(cfg, servico),
            "layout2": {campo: servico.get(campo) for campo in CAMPOS_LAYOUT2},
        })
    return {
        "ambiente": ambiente,
        "modo_teste": modo_teste,
        "emissao_gera_nota_real": not modo_teste,
        "destino_da_emissao": onde,
        "layout": cfg.get("layout", 1),
        "tributacao": cfg.get("tributacao"),
        "prestador": cfg.get("prestador", {}),
        "serie_rps": cfg.get("serie_rps"),
        "proximo_numero_rps": cfg.get("proximo_numero_rps"),
        "nacional": {
            campo: (nacional.get(campo) if campo != "inscricao_municipal"
                    else nacional.get(campo) or None)
            for campo in CAMPOS_NACIONAL
        },
        "servicos": servicos,
    }


def consultar_configuracao() -> dict:
    session = get_session()
    try:
        from app.models.config_store import get_config

        return {"ok": True, **_visao_config(get_config(session))}
    finally:
        session.close()


# Campos editaveis pelo MCP. modo_teste e certificado ficam de fora de proposito:
# ligar a emissao real e decisao de quem esta na tela.
CAMPOS_NACIONAL = tuple(CONFIG_DEFAULT["nacional"])
CAMPOS_PRESTADOR = tuple(CONFIG_DEFAULT["prestador"])
CAMPOS_LAYOUT2 = ("nbs", "c_class_trib", "c_ind_op", "fin_nfse", "ind_final", "ind_dest")
CAMPOS_SERVICO = {
    "descricao": "descricao_padrao",
    "aliquota_iss_percentual": "aliquota",
    "iss_retido": "iss_retido",
    "local_prestacao": "c_loc_prestacao",
    "codigo_tributacao_nacional": "c_trib_nac",
    "codigo_tributacao_municipal": "c_trib_mun",
    "nbs": "c_nbs",
    "percentual_tributos_sn_servico": "p_tot_trib_sn",
}


def _servico_canonico(cfg: dict, item: dict) -> tuple[str, dict]:
    if not isinstance(item, dict) or not item.get("codigo"):
        raise ConfigInvalida(["Cada servico precisa de codigo (codigo municipal, ex.: 05762)"])
    codigo = so_digitos(str(item["codigo"])) or str(item["codigo"])
    atual = cfg.get("servicos", {}).get(codigo)
    servico = dict(atual) if atual else {
        **SERVICO_PADRAO, "c_loc_prestacao": cfg.get("nacional", {}).get("c_loc_emi", ""),
    }
    erros = []
    for campo, valor in item.items():
        if campo == "codigo":
            continue
        if campo == "layout2":
            if not isinstance(valor, dict) or set(valor) - set(CAMPOS_LAYOUT2):
                erros.append(
                    f"Servico {codigo}: layout2 aceita {', '.join(CAMPOS_LAYOUT2)}"
                )
            else:
                servico.update(valor)
            continue
        if campo not in CAMPOS_SERVICO:
            erros.append(
                f"Servico {codigo}: campo {campo} desconhecido. Campos aceitos: "
                f"{', '.join(['codigo', *CAMPOS_SERVICO, 'layout2'])}"
            )
            continue
        if campo == "aliquota_iss_percentual":
            percentual = numero(valor)
            if isinstance(percentual, bool) or not isinstance(percentual, (int, float)):
                erros.append(f"Servico {codigo}: aliquota_iss_percentual deve ser numero (ex.: 2)")
                continue
            if 0 < percentual < 1:
                erros.append(
                    f"Servico {codigo}: aliquota_iss_percentual vai em porcentagem: "
                    "2 para 2%, 2,9 para 2,9%"
                )
                continue
            valor = round(percentual / 100, 6)
        servico[CAMPOS_SERVICO[campo]] = valor
    if erros:
        raise ConfigInvalida(erros)
    return codigo, servico


def atualizar_configuracao(
    ambiente: str | None = None,
    layout: int | None = None,
    tributacao: str | None = None,
    serie_rps: str | None = None,
    proximo_numero_rps: int | None = None,
    prestador: dict | None = None,
    nacional: dict | None = None,
    servicos: list[dict] | None = None,
    remover_servicos: list[str] | None = None,
) -> dict:
    session = get_session()
    try:
        from app.models.config_store import get_config

        cfg = get_config(session)
        novos: dict = {}
        erros: list[str] = []
        for chave, valor in (
            ("ambiente", ambiente), ("layout", layout), ("tributacao", tributacao),
            ("serie_rps", serie_rps), ("proximo_numero_rps", proximo_numero_rps),
        ):
            if valor is not None:
                novos[chave] = valor
        if prestador is not None:
            extras = set(prestador) - set(CAMPOS_PRESTADOR)
            if extras:
                erros.append(
                    f"prestador aceita {', '.join(CAMPOS_PRESTADOR)} "
                    f"(recebeu {', '.join(sorted(extras))})"
                )
            novos["prestador"] = prestador
        if nacional is not None:
            if "modo_teste" in nacional:
                erros.append("modo_teste nao muda pelo MCP: ligue ou desligue na tela Configuracao")
            extras = set(nacional) - set(CAMPOS_NACIONAL) - {"modo_teste"}
            if extras:
                erros.append(
                    f"nacional aceita {', '.join(CAMPOS_NACIONAL)} "
                    f"(recebeu {', '.join(sorted(extras))})"
                )
            novos["nacional"] = {k: v for k, v in nacional.items() if k != "modo_teste"}
        if servicos is not None or remover_servicos:
            todos = dict(cfg.get("servicos", {}))
            for item in servicos or []:
                try:
                    codigo, servico = _servico_canonico(cfg, item)
                except ConfigInvalida as e:
                    erros.extend(e.erros)
                    continue
                todos[codigo] = servico
            for codigo in remover_servicos or []:
                codigo = so_digitos(str(codigo)) or str(codigo)
                if codigo not in todos:
                    erros.append(f"Servico {codigo} nao existe para remover")
                todos.pop(codigo, None)
            novos["servicos"] = todos
        if erros:
            return _erro("; ".join(erros))
        if not novos:
            return _erro("Nada para atualizar")
        try:
            aplicar(session, novos)
        except ConfigInvalida as e:
            return _erro("; ".join(e.erros))
        return {"ok": True, "configuracao": _visao_config(get_config(session))}
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
        "nacional), prestador, leiaute do XML, se o modo teste esta ativo, o "
        "bloco nacional e cada servico com todos os campos (porcentagens em "
        "porcentagem). Chame antes de emitir para saber onde a nota sai e se a "
        "emissao sera real ou de teste. O formato e o mesmo que "
        "atualizar_configuracao aceita.",
    ),
    (
        atualizar_configuracao,
        "Atualizar configuracao",
        "Altera a configuracao do emissor, menos o modo teste e o certificado "
        "(esses so pela tela). Atualizacao parcial: mande so o que muda. "
        "Porcentagens vao em porcentagem (aliquota_iss_percentual 2 = 2%; "
        "percentual do Simples 11,2 = 11,2%) e codigos podem ir como aparecem no "
        "DANFSe (08.02.01, 1.2205.19.00). servicos e uma lista de objetos com "
        "codigo (municipal) e os campos que mudam: descricao, "
        "aliquota_iss_percentual, iss_retido, local_prestacao, "
        "codigo_tributacao_nacional, codigo_tributacao_municipal, nbs, "
        "percentual_tributos_sn_servico (null usa o geral) e layout2 (nbs, "
        "c_class_trib, c_ind_op, fin_nfse, ind_final, ind_dest). Codigo novo cria "
        "o servico; remover_servicos apaga. nacional aceita os mesmos campos que "
        "consultar_configuracao mostra (p_tot_trib_sn e o percentual geral do "
        "Simples). Devolve a configuracao como ficou. Mudar dado fiscal afeta as "
        "proximas notas: confirme com o usuario antes.",
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
        version="1.2.0",
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
