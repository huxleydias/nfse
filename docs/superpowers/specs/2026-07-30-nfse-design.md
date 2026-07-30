# NFS-e: emissor direto no webservice da Prefeitura de São Paulo

Data: 2026-07-30
Status: aprovado por Huxley (brainstorm seção a seção)

## Objetivo

Sistema standalone que emite, lista e cancela NFS-e no webservice oficial da Prefeitura de São Paulo, sem intermediário (sem Focus NFe). Layout versão 2 da reforma tributária (IBS/CBS) desde o início. UI para configuração e operação, API genérica com bearer token para automações (n8n, WooCommerce, qualquer cliente).

Projeto independente: git próprio, README próprio, CLAUDE.md próprio. Deploy no Railway em serviço único com volume persistente.

## Contexto e referências

- Manual oficial: `NFe_Web_Service-v3.3.7.pdf` (guia do webservice LoteNFe)
- Schemas XSD v2: pasta `schemas-reformatributaria-v02-5` (copiar para `backend/schemas/`)
- Referência de implementação: emissor SOAP v1 arquivado em `punkmetrics/archives/nfe-soap/emit_nfe.py` (assinatura XML funcionou em produção, 7 RPS emitidos na série PM em abril/2026)
- Endpoint v2 (aceita layouts 1 e 2): `https://nfews.prefeitura.sp.gov.br/lotenfe.asmx`
- Endpoint antigo `https://nfe.prefeitura.sp.gov.br/ws/lotenfe.asmx` NÃO aceita v2 (causa do erro 1002 visto no Focus)
- Cabeçalho do XML: campo `Versao` igual a 2
- A string de assinatura do RPS mudou na v2 (changelog out/2025 do manual). Implementar conforme a seção correspondente do manual, não copiar a regra v1 do emissor arquivado
- `TesteEnvioRPS` disponível em produção com campos v2: caminho de teste sem emitir nota real (SP não tem ambiente de homologação separado)

## Decisões (com raciocínio)

| Decisão | Escolha | Raciocínio |
|---|---|---|
| Stack backend | Python + FastAPI | Reaproveita padrão do núcleo crypto/SOAP já testado em produção (emissor arquivado) |
| Frontend | Vite + React + TS + Tailwind + shadcn (componentes via CLI do shadcn) | Pedido do Huxley; UI de qualidade com custo baixo |
| Deploy | Railway, serviço único | Volume persistente para certificado e SQLite; FastAPI serve API e build estático; uma URL |
| Construção do XML | lxml manual + validação XSD local antes de enviar | Controle total sobre C14N (assinatura exige byte exato); XSD local dá a garantia estrutural que codegen daria com fração do código |
| API | Genérica, não acoplada a nenhum consumidor | n8n/WooCommerce transformam pedido em payload padrão fora do sistema |
| Emissão | Síncrona (EnvioRPS de 1 RPS) | Resposta na hora, sem fila e sem poll |
| Banco | SQLite em volume | Porte do sistema não justifica Postgres; CREATE TABLE IF NOT EXISTS no boot, sem framework de migração |
| Fonte da lista de notas | Banco local + sync sob demanda (ConsultaNFePeriodo) | Lista rápida offline; sync traz notas emitidas fora do sistema |

Descartado: codegen xsdata (centenas de classes geradas para manter), templates de string (frágil para assinatura digital), Vercel (sem disco persistente para o certificado, serverless com timeout).

## Estrutura do repositório

```
nfse/
├── CLAUDE.md
├── README.md                   (setup, deploy, geração de secrets, uso da API)
├── .env.example
├── backend/
│   ├── app/
│   │   ├── main.py             (FastAPI, monta rotas, serve frontend build)
│   │   ├── api/                (rotas REST)
│   │   ├── core/               (config, security, db)
│   │   ├── nfse/               (xml_builder, xsd_validator, signer, soap_client, parser)
│   │   └── models/             (SQLAlchemy)
│   ├── schemas/                (XSDs v02-5)
│   ├── tests/
│   └── requirements.txt        (versões pinadas)
├── frontend/                   (Vite + React + TS + shadcn)
│   └── src/pages/              (login, notas, emitir, config, certificado)
├── Dockerfile                  (multi-stage: build frontend, imagem Python final)
└── railway.toml                (healthcheck /api/health; volume e criado a parte)
```

Local de trabalho: `/Users/huxleydias/Sites/nfse` (fora da pasta punkmetrics; repo aninhado sujaria o git da punkmetrics).

## Domínio NFS-e (backend/app/nfse/)

- `xml_builder.py`: monta `PedidoEnvioRPS` layout v2 com lxml. Cabeçalho `Versao=2`. `tpRPS` com todos os campos obrigatórios v2. Valores fiscais vêm da config (defaults por serviço) com override por request.
- `xsd_validator.py`: valida o XML montado contra `PedidoEnvioRPS_v02.xsd` local ANTES de assinar e enviar. Erro de schema vira 422 com elemento e motivo.
- `signer.py`: duas assinaturas conforme manual v3.3.7:
  1. String de assinatura do RPS (regra v2), RSA-SHA1, base64 no campo `Assinatura`
  2. XMLDSig enveloped no documento (C14N, digest SHA1, elemento `Signature`), portando o padrão do emissor arquivado
