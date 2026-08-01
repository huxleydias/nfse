# NFS-e

Emissor standalone de NFS-e no webservice da Prefeitura de Sao Paulo. Suporta os leiautes 1 (pre reforma) e 2 (reforma IBS/CBS). Projeto open source: nada especifico de uma empresa deve entrar no codigo, nos testes ou na documentacao.

## Regras do projeto

- NUNCA usar travessao em nenhum entregavel (codigo, comentario, UI, doc). Grep antes de commitar.
- Idioma de UI, mensagens, docs e commits: portugues (sem acentos em codigo/commits e permitido).
- Segredos SO em variaveis de ambiente (`.env` local, Variables no Railway). Nunca em codigo ou config commitada. Valores com `$` (hash bcrypt) entre aspas simples no `.env`.
- A senha do certificado A1 nunca aparece em log, resposta de API ou texto puro em disco (cifrada com Fernet, chave derivada de SECRET_KEY).
- Todo XML enviado a prefeitura valida ANTES contra os XSDs oficiais em `backend/schemas/` (v02-5). Se a prefeitura publicar XSD novo, substituir a pasta inteira e rodar a suite.
- Emissao real so com `modo_teste` desligado; o metodo de teste e `TesteEnvioLoteRPS` (recebe lote com 1 RPS).
- Numeracao de RPS nunca regride: o contador em config so avanca. Numero queimado por falha de rede e aceitavel (prefeitura tolera gaps).

## O mais importante: layout 1 vs layout 2

O leiaute do XML depende do **regime tributario** de quem emite, nao de uma escolha do sistema:

| Regime | Leiaute | Vira leiaute 2 em |
|---|---|---|
| Simples Nacional e MEI | 1 | 04/01/2027 |
| Regime Normal (CRT 3) | 2 | ja obrigatorio desde 03/08/2026 |

Default do sistema: `layout: 1` na config, com toggle na tela Configuracao. Enviar o leiaute que nao corresponde ao regime faz a prefeitura recusar a nota apontando qual usar. Builder, assinatura, XSD e VersaoSchema seguem esse campo, entao trocar o toggle basta.

Diferencas praticas entre os layouts:

| | Layout 1 | Layout 2 |
|---|---|---|
| Inscricao na string de assinatura | 8 posicoes | 12 posicoes |
| Campo 8 da assinatura | ValorServicos | Valor cobrado |
| Valor no XML | `ValorServicos` | `ValorFinalCobrado` (choice com Inicial) |
| Campos da reforma | nao existem | `NBS`, `cLocPrestacao`, grupo `IBSCBS` |
| Cabecalho / VersaoSchema | `1` | `2` |
| XSDs | `*_v01.xsd` | `*_v02.xsd` |

## PDF da nota

Nao existe PDF no webservice: ele so devolve XML. O documento impresso vem de
`https://nfe.prefeitura.sp.gov.br/contribuinte/notaprintpdf.aspx?inscricao={ccm}&nf={numero}&verificacao={codigo}`,
endpoint publico do portal (sem certificado e sem login, protegido pelo codigo de
verificacao). Descoberto abrindo o `notaprint.aspx`, que carrega esse PDF num iframe.

O backend busca server-side (`app/nfse/pdf.py`) em vez de linkar direto, por dois
motivos: nao expor a inscricao municipal na URL do navegador e poder nomear o
arquivo. A prefeitura devolve HTML de erro com status 200 quando a chave nao bate,
entao a checagem e pelo magic number `%PDF`.

## Fatos tecnicos que custaram caro descobrir

- Endpoint v2: `https://nfews.prefeitura.sp.gov.br/lotenfe.asmx`. O endpoint antigo (`nfe.prefeitura.sp.gov.br/ws/lotenfe.asmx`) NAO aceita layout 2 e devolve erro 1002.
- Cabecalho do pedido: atributo `Versao="2"`. Envelope SOAP 1.1 com `VersaoSchema=2` e `MensagemXML` em CDATA.
- `tpRPS` v2: `ValorInicialCobrado` e `ValorFinalCobrado` sao um `xs:choice` (enviar SO UM; usamos ValorFinalCobrado, tributos por dentro). `ValorServicos` da v1 nao existe mais.
- `cLocPrestacao` (grupo gpPrestacao) e obrigatorio: codigo IBGE do municipio da prestacao (3550308 = SP).
- String de assinatura do RPS v2: inscricao com 12 posicoes (v1 era 8), valor cobrado no campo 8, indicador de tomador aceita 4 (NIF) com campo 16 no final. Vetores oficiais do manual em `backend/tests/test_sign_string.py`.
- Assinatura de cancelamento: 20 posicoes (inscricao 8 + numero NFS-e 12), diferente da assinatura de RPS.
- O xmldsig da prefeitura exige `Transforms` e `KeyInfo/X509Data/X509Certificate` na Signature (schema customizado).
- Consulta por periodo: metodo `ConsultaNFeEmitidas` com `PedidoConsultaNFePeriodo_v02.xsd`.

## Chaves de API e servidor MCP

- Uma chave (`nfse_...`) autentica a API REST e o MCP. Banco guarda so o hash SHA-256; o valor em claro existe apenas na resposta de criacao. Nunca logar nem devolver o valor em outro lugar.
- `API_TOKEN` do ambiente segue valendo em paralelo, para integracoes antigas.
- O servidor MCP e criado por **fabrica** (`criar_servidor()`), nao no import: o session manager do SDK so roda uma vez por instancia, e cada startup (inclusive de cada TestClient) precisa de uma limpa. Por isso existe o delegador `MontagemMCP`, que recebe o app pronto no lifespan.
- Autenticacao do MCP fica na borda (`MontagemMCP.__call__`), antes do SDK: sem chave valida a requisicao nem chega nas ferramentas.
- Protecao de DNS rebinding do SDK: allowlist vazia recusa todo Host que nao seja localhost, o que derruba producao. Controlada por `MCP_ALLOWED_HOSTS`; sem a variavel fica desligada (seguro aqui, porque a auth e por header, sem cookie).
- Ferramenta que gera efeito irreversivel (emitir com modo teste desligado, cancelar) precisa dizer isso na descricao, para o modelo confirmar com o usuario antes.

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

## Cuidados com dados de instalacao

- `cClassTrib` e `cIndOp` variam por atividade e regime: sao configuraveis de proposito, e a config nasce com placeholders. Nunca tratar os placeholders como valores fiscais validos.
- Se a empresa ja emitiu RPS na serie por outro sistema, o contador precisa comecar acima do ultimo numero usado, senao a prefeitura recusa por duplicidade.
- Nada de CNPJ, inscricao municipal, dominio de deploy ou razao social reais em codigo, teste ou doc. Os testes usam CNPJ ficticio (`11222333000181`), CCM `12345678` e "EMPRESA EXEMPLO LTDA".

## Docs

- Spec: `docs/superpowers/specs/2026-07-30-nfse-design.md`
- Plano: `docs/superpowers/plans/2026-07-30-nfse.md`
- Deploy: `docs/deploy-railway.md`
