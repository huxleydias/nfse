"""Edicao da config: normaliza, valida e grava.

Ponto unico usado pela API (tela) e pelo MCP. Quem chama pode mandar os
codigos como aparecem no DANFSe ("08.02.01", "1.2205.19.00") e numeros com
virgula ("11,2"): aqui tudo vira o formato canonico antes de validar.

Unidades guardadas:
- aliquota do ISS (servico.aliquota): fracao, 0.02 = 2%, que e o formato do
  XML municipal. Quem edita em porcentagem converte antes (tela e MCP).
- percentual do Simples (p_tot_trib_sn, geral e por servico): porcentagem,
  11.2 = 11,2%, que e o formato do pTotTribSN.
"""
from app.models.config_store import AMBIENTES, get_config, save_config
from app.nfse.utils import so_digitos

CONTADORES_DPS = ("proximo_numero_dps", "proximo_numero_dps_homologacao")

# ISS municipal vai de 2% a 5% (LC 116, arts. 8 e 8-A). Fracao acima de 0.05
# e porcentagem digitada por engano e viraria nota com aliquota absurda.
ALIQUOTA_MAX = 0.05

# Codigos numericos: (tamanho, menor tamanho que ganha zeros a esquerda).
# O codigo nacional so perde o zero inicial (as tabelas oficiais escrevem
# 80201 para 08.02.01); NBS e IBGE nunca comecam com zero.
_CODIGOS_SERVICO = {
    "c_trib_nac": (6, 5),
    "c_trib_mun": (3, 1),
    "c_nbs": (9, 9),
    "nbs": (9, 9),
    "c_class_trib": (6, 1),
    "c_ind_op": (6, 1),
    "c_loc_prestacao": (7, 7),
}


class ConfigInvalida(Exception):
    def __init__(self, erros: list[str]):
        self.erros = erros
        super().__init__("; ".join(erros))


def numero(valor):
    """"11,2" -> 11.2; "" -> None; numero fica como esta; texto invalido fica
    como esta para a validacao acusar."""
    if valor is None or isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return valor
    texto = str(valor).strip().replace("%", "").strip()
    if texto == "":
        return None
    try:
        return float(texto.replace(".", "").replace(",", ".") if "," in texto else texto)
    except ValueError:
        return valor


def _codigo(valor, tamanho: int, minimo_para_completar: int | None = None):
    if valor in (None, ""):
        return ""
    digitos = so_digitos(str(valor))
    if not digitos:
        return str(valor)
    minimo = tamanho if minimo_para_completar is None else minimo_para_completar
    return digitos.zfill(tamanho) if minimo <= len(digitos) < tamanho else digitos


def normalizar_servico(servico: dict) -> dict:
    s = dict(servico)
    for campo, (tamanho, minimo) in _CODIGOS_SERVICO.items():
        if campo in s:
            s[campo] = _codigo(s[campo], tamanho, minimo)
    if "aliquota" in s:
        s["aliquota"] = numero(s["aliquota"])
    if "p_tot_trib_sn" in s:
        s["p_tot_trib_sn"] = numero(s["p_tot_trib_sn"])
    return s


def normalizar_nacional(nacional: dict) -> dict:
    n = dict(nacional)
    if "p_tot_trib_sn" in n:
        n["p_tot_trib_sn"] = numero(n["p_tot_trib_sn"])
    if "c_loc_emi" in n:
        n["c_loc_emi"] = _codigo(n["c_loc_emi"], 7)
    if "serie_dps" in n and n["serie_dps"] not in (None, ""):
        digitos = so_digitos(str(n["serie_dps"]))
        n["serie_dps"] = str(int(digitos)) if digitos else n["serie_dps"]
    if isinstance(n.get("inscricao_municipal"), str):
        n["inscricao_municipal"] = n["inscricao_municipal"].strip()
    return n


def _erro_percentual_sn(onde: str, valor) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return f"{onde}: percentual do Simples deve ser numero (ex.: 11,2)"
    if not 0 <= valor < 100:
        return f"{onde}: percentual do Simples deve ficar entre 0 e 99,99"
    if 0 < valor < 1:
        # Nenhuma aliquota nominal do Simples fica abaixo de 4%
        return (
            f"{onde}: {str(valor).replace('.', ',')}% parece fracao. Informe em "
            "porcentagem: 11,2 para 11,2%"
        )
    return None


