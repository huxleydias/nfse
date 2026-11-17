"""Orquestracao da emissao e do cancelamento no Sistema Nacional.

Mesmo contrato do emissor municipal (emitter.emitir / emitter.cancelar):
recebe EmissaoPayload, devolve {"nota", "teste", "idempotente"?} e levanta as
mesmas excecoes, para a API REST e o MCP nao precisarem saber o ambiente.

Protecao contra nota duplicada: a identificacao da DPS (municipio + CNPJ +
serie + numero) fica gravada na nota. Uma nova tentativa da mesma
ref_externa reaproveita essa identificacao e, antes de enviar, pergunta ao
Sistema Nacional se a DPS ja virou NFS-e. Se virou, a nota e recuperada em
vez de emitida de novo.
"""
import json

from app.models.config_store import alocar_numero_dps
from app.models.nota import Nota
from app.nfse.emitter import (
    EmissaoInvalidaError,
    EmissaoPayload,
    PrefeituraRecusouError,
    RefEmAndamentoError,
)
from app.nfse.soap_client import PrefeituraIndisponivelError
from app.nfse.utils import so_digitos
from app.nfse.xsd_validator import validar

from . import (
    AMBIENTE_HOMOLOGACAO,
    AMBIENTE_PRODUCAO,
    agora_brasilia,
    hoje_brasilia,
    leiaute_vigente,
    schema_dps,
    schema_evento,
)
from .assinatura import assinar
from .cliente import SefinClient, SefinRecusouError, normalizar_mensagens
from .dps import build_dps, montar_id_dps, serie_formatada, xml_bytes
from .evento import MOTIVO_PADRAO, MOTIVOS_CANCELAMENTO, build_pedido_cancelamento
from .retorno import ler_nfse, xml_evento, xml_nfse

PREFIXO_REF_HOMOLOGACAO = "homologacao:"
# DPS com a mesma identificacao ja convertida em NFS-e
ERRO_DPS_JA_CONVERTIDA = "E0014"


def criar_cliente(cert, private_key, homologacao: bool) -> SefinClient:
    """Ponto unico de criacao do cliente (os testes substituem aqui)."""
    return SefinClient(cert, private_key, homologacao=homologacao)


def ref_no_banco(ref_externa: str | None, homologacao: bool) -> str | None:
    """Nota de homologacao grava a ref com prefixo: a coluna e unica e o teste
    nao pode bloquear a mesma referencia em producao."""
    if not ref_externa:
        return None
    return f"{PREFIXO_REF_HOMOLOGACAO}{ref_externa}" if homologacao else ref_externa


def _validar_config(cfg: dict, payload: EmissaoPayload) -> dict:
    erros = []
    nac = cfg.get("nacional") or {}
    doc_prestador = so_digitos(cfg.get("prestador", {}).get("cnpj", ""))
    if len(doc_prestador) not in (11, 14):
        erros.append("CNPJ do prestador nao configurado")
    if str(nac.get("op_simp_nac")) != "3":
        erros.append(
            "Emissao nacional implementada para optante do Simples ME/EPP "
            "(nacional.op_simp_nac = 3)"
        )
    p_tot = nac.get("p_tot_trib_sn")
    try:
        p_tot = float(p_tot) if p_tot not in (None, "") else None
    except (TypeError, ValueError):
        p_tot = None
    if p_tot is None or not 0 <= p_tot < 100:
        erros.append(
            "Configure nacional.p_tot_trib_sn: percentual aproximado de "
            "tributos do Simples, de 0 a 99,99 (confirme com o contador)"
        )
    try:
        serie_formatada(nac.get("serie_dps", ""))
    except ValueError as e:
        erros.append(str(e))
    if len(so_digitos(nac.get("c_loc_emi", ""))) != 7:
        erros.append("nacional.c_loc_emi deve ter o codigo IBGE de 7 digitos")

    servico = cfg.get("servicos", {}).get(payload.servico)
    if not servico:
        erros.append(f"Servico {payload.servico} nao cadastrado na configuracao")
    else:
        if len(so_digitos(servico.get("c_trib_nac", ""))) != 6:
            erros.append(
                f"Servico {payload.servico} sem c_trib_nac (codigo de "
                "tributacao nacional de 6 digitos)"
            )
        nbs = so_digitos(servico.get("c_nbs") or "")
        if nbs and len(nbs) != 9:
            erros.append(f"Servico {payload.servico}: c_nbs deve ter 9 digitos")
    if erros:
        raise EmissaoInvalidaError(erros)
    return servico


