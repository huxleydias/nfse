# Deploy no Railway

Guia completo para colocar o NFS-e SP no ar. Duas rotas: via CLI (recomendada) ou via dashboard. O projeto ja traz `Dockerfile` e `railway.toml` prontos.

## Pre-requisitos

- Conta no Railway (https://railway.com)
- Repositorio commitado (o deploy via CLI sobe o diretorio local)
- Segredos gerados (comandos abaixo)

## 1. Gerar os segredos

```bash
# Hash bcrypt da senha de login da UI
backend/.venv/bin/python -c "import bcrypt; print(bcrypt.hashpw(input('senha: ').encode(), bcrypt.gensalt()).decode())"

# API_TOKEN (bearer da API) e SECRET_KEY (sessao + cifra da senha do certificado)
backend/.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Guarde os tres valores. O hash contem `$`: ao colar no Railway nao precisa de aspas; em `.env` local, aspas simples.

## 2. Deploy via CLI (recomendado)

```bash
# Instalar e autenticar (uma vez)
npm i -g @railway/cli
railway login

# Na pasta do projeto
cd /Users/huxleydias/Sites/nfse-sp
railway init --name nfse-sp

# Variaveis de ambiente
railway variables --set "ADMIN_USER=huxley" \
  --set "ADMIN_PASSWORD_HASH=<hash bcrypt>" \
  --set "API_TOKEN=<token>" \
  --set "SECRET_KEY=<chave>" \
  --set "DATA_DIR=/data"

# Volume persistente (certificado + SQLite)
railway volume add --mount-path /data

# Subir
railway up
```

O `railway.toml` ja define builder Dockerfile, healthcheck em `/api/health` e o volume em `/data`.

Dominio publico:

```bash
railway domain
```

Anote a URL gerada (ex.: `nfse-sp-production.up.railway.app`).

## 3. Alternativa: deploy via dashboard (GitHub)

1. Suba o repo para o GitHub (repo privado): `gh repo create nfse-sp --private --source . --push`
2. No Railway: New Project, Deploy from GitHub repo, selecione `nfse-sp`
3. Em Variables, adicione: `ADMIN_USER`, `ADMIN_PASSWORD_HASH`, `API_TOKEN`, `SECRET_KEY`, `DATA_DIR=/data`
4. Em Settings do servico, confirme o volume montado em `/data` (o railway.toml declara; se nao aparecer, crie manualmente: Volumes, New Volume, mount path `/data`)
5. Settings, Networking, Generate Domain
6. Cada push na branch principal redeploya automaticamente

## 4. Pos-deploy (primeira configuracao)

1. Abra `https://<seu-dominio>` e faca login (`ADMIN_USER` + senha escolhida)
2. Tela Certificado: envie o `.pfx` do A1 e a senha (validada na hora, cifrada no banco)
3. Tela Configuracao:
   - Prestador: CNPJ, CCM (inscricao municipal), razao social, e-mail
   - RPS: serie e proximo numero (serie PM ja usou 1 a 7; contador nasce em 8)
   - Servicos: cadastre `05762` (cursos/mentoria) e `02881` (consultoria) com NBS, cClassTrib e cIndOp
   - Deixe modo teste ATIVO
4. Smoke real sem emitir nota (roda local apontando para os mesmos dados, ou direto pela UI com modo teste ativo): botao Testar emissao na tela Emitir
5. Com o teste passando e os codigos fiscais confirmados com o contador: desligue o modo teste na Configuracao
6. Primeira nota real: R$ 1,00 para voce mesmo, depois cancele pela lista

## 5. Integracao (n8n / WooCommerce)

Webhook de pedido pago chama a API com o bearer token:

```
POST https://<seu-dominio>/api/notas
Authorization: Bearer <API_TOKEN>
```

Use o numero do pedido como `ref_externa` (`woo-1234`): retry do webhook nunca duplica nota.

## 6. Operacao

- Logs: `railway logs` (ou aba Deployments no dashboard)
- Rollback: dashboard, Deployments, Redeploy em um build anterior
- Backup: o SQLite vive no volume `/data`; snapshot pelo dashboard (Volumes)
- Certificado A1 vence anualmente: a tela Certificado alerta com menos de 30 dias; envie o novo .pfx pela propria UI (aproveite e troque a senha do certificado)

## Problemas comuns

| Sintoma | Causa provavel | Fix |
|---|---|---|
| 401 no login com senha certa | hash bcrypt truncado (`$` interpretado) | recole o hash; em `.env` local use aspas simples |
| 409 "Nenhum certificado configurado" | upload nao feito apos redeploy sem volume | confirme volume em `/data` e reenvie o .pfx |
| Erro 1002 da prefeitura | pedido caiu no endpoint v1 | conferir URL `nfews.prefeitura.sp.gov.br/lotenfe.asmx` (ja e o default do codigo) |
| 502 Prefeitura fora do ar | instabilidade do webservice | tentar de novo; nada e emitido pela metade (RPS queimado e ok) |
