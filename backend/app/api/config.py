from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import db_session
from app.core.security import sessao_requerida
from app.models.config_store import AMBIENTES, get_config, save_config
from app.nfse.utils import so_digitos

CONTADORES_DPS = ("proximo_numero_dps", "proximo_numero_dps_homologacao")

router = APIRouter(prefix="/api/config", tags=["config"])

# O XML da prefeitura recebe a aliquota como fracao (0.02 = 2%). ISS municipal
# vai de 2% a 5%, entao qualquer valor acima de 1 e percentual digitado por
# engano e viraria uma nota com aliquota absurda. Barrar aqui e melhor do que
# descobrir na nota emitida.
ALIQUOTA_MAX = 1.0


def _validar_servicos(servicos: dict) -> None:
    erros = []
    for codigo, s in (servicos or {}).items():
        try:
            aliquota = float(s.get("aliquota", 0))
        except (TypeError, ValueError):
            erros.append(f"Servico {codigo}: aliquota nao e numero")
            continue
        if aliquota < 0 or aliquota > ALIQUOTA_MAX:
            erros.append(
                f"Servico {codigo}: aliquota {aliquota} fora da faixa. "
                f"Use fracao, nao percentual: 2% e 0.02"
            )
        c_trib_nac = s.get("c_trib_nac")
        if c_trib_nac not in (None, "") and not (
            len(so_digitos(c_trib_nac)) == 6 == len(str(c_trib_nac))
        ):
            erros.append(f"Servico {codigo}: c_trib_nac deve ter 6 digitos (ex.: 080201)")
        c_nbs = s.get("c_nbs")
        if c_nbs not in (None, "") and not (len(so_digitos(c_nbs)) == 9 == len(str(c_nbs))):
            erros.append(f"Servico {codigo}: c_nbs deve ter 9 digitos")
        c_trib_mun = s.get("c_trib_mun")
        if c_trib_mun not in (None, "") and not (
            len(so_digitos(c_trib_mun)) == 3 == len(str(c_trib_mun)) and str(c_trib_mun) != "000"
        ):
            erros.append(f"Servico {codigo}: c_trib_mun deve ter 3 digitos, exceto 000 (ex.: 001)")
    if erros:
        raise HTTPException(status_code=422, detail=erros)


def _validar_nacional(novos: dict) -> None:
    """Ambiente e bloco nacional. Percentual vazio e aceito (a emissao e que
    recusa), para a config poder ser salva aos poucos."""
    erros = []
    if "ambiente" in novos and novos["ambiente"] not in AMBIENTES:
        erros.append(f"ambiente deve ser um de: {', '.join(AMBIENTES)}")
    nac = novos.get("nacional")
    if nac is not None and not isinstance(nac, dict):
        erros.append("nacional deve ser um objeto")
        nac = None
    nac = nac or {}

    def inteiro(nome, minimo, maximo=None):
        if nome not in nac:
            return
        try:
            valor = int(str(nac[nome]))
        except (TypeError, ValueError):
            erros.append(f"nacional.{nome} deve ser numero inteiro")
            return
        if valor < minimo or (maximo is not None and valor > maximo):
            faixa = f"de {minimo} a {maximo}" if maximo is not None else f"a partir de {minimo}"
            erros.append(f"nacional.{nome} deve estar {faixa}")

    inteiro("serie_dps", 1, 49999)
    inteiro("op_simp_nac", 1, 3)
    inteiro("reg_ap_trib_sn", 1, 3)
    inteiro("reg_esp_trib", 0, 6)
    for contador in CONTADORES_DPS:
        inteiro(contador, 1)
    if "c_loc_emi" in nac and len(so_digitos(str(nac["c_loc_emi"]))) != 7:
        erros.append("nacional.c_loc_emi deve ter o codigo IBGE de 7 digitos")
    if nac.get("p_tot_trib_sn") not in (None, ""):
        try:
            p = float(nac["p_tot_trib_sn"])
        except (TypeError, ValueError):
            p = -1
        if not 0 <= p < 100:
            erros.append("nacional.p_tot_trib_sn deve ser percentual de 0 a 99,99")
    if "informar_im" in nac and not isinstance(nac["informar_im"], bool):
        erros.append("nacional.informar_im deve ser true ou false")
    im = nac.get("inscricao_municipal")
    if im not in (None, ""):
        if not isinstance(im, str) or len(im.strip()) > 15 or any(c.isspace() for c in im.strip()):
            erros.append("nacional.inscricao_municipal deve ter ate 15 caracteres, sem espacos")
    if erros:
        raise HTTPException(status_code=422, detail=erros)


@router.get("", dependencies=[Depends(sessao_requerida)])
def obter_config(session=Depends(db_session)):
    cfg = get_config(session)
    # Nunca expor a senha cifrada do certificado
    cfg.pop("certificado", None)
    return cfg


@router.put("", dependencies=[Depends(sessao_requerida)])
def atualizar_config(novos: dict, session=Depends(db_session)):
    if "servicos" in novos:
        _validar_servicos(novos["servicos"])
    _validar_nacional(novos)
    cfg = get_config(session)
    # Bloco certificado so muda via upload dedicado
    novos.pop("certificado", None)
    if isinstance(novos.get("nacional"), dict):
        # Mescla em vez de substituir, e contador de DPS nunca regride: a tela
        # pode mandar um valor lido antes de uma emissao que ja avancou o numero.
        nacional = {**cfg["nacional"], **novos.pop("nacional")}
        for contador in CONTADORES_DPS:
            nacional[contador] = max(int(cfg["nacional"][contador]), int(nacional[contador]))
        if nacional.get("p_tot_trib_sn") == "":
            nacional["p_tot_trib_sn"] = None
        cfg["nacional"] = nacional
    cfg.update(novos)
    save_config(session, cfg)
    cfg_limpa = {k: v for k, v in cfg.items() if k != "certificado"}
    return cfg_limpa
