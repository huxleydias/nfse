# NFS-e SP

Emissor standalone de NFS-e no webservice da Prefeitura de Sao Paulo, layout v2 (reforma tributaria IBS/CBS). Projeto independente da pasta punkmetrics: git proprio, deploy proprio no Railway.

## Regras do projeto

- NUNCA usar travessao em nenhum entregavel (codigo, comentario, UI, doc). Grep antes de commitar.
- Idioma de UI, mensagens, docs e commits: portugues (sem acentos em codigo/commits e permitido).
- Segredos SO em variaveis de ambiente (`.env` local, Variables no Railway). Nunca em codigo ou config commitada. Valores com `$` (hash bcrypt) entre aspas simples no `.env`.
- A senha do certificado A1 nunca aparece em log, resposta de API ou texto puro em disco (cifrada com Fernet, chave derivada de SECRET_KEY).
- Todo XML enviado a prefeitura valida ANTES contra os XSDs oficiais em `backend/schemas/` (v02-5). Se a prefeitura publicar XSD novo, substituir a pasta inteira e rodar a suite.
- Emissao real so com `modo_teste` desligado; o metodo de teste e `TesteEnvioLoteRPS` (recebe lote com 1 RPS).
- Numeracao de RPS nunca regride: o contador em config so avanca. Numero queimado por falha de rede e aceitavel (prefeitura tolera gaps).

## Fatos tecnicos que custaram caro descobrir

- Endpoint v2: `https://nfews.prefeitura.sp.gov.br/lotenfe.asmx`. O endpoint antigo (`nfe.prefeitura.sp.gov.br/ws/lotenfe.asmx`) NAO aceita layout 2 e devolve erro 1002.
- Cabecalho do pedido: atributo `Versao="2"`. Envelope SOAP 1.1 com `VersaoSchema=2` e `MensagemXML` em CDATA.
- `tpRPS` v2: `ValorInicialCobrado` e `ValorFinalCobrado` sao um `xs:choice` (enviar SO UM; usamos ValorFinalCobrado, tributos por dentro). `ValorServicos` da v1 nao existe mais.
- `cLocPrestacao` (grupo gpPrestacao) e obrigatorio: codigo IBGE do municipio da prestacao (3550308 = SP).
- String de assinatura do RPS v2: inscricao com 12 posicoes (v1 era 8), valor cobrado no campo 8, indicador de tomador aceita 4 (NIF) com campo 16 no final. Vetores oficiais do manual em `backend/tests/test_sign_string.py`.
- Assinatura de cancelamento: 20 posicoes (inscricao 8 + numero NFS-e 12), diferente da assinatura de RPS.
- O xmldsig da prefeitura exige `Transforms` e `KeyInfo/X509Data/X509Certificate` na Signature (schema customizado).
- Consulta por periodo: metodo `ConsultaNFeEmitidas` com `PedidoConsultaNFePeriodo_v02.xsd`.

## Comandos

```bash
# Testes (sempre antes de commitar)
cd backend && .venv/bin/pytest

# Rodar local
set -a && source .env && set +a
backend/.venv/bin/uvicorn app.main:app --app-dir backend --port 8000

# Build frontend (FastAPI serve dist/)
cd frontend && npm run build

# Smoke real contra a prefeitura (modo teste, nao emite nota)
backend/.venv/bin/python scripts/teste_envio_real.py
```

## Pendencias de negocio

- Valores reais de `cClassTrib` e `cIndOp` (PunkMetrics, Simples Nacional) pendentes de confirmacao com o contador. Ate la, placeholders na config e nada de nota real para cliente.
- Serie de RPS PM ja teve numeros 1 a 7 emitidos pelo emissor antigo (abril/2026). O contador nasce em 8; nunca reutilizar numeros anteriores nesta serie.

## Docs

- Spec: `docs/superpowers/specs/2026-07-30-nfse-sp-design.md`
- Plano: `docs/superpowers/plans/2026-07-30-nfse-sp.md`
- Deploy: `docs/deploy-railway.md`