def _dados_dps(cfg, payload, servico, serie, numero, competencia, homologacao, leiaute) -> dict:
    nac = cfg["nacional"]
    prestador = cfg["prestador"]
    tomador = {
        "cpf_cnpj": payload.tomador.cpf_cnpj,
        "razao_social": payload.tomador.razao_social or payload.tomador.cpf_cnpj,
        "email": payload.tomador.email,
        "endereco": payload.tomador.endereco.model_dump() if payload.tomador.endereco else None,
    }
    return {
        "tp_amb": 2 if homologacao else 1,
        "leiaute": leiaute,
        "dh_emi": agora_brasilia(),
        "serie": serie,
        "numero": numero,
        "competencia": competencia,
        "c_loc_emi": nac["c_loc_emi"],
        "prestador": {
            "cnpj": prestador["cnpj"],
            "im": prestador.get("inscricao_municipal") if nac.get("informar_im") else None,
        },
        "reg_trib": {
            "op_simp_nac": nac["op_simp_nac"],
            "reg_ap_trib_sn": nac.get("reg_ap_trib_sn", 1),
            "reg_esp_trib": nac.get("reg_esp_trib", 0),
        },
        "tomador": tomador,
        "servico": {
            "c_loc_prestacao": servico.get("c_loc_prestacao", nac["c_loc_emi"]),
            "c_trib_nac": servico["c_trib_nac"],
            "descricao": payload.descricao,
            "c_nbs": servico.get("c_nbs", ""),
        },
        "valor": payload.valor,
        "p_tot_trib_sn": float(nac["p_tot_trib_sn"]),
    }


def _autorizar(nota: Nota, corpo: dict, session) -> Nota:
    xml = xml_nfse(corpo)
    info = ler_nfse(xml)
    nota.status = "autorizada"
    nota.chave_acesso = info["chave_acesso"]
    nota.numero_nfse = info["numero_nfse"]
    nota.codigo_verificacao = None
    nota.xml_retorno = xml.decode("utf-8")
    nota.erros_json = None
    session.commit()
    return nota


def _recuperar(cliente: SefinClient, id_dps: str, nota: Nota, session) -> bool:
    """Se a DPS ja virou NFS-e, grava a nota como autorizada e devolve True."""
    chave = cliente.consultar_dps(id_dps)
    if not chave:
        return False
    _autorizar(nota, cliente.consultar_nfse(chave), session)
    return True


