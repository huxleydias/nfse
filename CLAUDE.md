# NFS-e

Emissor standalone de NFS-e em dois ambientes: webservice da Prefeitura de Sao Paulo (leiautes 1 e 2) e Sistema Nacional NFS-e (DPS v1.01). Projeto open source: nada especifico de uma empresa deve entrar no codigo, nos testes ou na documentacao.

## Regras do projeto

- NUNCA usar travessao em nenhum entregavel (codigo, comentario, UI, doc). Grep antes de commitar.
- Idioma de UI, mensagens, docs e commits: portugues (sem acentos em codigo/commits e permitido).
- Segredos SO em variaveis de ambiente (`.env` local, Variables no Railway). Nunca em codigo ou config commitada. Valores com `$` (hash bcrypt) entre aspas simples no `.env`.
- A senha do certificado A1 nunca aparece em log, resposta de API ou texto puro em disco (cifrada com Fernet, chave derivada de SECRET_KEY).
- Todo XML enviado valida ANTES contra os XSDs oficiais: `backend/schemas/` (v02-5, prefeitura) e `backend/schemas/nacional/` (Sistema Nacional, uma pasta por leiaute, ver o `LEIAME.md` de la). Se publicarem XSD novo, substituir a pasta inteira e rodar a suite.
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

## Ambiente nacional (Sistema Nacional NFS-e)

ME/EPP do Simples emitem so no Sistema Nacional para competencias a partir de 01/11/2026 (Resolucao CGSN 191/2026); o webservice de SP recusa com o erro 1647. `ambiente` na config escolhe `municipal` ou `nacional`; cada nota guarda o ambiente em que saiu (`municipal`, `nacional`, `nacional_homologacao`) e cancela sempre nele. Codigo em `backend/app/nfse/nacional/`, spec em `docs/superpowers/specs/2026-11-14-nfse-nacional-design.md`.

Fatos que custaram caro descobrir:

- API Sefin: `POST /nfse` com `{"dpsXmlGZipB64"}` (XML em GZip + Base64), mTLS com o A1. Producao `https://sefin.nfse.gov.br/SefinNacional`, producao restrita `https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional`. O Swagger oficial devolve 403 sem certificado cliente; os nomes dos campos foram conferidos num espelho publico e no manual.
- c14n de subarvore do lxml emite `xmlns=""` espurio em filhos da Signature. A assinatura so bate com um verificador padrao canonicalizando o elemento reparseado como documento isolado (`nacional/assinatura.py::_c14n`). O teste com `signxml` pega regressao.
- XSD oficial `TSSerieDPS` usa `^...$`, que em regex de XSD e caractere literal: o libxml2 recusa toda serie. A copia local remove os dois caracteres (ver `backend/schemas/nacional/LEIAME.md`). Reaplicar ao trocar a pasta.
- Sem prefixo de namespace no XML (E1228): DPS e Signature com namespace padrao.
- tpEmit 1 (prestador) nao leva `xNome` nem `end` do prestador (E0121, E0128). IM so vai se houver registro complementar no CNC do municipio (`nacional.informar_im`).
- ME/EPP apurando pelo Simples sem retencao: sem `pAliq` (E0625, E0631) e sem `indTotTrib` (E0712). O total aproximado vai em `pTotTribSN`, que e configuracao de cada instalacao (`nacional.p_tot_trib_sn`); vazio recusa a emissao antes de enviar.
- Serie da DPS e numerica, 1 a 49999 para aplicativo proprio (E0010). Contadores proprios, um para producao e outro para homologacao, que so avancam.
- Falha de rede no envio: a nota fica `erro` com serie e numero da DPS. Nova tentativa da mesma `ref_externa` reaproveita a identificacao e consulta `GET /dps/{id}` antes de reenviar; E0014 (DPS ja convertida) tambem dispara a recuperacao. Assim nao sai nota duplicada.
- Modo teste no nacional emite de verdade na producao restrita (sem valor fiscal) e grava a nota com ref `homologacao:<ref>`, porque `ref_externa` e unica.
- Cancelamento e evento `e101101` com Id `PRE` + chave + `101101`, motivo 1, 2 ou 9 e texto de 15 a 255 caracteres. O XML do evento fica em `xml_evento`; `xml_retorno` guarda a NFS-e autorizada.
- API de DANFSe suspensa em 03/08/2026 (NT 008): `pdf_url` e o link da Consulta Publica (`https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave=`).
- Algoritmo da assinatura em constante (`ALGORITMO_PADRAO = "sha256"`). Se a producao restrita recusar com E0714, a troca para SHA-1 e de uma linha.
- Grupo IBS/CBS ainda nao enviado: para o Simples ele vale a partir de 01/01/2027.
- IM do prestador na DPS: tem que ser igual a do CNC (E0116 quando difere). `nacional.inscricao_municipal` guarda esse valor (Sao Paulo: CCM com zeros a esquerda ate 15 digitos, como aparece no Indicador Municipal do DANFSe); vazio usa `prestador.inscricao_municipal`, que continua servindo ao municipal.
- Servico no nacional: `c_trib_nac` (6 digitos, obrigatorio), `c_trib_mun` (desdobro municipal, 3 digitos, opcional, validado pelo municipio com E0314) e `c_nbs` (9 digitos, opcional; correlacao com o item da LC 116 no Anexo VIII).
- Dois leiautes ate 30/11/2026: producao na NT 004, producao restrita na NT 009 (finNFSe obrigatorio em infDPS e xDescServ no fim de cServ, depois de cNBS). A producao passa para a NT 009 em 01/12/2026 (`INICIO_NT009_PRODUCAO`); se o governo adiar, mudar a constante.
- Colunas novas entram no banco existente pelo `init_db` (`ALTER TABLE ADD COLUMN` para o que faltar), sem framework de migracao.

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
- Spec do ambiente nacional: `docs/superpowers/specs/2026-11-14-nfse-nacional-design.md`
- Plano: `docs/superpowers/plans/2026-07-30-nfse.md`
- Deploy: `docs/deploy-railway.md`
