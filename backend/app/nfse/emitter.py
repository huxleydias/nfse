"""Orquestrador: valida, monta, assina, valida XSD, envia e persiste."""
import json
from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.models.config_store import alocar_numero_rps, get_config
from app.models.nota import Nota

from .parser import (
    extrair_retorno_soap,
    parse_retorno_cancelamento,
    parse_retorno_consulta,
    parse_retorno_envio,
)
from .sign_string import build_cancelamento_sign_string, build_sign_string_v2
from .signer import sign_rps_hash, sign_xml_enveloped
from .soap_client import SoapClient
from .utils import so_digitos, validar_cnpj, validar_cpf
from .xml_builder import (
    build_pedido_cancelamento,
    build_pedido_consulta_periodo,
    build_pedido_envio_lote_rps,
    build_pedido_envio_rps,
    xml_to_string,
)
from .xsd_validator import validar


class EmissaoInvalidaError(Exception):
    def __init__(self, detalhes):
        self.detalhes = detalhes if isinstance(detalhes, list) else [str(detalhes)]
        super().__init__("; ".join(self.detalhes))


class RefEmAndamentoError(Exception):
    pass


class PrefeituraRecusouError(Exception):
    def __init__(self, erros: list[dict], nota: Nota | None = None):
        self.erros = erros
        self.nota = nota
        super().__init__("; ".join(f"[{e['codigo']}] {e['descricao']}" for e in erros))


class EnderecoPayload(BaseModel):
    cep: str = ""
    tipo_logradouro: str = ""
    logradouro: str = ""
    numero: str = ""
    complemento: str = ""
    bairro: str = ""
    codigo_municipio: str = ""
    uf: str = ""


class TomadorPayload(BaseModel):
    cpf_cnpj: str
    razao_social: str = ""
    email: str = ""
    endereco: EnderecoPayload | None = None

    @field_validator("cpf_cnpj")
    @classmethod
    def _valida_doc(cls, v):
        doc = so_digitos(v)
        if len(doc) == 11 and validar_cpf(doc):
            return doc
        if len(doc) == 14 and validar_cnpj(doc):
            return doc
        raise ValueError("CPF/CNPJ do tomador invalido")


class EmissaoPayload(BaseModel):
    tomador: TomadorPayload
    servico: str
    valor: float = Field(gt=0)
    descricao: str = Field(min_length=1, max_length=2000)
    ref_externa: str | None = None
    # Overrides opcionais dos campos fiscais configurados no servico
    aliquota: float | None = None
    iss_retido: bool | None = None
    deducoes: float = 0.0
    valores_retencao: dict = Field(default_factory=dict)
    fiscal: dict = Field(default_factory=dict)


def _montar_dados_rps(cfg: dict, payload: EmissaoPayload, numero_rps: int) -> dict:
    servico_cfg = cfg["servicos"].get(payload.servico)
    if not servico_cfg:
        raise EmissaoInvalidaError(
            f"Servico {payload.servico} nao cadastrado na configuracao"
        )
    fiscal = {
        "nbs": servico_cfg.get("nbs", ""),
        "c_class_trib": servico_cfg.get("c_class_trib", ""),
        "c_ind_op": servico_cfg.get("c_ind_op", ""),
        "fin_nfse": servico_cfg.get("fin_nfse", 0),
        "ind_final": servico_cfg.get("ind_final", 1),
        "ind_dest": servico_cfg.get("ind_dest", 0),
        "c_loc_prestacao": servico_cfg.get("c_loc_prestacao", "3550308"),
        "exigibilidade_suspensa": servico_cfg.get("exigibilidade_suspensa", 0),
        "valor_ipi": 0.0,
    }
    fiscal.update(payload.fiscal)

    tomador = {
        "cpf_cnpj": payload.tomador.cpf_cnpj,
        "razao_social": payload.tomador.razao_social,
        "email": payload.tomador.email,
    }
    if payload.tomador.endereco:
        tomador["endereco"] = payload.tomador.endereco.model_dump()

    return {
        "serie": cfg["serie_rps"],
        "numero": numero_rps,
        "data_emissao": date.today(),
        "status": "N",
        "tributacao": cfg.get("tributacao", "T"),
        "iss_retido": (
            payload.iss_retido
            if payload.iss_retido is not None
            else servico_cfg.get("iss_retido", False)
        ),
        "valor": payload.valor,
        "deducoes": payload.deducoes,
        "valores_retencao": payload.valores_retencao,
        "codigo_servico": payload.servico,
        "aliquota": (
            payload.aliquota
            if payload.aliquota is not None
            else servico_cfg.get("aliquota", 0.02)
        ),
        "discriminacao": payload.descricao,
        "tomador": tomador,
        "fiscal": fiscal,
    }


