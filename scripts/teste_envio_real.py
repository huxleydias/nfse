#!/usr/bin/env python3
"""Smoke test REAL contra a prefeitura: TesteEnvioLoteRPS.

Valida certificado, assinaturas, schema v2 e comunicacao TLS SEM emitir nota.
E o gate obrigatorio antes da primeira emissao real.

Uso:
  cd backend && .venv/bin/python ../scripts/teste_envio_real.py

Requisitos: .env carregado (DATA_DIR, SECRET_KEY), certificado enviado pela UI
e config de prestador/servico preenchida.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.db import get_session, init_db  # noqa: E402
from app.models.config_store import get_config  # noqa: E402
from app.nfse.cert_store import carregar_certificado  # noqa: E402
from app.nfse.emitter import EmissaoPayload, emitir  # noqa: E402
from app.nfse.soap_client import SoapClient  # noqa: E402


def main() -> int:
    init_db()
    session = get_session()
    cfg = get_config(session)

    if not cfg.get("modo_teste", True):
        print("ABORTADO: modo_teste esta DESLIGADO na config.")
        print("Este script so roda com modo teste ativo (nao emite nota).")
        return 1

    servicos = list(cfg.get("servicos", {}).keys())
    if not servicos or not cfg["prestador"].get("cnpj"):
        print("ABORTADO: configure prestador e ao menos um servico na UI antes.")
        return 1

    cert, key = carregar_certificado(session)
    client = SoapClient(cert, key)

    payload = EmissaoPayload(
        tomador={"cpf_cnpj": "111.444.777-35", "razao_social": "Teste Homologacao"},
        servico=servicos[0],
        valor=1.0,
        descricao="Teste de integracao do emissor NFS-e (TesteEnvioLoteRPS)",
    )

    print(f"Enviando TesteEnvioLoteRPS (servico {servicos[0]}, R$ 1,00)...")
    resultado = emitir(payload, session, client, cert, key)
    retorno = resultado["resultado"]

    if retorno["sucesso"]:
        print("SUCESSO: prefeitura validou o pedido v2 sem erros.")
        if retorno["alertas"]:
            print("Alertas:")
            for a in retorno["alertas"]:
                print(f"  [{a['codigo']}] {a['descricao']}")
        return 0

    print("PREFEITURA RECUSOU:")
    for e in retorno["erros"]:
        print(f"  [{e['codigo']}] {e['descricao']}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
