# Deploy no Railway

Guia para colocar o NFS-e SP no ar. Duas rotas: via CLI (recomendada) ou via dashboard. O projeto ja traz `Dockerfile` e `railway.toml` prontos, entao o Railway sabe como buildar e rodar a aplicacao sem configuracao manual de build.

## Por que Railway

O sistema precisa de dois recursos que a maioria das plataformas serverless (Vercel, por exemplo) nao oferece: um processo continuo (nao serverless, para manter conexoes SOAP com timeout de ate 60s) e um volume de disco persistente (para guardar o certificado digital `.pfx` e o banco SQLite entre deploys). Railway oferece os dois de forma simples, com um servico so.

## Pre-requisitos

- Conta no Railway (https://railway.com)
- Repositorio no GitHub (ja feito: https://github.com/huxleydias/nfse-sp)
- Segredos gerados (etapa 1)

## 1. Gerar os segredos

**Por que:** a aplicacao nao guarda nenhuma senha ou chave no codigo (isso seria visivel para qualquer um com acesso ao repo). Em vez disso, ela le tres valores de variaveis de ambiente, configuradas so no Railway:

- `ADMIN_PASSWORD_HASH`: a senha de login da UI nunca fica salva em texto puro, nem localmente nem no servidor. Voce gera um hash bcrypt (uma via de mao unica: da pra checar se uma senha bate com o hash, mas nao da pra descobrir a senha a partir do hash) e so o hash e armazenado.
- `API_TOKEN`: o token que qualquer automacao (n8n, WooCommerce, etc.) usa para chamar a API sem passar pela tela de login.
- `SECRET_KEY`: usada para duas coisas: assinar o cookie de sessao da UI (pra ninguem forjar um login) e cifrar a senha do certificado digital antes de salvar no banco.

Gerar os tres valores:

```bash
# Hash bcrypt da senha de login da UI (vai pedir a senha e nao mostra ela na tela)
backend/.venv/bin/python -c "import bcrypt; print(bcrypt.hashpw(input('senha: ').encode(), bcrypt.gensalt()).decode())"

# API_TOKEN (bearer da API) - rode de novo pra gerar o SECRET_KEY (sao independentes)
backend/.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Rode o segundo comando duas vezes: uma saida vira `API_TOKEN`, a outra vira `SECRET_KEY`. Sao valores diferentes, cada um com seu proprio uso.

Guarde os tres resultados (hash, API_TOKEN, SECRET_KEY) em algum lugar seguro por enquanto (voce vai colar eles na etapa 2). O hash bcrypt comeca com `$2b$...`: esse `$` e so parte do formato do hash, nao e um erro.

## 2. Deploy via CLI (recomendado)

**Por que CLI e nao so o dashboard:** a CLI faz em um comando o que no dashboard seria varios cliques (criar projeto, setar variaveis, criar volume, subir o codigo). Ela tambem serve pra debugar depois (`railway logs`, `railway up` de novo).

```bash
# Instalar a CLI e autenticar (uma vez so, fica salvo)
npm i -g @railway/cli
railway login
```

`railway login` abre o navegador pra voce autorizar a CLI na sua conta Railway. So precisa fazer isso uma vez por maquina.

```bash
# Na pasta do projeto
cd /Users/huxleydias/Sites/nfse-sp
railway init --name nfse-sp
```

**O que esse comando faz:** cria um projeto novo dentro do seu workspace no Railway (o "container" que vai agrupar o servico, as variaveis e o volume) e **vincula a pasta local a esse projeto**. Se ele perguntar qual workspace usar, escolha o seu (ex.: PUNKMETRICS).

### Como a CLI sabe de qual projeto voce esta falando

Essa e a parte que confunde quem tem varios projetos no Railway: **nenhum dos comandos seguintes recebe o nome do projeto**. A CLI resolve isso por **vinculo de diretorio**.

O `railway init` (ou `railway link`) grava a associacao `caminho absoluto da pasta -> projeto/ambiente/servico` no arquivo global `~/.railway/config.json`. A partir dai, qualquer comando rodado **de dentro daquela pasta** ja sabe o projeto. Nao e pelo nome da pasta nem por nada dentro do repositorio: e pelo caminho registrado nesse arquivo.

Comandos uteis pra conferir e controlar isso:

```bash
railway status   # mostra a qual projeto/ambiente/servico esta pasta esta vinculada
railway list     # lista todos os seus projetos, agrupados por workspace
railway link     # vincula esta pasta a um projeto JA existente (menu interativo)
railway unlink   # desfaz o vinculo desta pasta
```

Se `railway status` responder `No linked project found`, nenhum comando de projeto vai funcionar dessa pasta ate voce rodar `init` ou `link`.

Todo subcomando tambem aceita flags pra forcar explicitamente, sem depender do vinculo:

```bash
railway variable set CHAVE=valor -p <PROJECT_ID> -s <SERVICO> -e <AMBIENTE>
```

Na pratica: vincule uma vez com `init`/`link` e rode tudo de dentro da pasta. As flags servem pra casos pontuais (script, CI, ou operar outro projeto sem sair do diretorio atual).

> **Se aparecer "Deploys have been paused temporarily" ou "Limited Access":** nao e erro no seu codigo nem na sua configuracao. E o Railway limitando deploys do plano Hobby em horario de pico ou durante instabilidade da infra deles (contas Pro/Enterprise tem prioridade).
>
> **Atencao:** essa mensagem pode **abortar o `railway init` antes de criar o projeto**. Confirme antes de seguir:
>
> ```bash
> railway list     # o projeto novo aparece na lista?
> railway status   # a pasta ficou vinculada?
> ```
>
> Se o projeto nao aparecer, o init nao completou: repita `railway init` mais tarde. Se o projeto foi criado mas a pasta nao ficou vinculada, use `railway link` (nao rode `init` de novo, senao cria um projeto duplicado). Status da plataforma em https://status.railway.com. Plano Pro remove essa fila.

```bash
# Variaveis de ambiente: aqui entram os 3 segredos gerados na etapa 1.
# Roda de dentro da pasta vinculada, por isso nao precisa dizer o projeto.
railway variable set ADMIN_USER=huxley --skip-deploys
railway variable set ADMIN_PASSWORD_HASH='<hash bcrypt gerado>' --skip-deploys
railway variable set API_TOKEN='<token gerado>' --skip-deploys
railway variable set SECRET_KEY='<chave gerada>' --skip-deploys
railway variable set DATA_DIR=/data
```

`--skip-deploys` evita que cada variavel dispare um deploy separado; a ultima (sem a flag) aciona um deploy so, ja com tudo no lugar. Use aspas simples nos valores: o hash bcrypt tem `$`, que o shell interpretaria.

`DATA_DIR=/data` diz pro backend onde procurar o certificado e o banco SQLite dentro do container. Precisa bater exatamente com o caminho do volume que vem a seguir.

```bash
# Volume persistente: sem isso, certificado e banco somem a cada redeploy
railway volume add --mount-path /data
```

**Por que isso importa:** todo deploy no Railway recria o container do zero. Sem volume, qualquer arquivo escrito durante a execucao (o `.pfx` que voce envia pela UI, o `nfse.db` com o historico de notas) desapareceria no proximo deploy. O volume e um disco que sobrevive entre deploys, montado sempre no mesmo caminho (`/data`).

```bash
# Builda a imagem Docker e sobe
railway up
```

Esse comando envia o codigo local, roda o `Dockerfile` (que builda o frontend e empacota com o backend Python) e inicia o servico. O `railway.toml` ja diz pro Railway usar esse Dockerfile, checar `/api/health` pra saber se o servico subiu bem, e montar o volume em `/data`.

Dominio publico:

```bash
railway domain
```

**Por que:** por padrao o servico so tem um endereco interno do Railway. Esse comando gera uma URL publica (`https://algo.up.railway.app`) que voce vai usar pra acessar a UI e configurar o webhook das automacoes. Anote a URL que ele devolver.

## 3. Alternativa: deploy via dashboard (GitHub)

Util se preferir nao instalar a CLI, ou se quiser deploy automatico a cada push sem rodar `railway up` manualmente.

1. O repo ja esta no GitHub: https://github.com/huxleydias/nfse-sp (privado)
2. No Railway: **New Project** > **Deploy from GitHub repo** > selecione `nfse-sp`. Isso conecta o Railway ao repo: a partir daqui, todo push na branch principal aciona um deploy novo automaticamente.
3. Em **Variables**, adicione os mesmos 5 valores da etapa 2 (`ADMIN_USER`, `ADMIN_PASSWORD_HASH`, `API_TOKEN`, `SECRET_KEY`, `DATA_DIR=/data`). Sao a mesma coisa, so preenchidos pela interface em vez da CLI.
4. Em **Settings** do servico, confirme que o volume esta montado em `/data` (o `railway.toml` ja declara isso; se por algum motivo nao aparecer, crie manualmente: **Volumes** > **New Volume** > mount path `/data`).
5. **Settings** > **Networking** > **Generate Domain**: mesma funcao do `railway domain` da CLI.
6. Pronto: de agora em diante, `git push` na branch principal redeploya sozinho.

## 4. Pos-deploy (primeira configuracao)

Com o servico no ar, a aplicacao ainda nao sabe quem e o prestador de servico nem tem certificado pra assinar nada. Essa etapa preenche isso pela propria UI (nada disso fica hardcoded no codigo, de proposito: sao dados que podem mudar sem precisar de novo deploy).

1. Abra `https://<seu-dominio>` e faca login (`ADMIN_USER` + a senha que voce escolheu na etapa 1, nao o hash)
2. Tela **Certificado**: envie o `.pfx` do certificado A1 e a senha dele. O sistema valida na hora (tenta abrir o certificado com a senha) e, se der certo, cifra a senha antes de salvar - ela nunca fica legivel no banco
3. Tela **Configuracao**:
   - **Prestador**: CNPJ, CCM (inscricao municipal), razao social, e-mail. Sao os dados que identificam quem esta emitindo a nota
   - **RPS**: serie e proximo numero. A serie `PM` ja teve os numeros 1 a 7 usados pelo emissor antigo (via Focus NFe) em abril/2026 - por isso o contador nasce em 8, pra nunca repetir um numero ja usado
   - **Servicos**: cadastre `05762` (cursos/mentoria) e `02881` (consultoria) com os campos NBS, cClassTrib e cIndOp da reforma tributaria (ver aviso abaixo)
   - Deixe **modo teste ATIVO** por enquanto - isso faz a aplicacao chamar o metodo `TesteEnvioLoteRPS` da prefeitura, que valida tudo (certificado, assinatura, todos os campos obrigatorios) mas garantidamente NAO emite nenhuma nota real
4. Rode o teste real sem risco: aba **Emitir**, botao **Testar emissao** (ou o script `scripts/teste_envio_real.py` direto no terminal). Isso manda um pedido de verdade pra prefeitura, mas como o modo teste esta ativo, a resposta so confirma "validado" ou aponta erro - nenhuma nota e gerada
5. So depois do teste passar E de confirmar os codigos fiscais com o contador (proximo aviso): desligue o modo teste na Configuracao. So a partir dai a emissao passa a gerar notas reais e valendo
6. Primeira nota real: emita uma de R$ 1,00 pra voce mesmo e cancele em seguida pela lista de Notas. E uma forma barata de confirmar que o fluxo completo (emissao + cancelamento) funciona antes de emitir pra um cliente de verdade

> **Atencao, nao pule isso:** os valores de `cClassTrib` e `cIndOp` que vem pre-preenchidos sao placeholders do exemplo da documentacao da prefeitura, nao valores fiscais reais da PunkMetrics. Confirme com o contador antes de desligar o modo teste - errar esses campos gera nota com classificacao tributaria incorreta.

## 5. Integracao (n8n / WooCommerce)

Webhook de pedido pago chama a API com o bearer token gerado na etapa 1:

```
POST https://<seu-dominio>/api/notas
Authorization: Bearer <API_TOKEN>
```

Use o numero do pedido como `ref_externa` (ex.: `woo-1234`). **Por que:** se o webhook disparar duas vezes por qualquer motivo (retry de rede, reentrega da plataforma), a segunda chamada com a mesma `ref_externa` devolve a nota ja emitida em vez de gerar uma nota duplicada.

## 6. Operacao

- **Logs**: `railway logs` (ou aba Deployments no dashboard) - primeiro lugar pra olhar se algo nao subir ou se uma emissao falhar
- **Rollback**: dashboard, Deployments, Redeploy em um build anterior - util se um deploy novo quebrar algo
- **Backup**: o SQLite vive no volume `/data`, que persiste sozinho entre deploys, mas nao tem backup automatico fora do Railway - considere um snapshot manual pelo dashboard (Volumes) de vez em quando
- **Certificado A1 vence anualmente**: a tela Certificado alerta quando faltam menos de 30 dias. Renove e envie o novo `.pfx` pela propria UI (aproveite pra trocar a senha do certificado, ja que a senha do certificado atual ficou exposta no historico do git do projeto antigo)

## Problemas comuns

| Sintoma | Causa provavel | Fix |
|---|---|---|
| "Deploys have been paused temporarily" no `railway init` ou `railway up` | Fila do plano Hobby em horario de pico, ou instabilidade da plataforma - nao e erro seu, mas pode abortar o `init` sem criar o projeto | Cheque com `railway list` e `railway status`; se o projeto nao existe, repita o `init` mais tarde; se existe mas a pasta nao esta vinculada, use `railway link`. Status em https://status.railway.com |
| "No linked project found" em qualquer comando | a pasta nao esta vinculada a nenhum projeto (o vinculo mora em `~/.railway/config.json`, por caminho de diretorio) | `railway link` de dentro de `~/Sites/nfse-sp` e escolha o projeto; ou passe `-p <PROJECT_ID>` no comando |
| Comando afetou o projeto errado | voce rodou de outra pasta, vinculada a outro projeto | `railway status` antes de operar; ou seja explicito com `-p/-s/-e` |
| 401 no login com senha certa | hash bcrypt colado errado (cortado ou com escape do `$`) | recole o hash gerado; em `.env` local use aspas simples ao redor do valor |
| 409 "Nenhum certificado configurado" | upload nunca foi feito, ou foi feito sem o volume `/data` montado (some no redeploy seguinte) | confirme o volume em Settings > Volumes e reenvie o `.pfx` pela tela Certificado |
| Erro 1002 da prefeitura | pedido caiu no endpoint antigo, que nao aceita o layout v2 | conferir que a URL usada e `nfews.prefeitura.sp.gov.br/lotenfe.asmx` (ja e o default do codigo, mas confirme que nao foi sobrescrita) |
| 502 "Prefeitura fora do ar" | instabilidade do webservice da prefeitura, nao da aplicacao | tentar de novo depois; nenhuma nota fica "pela metade" nesse caso (o numero de RPS pode ficar queimado, o que a prefeitura aceita) |