def emitir_nacional(payload: EmissaoPayload, session, cfg: dict, cert, private_key) -> dict:
    homologacao = bool(cfg.get("modo_teste", True))
    ambiente = AMBIENTE_HOMOLOGACAO if homologacao else AMBIENTE_PRODUCAO
    ref = ref_no_banco(payload.ref_externa, homologacao)

    nota = None
    if ref:
        existente = session.query(Nota).filter(Nota.ref_externa == ref).first()
        if existente is not None:
            if existente.status == "processando":
                raise RefEmAndamentoError(payload.ref_externa)
            if existente.status in ("autorizada", "cancelada"):
                return {"nota": existente, "idempotente": True, "teste": homologacao}
            if existente.ambiente == ambiente and existente.numero_dps:
                nota = existente
            else:
                # Erro de outro ambiente (ex.: tentativa no municipal): a
                # identificacao da DPS nao se aplica, comeca do zero.
                session.delete(existente)
                session.commit()

    servico = _validar_config(cfg, payload)
    competencia = payload.competencia or hoje_brasilia()
    cliente = criar_cliente(cert, private_key, homologacao)
    doc_prestador = cfg["prestador"]["cnpj"]

    if nota is not None:
        serie, numero = nota.serie_dps, nota.numero_dps
        id_dps = montar_id_dps(cfg["nacional"]["c_loc_emi"], doc_prestador, serie, numero)
        if _recuperar(cliente, id_dps, nota, session):
            return {"nota": nota, "idempotente": True, "teste": homologacao}
    else:
        serie = serie_formatada(cfg["nacional"]["serie_dps"])
        numero = alocar_numero_dps(session, homologacao)
        id_dps = montar_id_dps(cfg["nacional"]["c_loc_emi"], doc_prestador, serie, numero)

    leiaute = leiaute_vigente(homologacao, hoje_brasilia())
    root = build_dps(
        _dados_dps(cfg, payload, servico, serie, numero, competencia, homologacao, leiaute)
    )
    assinar(root, root[0], cert, private_key)
    validar(root, schema_dps(leiaute))
    dps = xml_bytes(root)

    if nota is None:
        nota = Nota(ref_externa=ref)
        session.add(nota)
    nota.ambiente = ambiente
    nota.serie_dps = serie
    nota.numero_dps = numero
    nota.numero_rps = None
    nota.serie_rps = None
    nota.competencia = competencia.isoformat()
    nota.tomador_nome = payload.tomador.razao_social
    nota.tomador_doc = payload.tomador.cpf_cnpj
    nota.valor = payload.valor
    nota.codigo_servico = payload.servico
    nota.status = "processando"
    nota.xml_enviado = dps.decode("utf-8")
    nota.erros_json = None
    session.commit()

    try:
        corpo = cliente.emitir(dps)
    except SefinRecusouError as e:
        if any(m["codigo"] == ERRO_DPS_JA_CONVERTIDA for m in e.erros):
            if _recuperar(cliente, id_dps, nota, session):
                return {"nota": nota, "idempotente": True, "teste": homologacao}
        nota.status = "erro"
        nota.erros_json = json.dumps(e.erros, ensure_ascii=False)
        session.commit()
        raise PrefeituraRecusouError(e.erros, nota, origem="nacional") from e
    except PrefeituraIndisponivelError:
        nota.status = "erro"
        nota.erros_json = json.dumps(
            [{"codigo": "rede", "descricao": "Falha de comunicacao com o Sistema Nacional"}]
        )
        session.commit()
        raise

    _autorizar(nota, corpo, session)
    alertas = normalizar_mensagens({"alertas": corpo.get("alertas") or []})
    return {"nota": nota, "teste": homologacao, "alertas": alertas}


def cancelar_nacional(nota: Nota, session, cfg: dict, cert, private_key,
                      motivo_codigo: int = 1, motivo: str | None = None) -> Nota:
    if not nota.chave_acesso:
        raise EmissaoInvalidaError("Nota sem chave de acesso, nao ha o que cancelar")
    if motivo_codigo not in MOTIVOS_CANCELAMENTO:
        raise EmissaoInvalidaError(
            "motivo_codigo deve ser 1 (erro na emissao), 2 (servico nao prestado) ou 9 (outros)"
        )
    texto = (motivo or MOTIVO_PADRAO).strip()
    if not 15 <= len(texto) <= 255:
        raise EmissaoInvalidaError("motivo deve ter de 15 a 255 caracteres")

    homologacao = nota.ambiente == AMBIENTE_HOMOLOGACAO
    root = build_pedido_cancelamento(
        2 if homologacao else 1, agora_brasilia(), cfg["prestador"]["cnpj"],
        nota.chave_acesso, motivo_codigo, texto,
    )
    assinar(root, root[0], cert, private_key)
    validar(root, schema_evento(leiaute_vigente(homologacao, hoje_brasilia())))

    cliente = criar_cliente(cert, private_key, homologacao)
    try:
        corpo = cliente.registrar_evento(nota.chave_acesso, xml_bytes(root))
    except SefinRecusouError as e:
        raise PrefeituraRecusouError(e.erros, nota, origem="nacional") from e

    nota.status = "cancelada"
    nota.xml_evento = xml_evento(corpo).decode("utf-8")
    session.commit()
    return nota