def validar_servicos(servicos: dict) -> list[str]:
    erros = []
    if not isinstance(servicos, dict):
        return ["servicos deve ser um objeto com o codigo de servico como chave"]
    for codigo, s in servicos.items():
        if not so_digitos(str(codigo)) or len(so_digitos(str(codigo))) > 5:
            erros.append(f"Servico {codigo}: codigo municipal deve ter ate 5 digitos")
        aliquota = s.get("aliquota", 0)
        if isinstance(aliquota, bool) or not isinstance(aliquota, (int, float)):
            erros.append(f"Servico {codigo}: aliquota do ISS nao e numero")
        elif aliquota < 0 or aliquota > ALIQUOTA_MAX:
            erros.append(
                f"Servico {codigo}: aliquota do ISS fora da faixa de 0% a 5% "
                f"(guardada como fracao: 2% e 0.02)"
            )
        if s.get("c_trib_nac") and len(s["c_trib_nac"]) != 6:
            erros.append(f"Servico {codigo}: codigo de tributacao nacional deve ter 6 digitos (ex.: 08.02.01)")
        if s.get("c_trib_mun") and (len(s["c_trib_mun"]) != 3 or s["c_trib_mun"] == "000"):
            erros.append(f"Servico {codigo}: codigo municipal deve ter 3 digitos, exceto 000 (ex.: 001)")
        for campo, nome in (("c_nbs", "NBS"), ("nbs", "NBS do layout 2")):
            if s.get(campo) and len(s[campo]) != 9:
                erros.append(f"Servico {codigo}: {nome} deve ter 9 digitos (ex.: 1.2205.19.00)")
        for campo, nome in (("c_class_trib", "cClassTrib"), ("c_ind_op", "cIndOp")):
            if s.get(campo) and len(s[campo]) != 6:
                erros.append(f"Servico {codigo}: {nome} deve ter 6 digitos")
        if s.get("c_loc_prestacao") and len(s["c_loc_prestacao"]) != 7:
            erros.append(f"Servico {codigo}: municipio da prestacao deve ter o codigo IBGE de 7 digitos")
        erro = _erro_percentual_sn(f"Servico {codigo}", s.get("p_tot_trib_sn"))
        if erro:
            erros.append(erro)
    return erros


def validar_nacional(novos: dict) -> list[str]:
    """Ambiente e bloco nacional. Percentual vazio e aceito (a emissao e que
    recusa), para a config poder ser salva aos poucos."""
    erros = []
    if "ambiente" in novos and novos["ambiente"] not in AMBIENTES:
        erros.append(f"ambiente deve ser um de: {', '.join(AMBIENTES)}")
    nac = novos.get("nacional")
    if nac is not None and not isinstance(nac, dict):
        return erros + ["nacional deve ser um objeto"]
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
    erro = _erro_percentual_sn("nacional.p_tot_trib_sn", nac.get("p_tot_trib_sn"))
    if erro:
        erros.append(erro)
    if "informar_im" in nac and not isinstance(nac["informar_im"], bool):
        erros.append("nacional.informar_im deve ser true ou false")
    im = nac.get("inscricao_municipal")
    if im not in (None, ""):
        if not isinstance(im, str) or len(im) > 15 or any(c.isspace() for c in im):
            erros.append("nacional.inscricao_municipal deve ter ate 15 caracteres, sem espacos")
    return erros


def aplicar(session, novos: dict) -> dict:
    """Valida e grava uma atualizacao parcial. Devolve a config sem o bloco do
    certificado. Levanta ConfigInvalida com a lista de erros."""
    novos = dict(novos)
    # Bloco certificado so muda via upload dedicado
    novos.pop("certificado", None)
    if isinstance(novos.get("servicos"), dict):
        novos["servicos"] = {
            so_digitos(str(codigo)) or str(codigo): normalizar_servico(s if isinstance(s, dict) else {})
            for codigo, s in novos["servicos"].items()
        }
    if isinstance(novos.get("nacional"), dict):
        novos["nacional"] = normalizar_nacional(novos["nacional"])
    if isinstance(novos.get("prestador"), dict):
        prestador = dict(novos["prestador"])
        for campo in ("cnpj", "inscricao_municipal"):
            if campo in prestador:
                prestador[campo] = so_digitos(str(prestador[campo] or ""))
        novos["prestador"] = prestador

    erros = []
    if "servicos" in novos:
        erros += validar_servicos(novos["servicos"])
    erros += validar_nacional(novos)
    if erros:
        raise ConfigInvalida(erros)

    cfg = get_config(session)
    if isinstance(novos.get("nacional"), dict):
        # Mescla em vez de substituir, e contador de DPS nunca regride: a tela
        # pode mandar um valor lido antes de uma emissao que ja avancou o numero.
        nacional = {**cfg["nacional"], **novos.pop("nacional")}
        for contador in CONTADORES_DPS:
            nacional[contador] = max(int(cfg["nacional"][contador]), int(nacional[contador]))
        cfg["nacional"] = nacional
    if isinstance(novos.get("prestador"), dict):
        cfg["prestador"] = {**cfg.get("prestador", {}), **novos.pop("prestador")}
    cfg.update(novos)
    save_config(session, cfg)
    return {k: v for k, v in cfg.items() if k != "certificado"}