def emitir(payload: EmissaoPayload, session, client: SoapClient,
           cert, private_key) -> dict:
    """Fluxo completo de emissao. Retorna dict com a nota ou resultado de teste."""
    cfg = get_config(session)
    modo_teste = bool(cfg.get("modo_teste", True))

    if payload.ref_externa:
        existente = (
            session.query(Nota).filter(Nota.ref_externa == payload.ref_externa).first()
        )
        if existente is not None:
            if existente.status == "processando":
                raise RefEmAndamentoError(payload.ref_externa)
            if existente.status in ("autorizada", "cancelada"):
                return {"nota": existente, "idempotente": True, "teste": False}
            # status erro: nova tentativa reaproveita a linha
            session.delete(existente)
            session.commit()

    numero_rps = alocar_numero_rps(session)
    dados = _montar_dados_rps(cfg, payload, numero_rps)
    prestador = cfg["prestador"]

    sign_str = build_sign_string_v2(
        inscricao=prestador["inscricao_municipal"],
        serie=dados["serie"],
        numero=numero_rps,
        data_emissao=dados["data_emissao"],
        tributacao=dados["tributacao"],
        status=dados["status"],
        iss_retido=dados["iss_retido"],
        valor_cobrado=dados["valor"],
        deducoes=dados["deducoes"],
        cod_servico=dados["codigo_servico"],
        tomador={
            "cpf" if len(dados["tomador"]["cpf_cnpj"]) == 11 else "cnpj":
                dados["tomador"]["cpf_cnpj"]
        },
    )
    assinatura_rps = sign_rps_hash(private_key, sign_str)

    if modo_teste:
        root = build_pedido_envio_lote_rps(prestador, dados, assinatura_rps)
        schema = "PedidoEnvioLoteRPS_v02.xsd"
    else:
        root = build_pedido_envio_rps(prestador, dados, assinatura_rps)
        schema = "PedidoEnvioRPS_v02.xsd"

    sign_xml_enveloped(root, cert, private_key)
    validar(root, schema)
    xml_enviado = xml_to_string(root)

    if modo_teste:
        resposta = client.teste_envio_lote_rps(xml_enviado)
        retorno = parse_retorno_envio(extrair_retorno_soap(resposta))
        return {"teste": True, "resultado": retorno, "xml_enviado": xml_enviado}

    nota = Nota(
        ref_externa=payload.ref_externa,
        numero_rps=numero_rps,
        serie_rps=dados["serie"],
        tomador_nome=dados["tomador"].get("razao_social"),
        tomador_doc=dados["tomador"]["cpf_cnpj"],
        valor=payload.valor,
        codigo_servico=payload.servico,
        status="processando",
        xml_enviado=xml_enviado,
    )
    session.add(nota)
    session.commit()

    try:
        resposta = client.envio_rps(xml_enviado)
    except Exception:
        nota.status = "erro"
        nota.erros_json = json.dumps(
            [{"codigo": "rede", "descricao": "Falha de comunicacao com a prefeitura"}]
        )
        session.commit()
        raise

    retorno = parse_retorno_envio(extrair_retorno_soap(resposta))
    nota.xml_retorno = resposta
    if retorno["sucesso"]:
        nota.status = "autorizada"
        nota.numero_nfse = retorno["numero_nfse"]
        nota.codigo_verificacao = retorno["codigo_verificacao"]
        session.commit()
        return {"nota": nota, "teste": False}

    nota.status = "erro"
    nota.erros_json = json.dumps(retorno["erros"], ensure_ascii=False)
    session.commit()
    raise PrefeituraRecusouError(retorno["erros"], nota)


def cancelar(nota: Nota, session, client: SoapClient, cert, private_key) -> Nota:
    cfg = get_config(session)
    prestador = cfg["prestador"]
    if not nota.numero_nfse:
        raise EmissaoInvalidaError("Nota sem numero de NFS-e, nao ha o que cancelar")

    sign_str = build_cancelamento_sign_string(
        prestador["inscricao_municipal"], nota.numero_nfse
    )
    assinatura = sign_rps_hash(private_key, sign_str)
    root = build_pedido_cancelamento(prestador, nota.numero_nfse, assinatura)
    sign_xml_enveloped(root, cert, private_key)
    validar(root, "PedidoCancelamentoNFe_v02.xsd")

    resposta = client.cancelamento_nfe(xml_to_string(root))
    retorno = parse_retorno_cancelamento(extrair_retorno_soap(resposta))
    if not retorno["sucesso"]:
        raise PrefeituraRecusouError(retorno["erros"], nota)

    nota.status = "cancelada"
    nota.xml_retorno = resposta
    session.commit()
    return nota


def sincronizar(dt_inicio: date, dt_fim: date, session, client: SoapClient,
                cert, private_key) -> dict:
    """ConsultaNFeEmitidas no periodo e upsert das notas no banco local."""
    cfg = get_config(session)
    prestador = cfg["prestador"]
    root = build_pedido_consulta_periodo(prestador, dt_inicio, dt_fim)
    sign_xml_enveloped(root, cert, private_key)
    validar(root, "PedidoConsultaNFePeriodo_v02.xsd")

    resposta = client.consulta_nfe_periodo(xml_to_string(root))
    notas_remotas = parse_retorno_consulta(extrair_retorno_soap(resposta))

    novas, atualizadas = 0, 0
    for remota in notas_remotas:
        if not remota["numero_nfse"]:
            continue
        local = (
            session.query(Nota).filter(Nota.numero_nfse == remota["numero_nfse"]).first()
        )
        status = "cancelada" if remota["status"] == "C" else "autorizada"
        if local is None:
            session.add(Nota(
                numero_nfse=remota["numero_nfse"],
                codigo_verificacao=remota["codigo_verificacao"],
                numero_rps=int(remota["numero_rps"]) if remota["numero_rps"] else None,
                tomador_nome=remota["tomador_nome"],
                tomador_doc=remota["tomador_doc"],
                valor=remota["valor"],
                codigo_servico=remota["codigo_servico"],
                status=status,
            ))
            novas += 1
        elif local.status != status:
            local.status = status
            atualizadas += 1
    session.commit()
    return {"novas": novas, "atualizadas": atualizadas, "total_remoto": len(notas_remotas)}
