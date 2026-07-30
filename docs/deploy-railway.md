# Deploy no Railway

Guia para colocar o NFS-e no ar. **Cada etapa traz as duas rotas: CLI e dashboard web.** Escolha a que preferir, ou misture (as duas mexem no mesmo projeto). O projeto ja traz `Dockerfile` e `railway.toml` prontos, entao o Railway sabe como buildar e rodar a aplicacao sem configuracao manual de build.

Se estiver em duvida: **o dashboard e mais facil na primeira vez** (voce ve o que esta acontecendo), e a CLI e mais rapida depois.

## Por que Railway

O sistema precisa de dois recursos que a maioria das plataformas serverless (Vercel, por exemplo) nao oferece: um processo continuo (nao serverless, para manter conexoes SOAP com timeout de ate 60s) e um volume de disco persistente (para guardar o certificado digital `.pfx` e o banco SQLite entre deploys). Railway oferece os dois de forma simples, com um servico so.

## Pre-requisitos

- Conta no Railway (https://railway.com)
- Repositorio no GitHub (ja feito: https://github.com/huxleydias/nfse)
- Segredos gerados (etapa 1)

---

## 1. Gerar os segredos

**Por que:** a aplicacao nao guarda nenhuma senha ou chave no codigo (isso seria visivel para qualquer um com acesso ao repo). Em vez disso, ela le tres valores de variaveis de ambiente, configuradas so no Railway:

- `ADMIN_PASSWORD_HASH`: a senha de login da UI nunca fica salva em texto puro, nem localmente nem no servidor. Voce gera um hash bcrypt (uma via de mao unica: da pra checar se uma senha bate com o hash, mas nao da pra descobrir a senha a partir do hash) e so o hash e armazenado.
- `API_TOKEN`: o token que qualquer automacao (n8n, WooCommerce, etc.) usa para chamar a API sem passar pela tela de login.
- `SECRET_KEY`: usada para duas coisas: assinar o cookie de sessao da UI (pra ninguem forjar um login) e cifrar a senha do certificado digital antes de salvar no banco.

Essa etapa e a unica que roda so no seu terminal. Nao tem equivalente no dashboard: sao valores gerados na sua maquina, que voce cola la depois.

```bash
# Hash bcrypt da senha de login da UI (vai pedir a senha e nao mostra ela na tela)
backend/.venv/bin/python -c "import bcrypt; print(bcrypt.hashpw(input('senha: ').encode(), bcrypt.gensalt()).decode())"

# API_TOKEN (bearer da API) - rode de novo pra gerar o SECRET_KEY (sao independentes)
backend/.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Rode o segundo comando duas vezes: uma saida vira `API_TOKEN`, a outra vira `SECRET_KEY`. Sao valores diferentes, cada um com seu proprio uso.

Guarde os tres resultados em algum lugar seguro por enquanto. O hash bcrypt comeca com `$2b$...`: esse `$` e so parte do formato, nao e erro.

---

## 2. Criar o projeto

**Por que:** o projeto e o "container" no Railway que agrupa o servico (sua aplicacao rodando), as variaveis de ambiente e o volume de disco. Tudo que vem depois acontece dentro dele.

### Rota A: CLI

```bash
# Instalar a CLI e autenticar (uma vez so por maquina, fica salvo)
npm i -g @railway/cli
railway login
```

`railway login` abre o navegador pra voce autorizar a CLI na sua conta. Depois:

```bash
cd /Users/huxleydias/Sites/nfse
railway init --name nfse
```

Cria o projeto no seu workspace e **vincula a pasta local a ele** (ver caixa abaixo). Se perguntar qual workspace, escolha o seu (ex.: PUNKMETRICS).

### Rota B: Dashboard

1. Acesse https://railway.com/dashboard
2. Botao **New Project** (canto superior direito)
3. Escolha **Deploy from GitHub repo**
4. Primeira vez: o Railway pede pra conectar sua conta do GitHub. Clique em **Configure GitHub App**, autorize e libere o repositorio `nfse` (repo privado precisa ser marcado explicitamente nessa tela do GitHub)
5. De volta no Railway, selecione `huxleydias/nfse` na lista
6. O Railway cria projeto e servico, detecta o `Dockerfile` e ja comeca o primeiro build

Esse primeiro build **sobe sem as variaveis e sem o volume**, entao provavelmente falha ou sobe com erro. Normal: as etapas 3 e 4 resolvem e o deploy bom vem na etapa 5.

Vantagem dessa rota: o repo ja fica conectado, entao todo `git push` na branch principal redeploya sozinho, sem voce rodar nada.

> ### Como a CLI sabe de qual projeto voce esta falando
>
> So vale pra rota CLI, e e a parte que confunde quem tem varios projetos: **nenhum comando recebe o nome do projeto**. A CLI resolve por **vinculo de diretorio**.
>
> O `railway init` (ou `railway link`) grava a associacao `caminho absoluto da pasta -> projeto/ambiente/servico` no arquivo global `~/.railway/config.json`. A partir dai, qualquer comando rodado **de dentro daquela pasta** ja sabe o projeto. Nao e pelo nome da pasta nem por nada dentro do repositorio: e pelo caminho registrado nesse arquivo.
>
> ```bash
> railway status   # a qual projeto/ambiente/servico esta pasta esta vinculada
> railway list     # todos os seus projetos, agrupados por workspace
> railway link     # vincula esta pasta a um projeto JA existente (menu interativo)
> railway unlink   # desfaz o vinculo desta pasta
> ```
>
> Se `railway status` responder `No linked project found`, nenhum comando funciona dessa pasta ate rodar `init` ou `link`. Isso inclui o caso de ter criado o projeto pelo dashboard: pra usar a CLI nele depois, rode `railway link` e escolha o projeto.
>
> Todo subcomando tambem aceita flags explicitas, sem depender do vinculo:
> `railway variable set CHAVE=valor -p <PROJECT_ID> -s <SERVICO> -e <AMBIENTE>`

> ### Se aparecer "Deploys have been paused temporarily" ou "Limited Access"
>
> Nao e erro no seu codigo nem na sua configuracao. E o Railway limitando deploys do plano Hobby em horario de pico ou durante instabilidade da infra deles (contas Pro/Enterprise tem prioridade).
>
> **Atencao:** essa mensagem pode **abortar o `railway init` antes de criar o projeto**. Confirme antes de seguir:
>
> ```bash
> railway list     # o projeto novo aparece na lista?
> railway status   # a pasta ficou vinculada?
> ```
>
> No dashboard, o equivalente e ver se o projeto aparece em https://railway.com/dashboard.
>
> Se o projeto nao existe, o init nao completou: repita mais tarde. Se existe mas a pasta nao ficou vinculada, use `railway link` (nao rode `init` de novo, senao cria projeto duplicado). Status da plataforma em https://status.railway.com. Plano Pro remove essa fila.

---

## 3. Configurar as variaveis de ambiente

**Por que:** aqui entram os tres segredos da etapa 1, mais dois valores simples. Sem eles a aplicacao nem sobe (ela exige `SECRET_KEY` no boot).

| Variavel | Valor |
|---|---|
| `ADMIN_USER` | `huxley` (ou o usuario que preferir pro login) |
| `ADMIN_PASSWORD_HASH` | o hash bcrypt gerado na etapa 1 |
| `API_TOKEN` | o token gerado na etapa 1 |
| `SECRET_KEY` | a chave gerada na etapa 1 |
| `DATA_DIR` | `/data` |

`DATA_DIR=/data` diz pro backend onde procurar o certificado e o banco SQLite dentro do container. Precisa bater exatamente com o caminho do volume da etapa 4.

### Rota A: CLI

```bash
railway variable set ADMIN_USER=huxley --skip-deploys
railway variable set ADMIN_PASSWORD_HASH='<hash bcrypt gerado>' --skip-deploys
railway variable set API_TOKEN='<token gerado>' --skip-deploys
railway variable set SECRET_KEY='<chave gerada>' --skip-deploys
railway variable set DATA_DIR=/data
```

`--skip-deploys` evita que cada variavel dispare um deploy separado; a ultima (sem a flag) aciona um deploy so, ja com tudo no lugar. Use aspas simples nos valores: o hash bcrypt tem `$`, que o shell interpretaria.

### Rota B: Dashboard

1. Abra o projeto e clique no **servico** (o card no canvas)
2. Aba **Variables**
3. Caminho rapido: botao **RAW Editor**, cole tudo de uma vez no formato `.env` e salve:

```
ADMIN_USER=huxley
ADMIN_PASSWORD_HASH=<hash bcrypt gerado>
API_TOKEN=<token gerado>
SECRET_KEY=<chave gerada>
DATA_DIR=/data
```

   No RAW Editor **nao use aspas** nos valores: ali o texto e literal e a aspa viraria parte do valor. Diferente do terminal, onde a aspa serve pra proteger o `$` do shell.

4. Caminho manual: botao **New Variable**, uma por vez, preenchendo nome e valor
5. O Railway acumula as mudancas como **staged changes**: revise e clique em **Deploy** pra aplicar

---

## 4. Criar o volume persistente

**Por que isso importa:** todo deploy no Railway recria o container do zero. Sem volume, qualquer arquivo escrito durante a execucao (o `.pfx` que voce envia pela UI, o `nfse.db` com o historico de notas) desapareceria no proximo deploy. O volume e um disco que sobrevive entre deploys, montado sempre no mesmo caminho (`/data`).

> **Isso NAO vem do `railway.toml`.** O schema de config as code do Railway cobre so as secoes de build e deploy: nao existe chave para volume. Criar o volume e uma acao manual, por CLI ou dashboard. Pulando esta etapa, o sistema funciona ate o primeiro redeploy e depois pede o certificado de novo, com o historico de notas zerado.

### Rota A: CLI

```bash
railway volume add --mount-path /data
```

### Rota B: Dashboard

1. Abra o projeto na tela do canvas (onde aparece o card do servico)
2. Pressione **Cmd+K** (ou **Ctrl+K**) e escolha a opcao de criar volume. Alternativa: **clique com o botao direito** numa area vazia do canvas e use o menu
3. Selecione o **servico** ao qual o volume se conecta (voce so tem um)
4. Defina o **mount path** como exatamente `/data`

Confira depois em **Settings** do servico que o volume aparece montado em `/data`.

---

## 5. Fazer o deploy

**Por que:** ate aqui voce so configurou. Agora a aplicacao e buildada (Docker) e colocada no ar. O `railway.toml` do repo ja diz pro Railway usar o `Dockerfile` e checar `/api/health` pra confirmar que o servico subiu saudavel.

### Rota A: CLI

```bash
railway up
```

Envia o codigo da pasta local, roda o `Dockerfile` (builda o frontend e empacota com o backend Python) e inicia o servico. Voce acompanha o log do build no proprio terminal.

### Rota B: Dashboard

Se veio da rota B na etapa 2, o repo ja esta conectado e o deploy dispara sozinho quando as variaveis sao aplicadas. Pra forcar manualmente:

1. No servico, aba **Deployments**
2. Menu de tres pontos no deploy mais recente > **Redeploy**
3. Ou: **Cmd+K** no canvas > **Deploy Latest Commit**

Acompanhe clicando no deploy em andamento pra ver **Build Logs** e **Deploy Logs**.

Daqui pra frente, todo `git push` na branch principal redeploya automaticamente. Pra mudar qual branch dispara: servico > **Settings** > secao de source.

---

## 6. Gerar o dominio publico

**Por que:** por padrao o servico so tem endereco interno da rede privada do Railway. Sem dominio publico voce nao abre a UI no navegador nem aponta o webhook das automacoes.

### Rota A: CLI

```bash
railway domain
```

### Rota B: Dashboard

1. No servico, aba **Settings**
2. Secao **Networking** > **Public Networking**
3. Botao **Generate Domain**

Nos dois casos voce recebe uma URL `https://algo.up.railway.app`. Anote: e por ela que voce acessa a UI e configura as automacoes.

---

## 7. Pos-deploy (primeira configuracao)

Com o servico no ar, a aplicacao ainda nao sabe quem e o prestador de servico nem tem certificado pra assinar nada. Essa etapa e **toda pela UI da propria aplicacao**, nao pelo Railway: sao dados que podem mudar sem precisar de deploy novo, de proposito.

1. Abra `https://<seu-dominio>` e faca login (`ADMIN_USER` + a senha que voce escolheu na etapa 1, nao o hash)
2. Tela **Certificado**: envie o `.pfx` do certificado A1 e a senha dele. O sistema valida na hora (tenta abrir o certificado com a senha) e, se der certo, cifra a senha antes de salvar: ela nunca fica legivel no banco
3. Tela **Configuracao**:
   - **Prestador**: CNPJ, CCM (inscricao municipal), razao social, e-mail. Identificam quem esta emitindo a nota
   - **RPS**: serie e proximo numero. A serie `PM` ja teve os numeros 1 a 7 usados pelo emissor antigo (via Focus NFe) em abril/2026, por isso o contador nasce em 8, pra nunca repetir numero
   - **Servicos**: cadastre `05762` (cursos/mentoria) e `02881` (consultoria) com os campos NBS, cClassTrib e cIndOp da reforma tributaria (ver aviso abaixo)
   - Deixe **modo teste ATIVO**: isso faz a aplicacao chamar o metodo `TesteEnvioLoteRPS` da prefeitura, que valida tudo (certificado, assinatura, campos obrigatorios) mas garantidamente NAO emite nota real
4. Rode o teste sem risco: aba **Emitir**, botao **Testar emissao**. Manda um pedido de verdade pra prefeitura, mas com modo teste ativo a resposta so confirma "validado" ou aponta erro: nenhuma nota e gerada
5. So depois do teste passar E de confirmar os codigos fiscais com o contador: desligue o modo teste na Configuracao. So a partir dai a emissao gera notas reais
6. Primeira nota real: emita uma de R$ 1,00 pra voce mesmo e cancele em seguida pela lista de Notas. Confirma o fluxo completo (emissao + cancelamento) antes de emitir pra cliente

> **Atencao, nao pule isso:** os valores de `cClassTrib` e `cIndOp` que vem pre-preenchidos sao placeholders do exemplo da documentacao da prefeitura, nao valores fiscais reais da PunkMetrics. Confirme com o contador antes de desligar o modo teste: errar esses campos gera nota com classificacao tributaria incorreta.

---

## 8. Integracao (n8n / WooCommerce)

Webhook de pedido pago chama a API com o bearer token gerado na etapa 1:

```
POST https://<seu-dominio>/api/notas
Authorization: Bearer <API_TOKEN>
```

Use o numero do pedido como `ref_externa` (ex.: `woo-1234`). **Por que:** se o webhook disparar duas vezes por qualquer motivo (retry de rede, reentrega da plataforma), a segunda chamada com a mesma `ref_externa` devolve a nota ja emitida em vez de gerar duplicata.

---

## 9. Operacao do dia a dia

| Tarefa | CLI | Dashboard |
|---|---|---|
| Ver logs | `railway logs` | servico > **Deployments** > clique no deploy > Build/Deploy Logs |
| Redeploy | `railway up` | **Deployments** > tres pontos > **Redeploy** |
| Rollback | (usar dashboard) | **Deployments** > tres pontos num build anterior > **Redeploy** |
| Ver variaveis | `railway variable list` | aba **Variables** |
| Ver volume | `railway volume list` | servico > **Settings** |
| Backup do banco | (usar dashboard) | volume > snapshot |
| Metricas (CPU/RAM) | (usar dashboard) | aba **Metrics** |

O SQLite vive no volume `/data`, que persiste entre deploys, mas **nao tem backup automatico fora do Railway**: faca snapshot manual de vez em quando.

**Certificado A1 vence anualmente.** A tela Certificado da aplicacao alerta quando faltam menos de 30 dias. Renove e envie o novo `.pfx` pela propria UI (aproveite pra trocar a senha do certificado, ja que a senha do certificado atual ficou exposta no historico do git do projeto antigo).

---

## Problemas comuns

| Sintoma | Causa provavel | Fix |
|---|---|---|
| "Deploys have been paused temporarily" no `railway init` ou `railway up` | Fila do plano Hobby em horario de pico, ou instabilidade da plataforma. Nao e erro seu, mas pode abortar o `init` sem criar o projeto | Cheque com `railway list` / `railway status` (ou o dashboard); se o projeto nao existe, repita mais tarde; se existe mas a pasta nao esta vinculada, use `railway link`. Status em https://status.railway.com |
| "No linked project found" em qualquer comando da CLI | a pasta nao esta vinculada (o vinculo mora em `~/.railway/config.json`, por caminho de diretorio) | `railway link` de dentro de `~/Sites/nfse`; ou passe `-p <PROJECT_ID>` no comando |
| Comando da CLI afetou o projeto errado | rodou de outra pasta, vinculada a outro projeto | `railway status` antes de operar; ou seja explicito com `-p/-s/-e` |
| Servico sobe e cai (healthcheck falhando) | falta `SECRET_KEY` (a app aborta no boot sem ela) | confira as 5 variaveis na aba Variables e redeploy |
| 401 no login com a senha certa | hash bcrypt colado errado (cortado, ou com aspas viradas parte do valor no RAW Editor) | regenere o hash e recole: no RAW Editor sem aspas, no terminal com aspas simples |
| 409 "Nenhum certificado configurado" depois de ja ter enviado o .pfx | volume nao existe ou nao esta em `/data`: o arquivo sumiu no ultimo redeploy | crie ou corrija o volume (etapa 4) e reenvie o `.pfx` pela tela Certificado |
| Erro 1002 da prefeitura | pedido caiu no endpoint antigo, que nao aceita layout v2 | confirmar que a URL usada e `nfews.prefeitura.sp.gov.br/lotenfe.asmx` (default do codigo) |
| 502 "Prefeitura fora do ar" | instabilidade do webservice da prefeitura, nao da aplicacao | tentar de novo depois; nenhuma nota fica pela metade (o numero de RPS pode ficar queimado, o que a prefeitura aceita) |