- `soap_client.py`: POST em `https://nfews.prefeitura.sp.gov.br/lotenfe.asmx`, TLS mútuo com certificado A1, envelope SOAP. Métodos: `EnvioRPS`, `TesteEnvioRPS`, `ConsultaNFe`, `ConsultaNFePeriodo`, `CancelamentoNFe`.
- `parser.py`: parseia retornos (RetornoEnvioRPS, RetornoCancelamentoNFe, RetornoConsulta). Sucesso extrai número NFS-e e código de verificação; falha extrai lista de erros com código e mensagem da prefeitura.

### Campos obrigatórios do layout v2 (verificados no TiposNFe_v02.xsd)

Novos no tpRPS v2 com minOccurs=1:

| Campo | Origem no sistema |
|---|---|
| `NBS` | config por serviço |
| `IBSCBS` (grupo) | montado pelo builder com dados da config/request |
| `ValorInicialCobrado` e `ValorFinalCobrado` | valor do request (substituem `ValorServicos`, excluído na v2) |
| `ValorIPI` | fixo 0.00 (serviços) |
| `ExigibilidadeSuspensa` | config, default não |
| `ValorDeducoes`, `ValorPIS`, `ValorCOFINS`, `ValorINSS`, `ValorIR`, `ValorCSLL` | request, default 0.00 |

Dentro do grupo `IBSCBS`, obrigatórios: `finNFSe`, `indFinal`, `cIndOp` (tabela Anexo VII), `indDest`, `valores > trib > gIBSCBS > cClassTrib`. Opcionais: `tpOper`, `dest`, `gTribRegular > cClassTribReg`.

Nota: NT 2025.002, grupo W03, Imposto Seletivo e pDevTrib pertencem à NF-e de mercadorias (modelo 55, SEFAZ nacional) e NÃO existem no schema da NFS-e municipal de SP (verificado por grep no XSD).

### Fluxo de emissão

```
payload -> validar dados -> montar XML v2 -> validar XSD -> assinar RPS
-> assinar XMLDSig -> SOAP EnvioRPS -> parsear retorno
-> gravar nota no SQLite (autorizada ou erro) -> responder
```

- Modo teste: flag na config troca `EnvioRPS` por `TesteEnvioRPS`. Mesmo fluxo, resposta marca `teste: true`, não grava nota.
- Numeração RPS: contador no SQLite. Série e próximo número editáveis na config (começar acima de 7 se reutilizar a série PM). Incremento em transação antes do envio; número queimado em falha de rede é aceitável (prefeitura aceita gaps).

## Banco de dados (SQLite em /data/nfse.db)

- `notas`: ref interna, ref_externa (única, nullable), número RPS, série, número NFS-e, código de verificação, tomador (nome, CPF/CNPJ), valor, código de serviço, status (autorizada, cancelada, erro, teste), XML enviado, XML retorno, timestamps.
- `config`: chave/valor JSON: prestador, serviços (cada um com alíquota, ISS retido, NBS, cClassTrib, cIndOp, finNFSe, indFinal, indDest), série e próximo número RPS, modo teste.
- Senha do certificado cifrada também vive no banco (ver Segurança).

## API REST

| Rota | Auth | Função |
|---|---|---|
| `POST /api/auth/login` | user/senha do .env | sessão UI (cookie httpOnly) |
| `POST /api/notas` | Bearer ou sessão | emitir nota |
| `GET /api/notas` | Bearer ou sessão | listar (filtros: período, status, tomador) |
| `GET /api/notas/{id}` | Bearer ou sessão | detalhe com XMLs |
| `DELETE /api/notas/{id}` | Bearer ou sessão | cancelar na prefeitura |
| `POST /api/notas/sync` | sessão | ConsultaNFePeriodo, upsert local |
| `GET/PUT /api/config` | sessão | prestador, serviços, RPS, modo teste |
| `POST /api/certificado` | sessão | upload .pfx + senha (multipart) |
| `GET /api/certificado` | sessão | CN, emissor, validade, dias restantes |
| `GET /api/health` | aberta | healthcheck Railway |

Payload de emissão:

```json
{
  "tomador": {
    "cpf_cnpj": "04891850000188",
    "razao_social": "Empresa X",
    "email": "fin@empresa.com",
    "endereco": { "cep": "01310100", "logradouro": "...", "numero": "..." }
  },
  "servico": "05762",
  "valor": 599.00,
  "descricao": "Curso IA para Designers - Pedido #1234",
  "ref_externa": "woo-1234"
}
```

