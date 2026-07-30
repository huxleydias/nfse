# NFS-e

Emissor de NFS-e direto no webservice oficial da Prefeitura de Sao Paulo (LoteNFe), sem intermediarios. Layout versao 2 da reforma tributaria (IBS/CBS) desde o inicio.

- Backend: Python + FastAPI (assinatura XML local com certificado A1, validacao XSD antes de cada envio)
- Frontend: React + shadcn (login, notas, emissao manual, configuracao, certificado)
- API generica com bearer token para automacoes (n8n, WooCommerce, qualquer cliente)
- Banco SQLite e certificado em volume persistente (Railway)

## Requisitos

- Python 3.12+ e Node 22+ (desenvolvimento)
- Certificado digital A1 (.pfx) da empresa
- Inscricao municipal (CCM) em Sao Paulo

## Setup local

```bash
# Backend
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
npm run build   # o FastAPI serve o build em producao

# Variaveis de ambiente
cd ..
cp .env.example .env
# Preencha os valores (comandos de geracao abaixo)
```

Gerar segredos:

```bash
# Hash da senha de login (cole a senha quando pedir)
backend/.venv/bin/python -c "import bcrypt; print(bcrypt.hashpw(input('senha: ').encode(), bcrypt.gensalt()).decode())"

# API_TOKEN e SECRET_KEY
backend/.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))"
```

IMPORTANTE: no `.env`, o hash bcrypt contem `$`. Use aspas simples no valor:
`ADMIN_PASSWORD_HASH='$2b$12$...'`

Rodar:

```bash
set -a && source .env && set +a
backend/.venv/bin/uvicorn app.main:app --app-dir backend --port 8000
```

Abra http://localhost:8000, faca login, envie o certificado na tela Certificado e preencha a Configuracao (prestador, servicos, campos IBS/CBS).

Para desenvolvimento do frontend com hot reload: `cd frontend && npm run dev` (proxy de `/api` para a porta 8000).

## Modo teste

A config nasce com `modo_teste` ATIVO: a emissao chama `TesteEnvioLoteRPS`, que valida tudo na prefeitura (certificado, assinaturas, schema v2, dados) sem emitir nota. Rode o smoke antes da primeira nota real:

```bash
set -a && source .env && set +a
backend/.venv/bin/python scripts/teste_envio_real.py
```

Com o smoke passando, desligue o modo teste na Configuracao. A primeira emissao real recomendada: nota de R$ 1,00 para voce mesmo, cancelada em seguida pela UI.

## API

Autenticacao: header `Authorization: Bearer $API_TOKEN`.

Emitir nota:

```bash
curl -X POST https://SEU-DOMINIO/api/notas \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tomador": {
      "cpf_cnpj": "111.444.777-35",
      "razao_social": "Fulano de Tal",
      "email": "fulano@example.com"
    },
    "servico": "05762",
    "valor": 599.00,
    "descricao": "Curso IA para Designers - Pedido #1234",
    "ref_externa": "woo-1234"
  }'
```

- `ref_externa` (opcional) garante idempotencia: repetir a mesma ref devolve a nota ja emitida em vez de duplicar. Use o ID do pedido no seu sistema.
- Tomador CNPJ exige endereco (`tomador.endereco` com cep, logradouro, numero, bairro, codigo_municipio, uf).
- Campos fiscais (aliquota, iss_retido, deducoes, valores_retencao, fiscal) aceitam override por request; o default vem do cadastro do servico na Configuracao.

Outros endpoints:

| Metodo | Rota | Descricao |
|---|---|---|
| GET | `/api/notas?inicio=AAAA-MM-DD&fim=...&status=...` | listar notas |
| GET | `/api/notas/{id}` | detalhe com XMLs enviados/retornados |
| DELETE | `/api/notas/{id}` | cancelar a nota na prefeitura |
| GET | `/api/health` | healthcheck |

Erros: `422` payload ou schema invalido, `400` recusa da prefeitura (codigos originais no corpo), `409` certificado ausente/vencido ou ref em processamento, `502` prefeitura fora do ar.

## Deploy no Railway

No ar em https://nfse-production-9338.up.railway.app (projeto `nfse`, workspace PUNKMETRICS).

**Guia completo: [docs/deploy-railway.md](docs/deploy-railway.md)**

Passo a passo com as duas rotas lado a lado (CLI e dashboard web) em cada etapa, explicando o motivo de cada uma:

1. Gerar os segredos (o que cada um protege)
2. Criar o projeto (e como a CLI resolve qual projeto e o seu)
3. Configurar as variaveis de ambiente
4. Criar o volume persistente (obrigatorio: sem ele o certificado e o banco somem a cada redeploy)
5. Fazer o deploy
6. Gerar o dominio publico
7. Primeira configuracao pela UI (certificado, prestador, servicos, modo teste)
8. Integracao com n8n / WooCommerce
9. Operacao do dia a dia (logs, redeploy, rollback, backup)

O guia tambem traz uma tabela de problemas comuns (deploys pausados no plano Hobby, projeto nao vinculado, healthcheck falhando, erro 1002 da prefeitura).

## Estrutura

```
backend/app/nfse/     nucleo: builder XML v2, assinaturas, XSD, SOAP, parser
backend/app/api/      rotas REST
backend/app/core/     settings, db, security, crypto
backend/schemas/      XSDs oficiais v02-5 da prefeitura
frontend/             React + shadcn
scripts/              smoke test real (TesteEnvioLoteRPS)
docs/                 spec, plano e guia de deploy
```

## Testes

```bash
cd backend && .venv/bin/pytest
```

114+ testes: vetores oficiais da string de assinatura v2 do manual, XML validado contra os XSDs oficiais, assinatura XMLDSig verificavel, fluxo completo com SOAP mockado, API com TestClient.

## Referencias

Documentacao do projeto:

- [Guia de deploy no Railway](docs/deploy-railway.md): CLI e dashboard, passo a passo
- [Spec de design](docs/superpowers/specs/2026-07-30-nfse-design.md): arquitetura e decisoes
- [Plano de implementacao](docs/superpowers/plans/2026-07-30-nfse.md): tasks e criterios de teste
- `CLAUDE.md`: regras do projeto e fatos tecnicos do layout v2 que custaram caro descobrir

Fontes externas:

- Manual do webservice v3.3.7 (Prefeitura de Sao Paulo)
- Schemas XSD v02-5 (reforma tributaria): `backend/schemas/`
- Endpoint (layouts 1 e 2): `https://nfews.prefeitura.sp.gov.br/lotenfe.asmx`