- `servico` referencia o cadastro na config (alíquota e campos IBS/CBS default). Qualquer campo fiscal aceita override opcional no payload.
- `ref_externa` única garante idempotência: repetição devolve a nota existente (200), protege retry de webhook.
- Códigos: 422 validação/XSD com detalhe por campo, 400 erro da prefeitura (códigos originais no corpo), 409 certificado ausente/vencido ou ref em andamento, 502 prefeitura fora do ar.

## Frontend

- Login: form simples.
- Notas (home): tabela shadcn com data, número, tomador, valor, badge de status, ações (detalhe, PDF na prefeitura, cancelar com dialog de confirmação). Botão Sincronizar. Filtros de período e status.
- Emitir: form completo de tomador (endereço via ViaCEP), select de serviço da config, valor, descrição. Banner visível quando modo teste ativo.
- Configuração: prestador, CRUD de serviços com campos IBS/CBS, série e próximo RPS, toggle modo teste.
- Certificado: upload .pfx com senha, exibe CN e validade, alerta com menos de 30 dias.

## Segurança

- Login da UI: `ADMIN_USER` + `ADMIN_PASSWORD_HASH` (bcrypt) no .env. README traz o comando de geração do hash. Sessão em cookie httpOnly assinado com `SECRET_KEY`, expira em 7 dias. Rate limit de 5 tentativas por minuto no login.
- API: `API_TOKEN` no .env (mínimo 32 chars aleatórios, comando no README). Comparação em tempo constante.
- Certificado: .pfx gravado em `/data/certs/` (volume, fora da imagem e do git). Senha cifrada com Fernet (chave derivada de `SECRET_KEY`) e salva no SQLite. Nunca em texto puro em disco, env, logs ou respostas. Certificado vencido bloqueia emissão. `GET /api/certificado` expõe apenas metadados.
- Atenção herdada: a senha do certificado A1 atual vazou no histórico do git da punkmetrics. Rotacionar a senha do A1 quando possível.
- HTTPS pela borda do Railway. CORS restrito à própria origem (mesmo domínio). Dependências pinadas.

Variáveis de ambiente: `ADMIN_USER`, `ADMIN_PASSWORD_HASH`, `API_TOKEN`, `SECRET_KEY`.

## Tratamento de erros

| Cenário | Comportamento |
|---|---|
| Payload inválido | 422 com campo e motivo, nada enviado |
| XML reprova no XSD local | 422 com elemento faltante ou inválido, nada enviado |
| Prefeitura retorna erro | nota gravada com status erro, XML retorno salvo, 400 com códigos originais |
| Prefeitura fora do ar ou timeout | 502, RPS queimado registrado, retry seguro |
| Certificado vencido ou ausente | 409 antes de montar XML |
| ref_externa repetida (emissão concluída) | devolve nota existente, 200 |
| ref_externa repetida (emissão em andamento) | 409, cliente tenta de novo depois |

Log estruturado JSON por emissão (ref, RPS, resultado, duração), sem dados sensíveis. XML enviado e XML retorno salvos por nota para auditoria.

## Testes

- Unit (pytest): builder XML v2 (campos IBS/CBS, valores em centavos, truncamentos), string de assinatura RPS v2 byte a byte contra exemplo do manual, validação XSD com casos válidos e inválidos, parser de retornos, cifra da senha do certificado.
- Integração local: fluxo completo com SOAP mockado (fixtures de XMLs reais), banco em memória, idempotência de ref_externa, contador RPS sob concorrência.
- Smoke real (script manual): `TesteEnvioRPS` contra a prefeitura com certificado real. Gate antes da primeira emissão de verdade.
- Frontend sem testes automatizados nesta fase (formulários simples). Verificação por preview manual.

## Deploy (Railway)

- Dockerfile multi-stage: stage 1 builda o frontend (node, gera dist), stage 2 Python slim com backend, dist e XSDs.
- railway.toml: healthcheck `/api/health`. O volume em `/data` nao cabe no railway.toml (schema so cobre build e deploy): criar por CLI `railway volume add --mount-path /data` ou pelo dashboard.
- Push no GitHub aciona auto-deploy (ou `railway up` manual). Rollback pelos builds anteriores do Railway; SQLite no volume sobrevive a redeploy.

## Fases de entrega

1. Núcleo: builder v2, assinaturas, validador XSD, testes unit (sem rede)
2. SOAP client e `TesteEnvioRPS` real passando com certificado
3. API REST, banco, auth
4. Frontend (login, notas, emitir, config, certificado)
5. Docker, deploy Railway, smoke em produção com nota real de R$ 1,00 cancelada em seguida

## Pendências fora do escopo de construção

- Confirmar com o contador os valores reais de `cClassTrib` e `cIndOp` da PunkMetrics (Simples Nacional). Sistema deixa configurável por isso; usar placeholders do exemplo até a confirmação e não emitir nota de cliente antes de confirmar.
- Rotação da senha do certificado A1 (vazada no histórico do git da punkmetrics).
