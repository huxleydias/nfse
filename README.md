# NFS-e

Emissor de NFS-e sem intermediarios, em dois ambientes:

- **Municipal:** webservice oficial da Prefeitura de Sao Paulo (LoteNFe), nos leiautes **1** (pre reforma) e **2** (reforma tributaria IBS/CBS).
- **Nacional:** Sistema Nacional NFS-e (Sefin Nacional, DPS v1.01). Obrigatorio para ME e EPP do Simples Nacional em competencias a partir de 01/11/2026.

- Backend: Python + FastAPI (assinatura XML local com certificado A1, validacao XSD antes de cada envio)
- Frontend: React + shadcn (login, notas, emissao manual, configuracao, certificado)
- API generica com bearer token para automacoes (n8n, WooCommerce, qualquer cliente)
- Servidor MCP para conectar assistentes de IA (Claude, Cursor e afins)
- PDF oficial da nota, buscado no portal da prefeitura
- Banco SQLite e certificado em volume persistente (Railway)

## Requisitos

- Python 3.12+ e Node 22+ (desenvolvimento)
- Certificado digital A1 (.pfx) da empresa
- Inscricao municipal (CCM) em Sao Paulo

## Leiaute 1 ou 2: leia antes de emitir

A prefeitura aceita dois leiautes de XML e **o regime tributario da empresa decide qual usar**. Mandar o errado faz a nota ser recusada.

| Regime | Leiaute hoje | Passa a usar o 2 em |
|---|---|---|
| Simples Nacional e MEI | **1** | 4 de janeiro de 2027 |
| Regime Normal (Lucro Real e Presumido, CRT 3) | 2 | ja obrigatorio desde 3 de agosto de 2026 |

O padrao do sistema e o **leiaute 1**, que atende Simples Nacional e MEI, hoje a maioria dos emissores. Se a empresa estiver no Regime Normal, mude para o 2 antes de emitir. Enviar o leiaute que nao corresponde ao regime faz a prefeitura recusar a nota, com uma mensagem apontando qual leiaute usar.

Onde muda: **Configuracao > Layout do XML**. O toggle troca leiaute 1 e 2, e tudo mais acompanha sozinho (builder do XML, string de assinatura, XSD de validacao e o `VersaoSchema` do envelope SOAP). Quando a reforma valer para o Simples, basta ligar o 2.

Diferencas entre os leiautes:

| | Leiaute 1 | Leiaute 2 |
|---|---|---|
| Inscricao na string de assinatura do RPS | 8 posicoes | 12 posicoes |
| Campo de valor na assinatura | ValorServicos | valor cobrado |
| Valor no XML | `ValorServicos` | `ValorFinalCobrado` (choice com `ValorInicialCobrado`) |
| Campos da reforma | nao existem | `NBS`, `cLocPrestacao` e o grupo `IBSCBS` (`finNFSe`, `indFinal`, `cIndOp`, `indDest`, `cClassTrib`) |
| Cabecalho e `VersaoSchema` | `1` | `2` |
| XSDs usados | `*_v01.xsd` | `*_v02.xsd` |

No leiaute 1 os campos NBS, cClassTrib e cIndOp continuam salvos na configuracao de cada servico, mas nao entram no XML. Confirme esses valores com a contabilidade da empresa antes de virar para o leiaute 2: sao codigos fiscais que variam por atividade e regime.

Atencao: NT 2025.002, grupo W03, Imposto Seletivo e `pDevTrib` sao da NF-e de mercadorias (modelo 55, SEFAZ nacional) e nao existem na NFS-e municipal de Sao Paulo. O leiaute da NFS-e paulistana e o do manual do webservice, nao o da NT.

## Ambiente nacional (Sistema Nacional NFS-e)

A Resolucao CGSN 191/2026 obriga ME e EPP optantes do Simples Nacional a emitir so pelo Emissor Nacional (web ou API) para competencias a partir de 01/11/2026, mesmo em municipio com sistema proprio. O webservice de Sao Paulo passou a recusar esses contribuintes com o erro 1647 e segue valendo para o Regime Normal e para emissao retroativa ate 31/10/2026.

Onde muda: **Configuracao > Ambiente de emissao**. Com `nacional`:

- A nota vira uma DPS (Declaracao de Prestacao de Servicos) v1.01, assinada com o mesmo certificado A1, validada contra os XSDs oficiais em `backend/schemas/nacional/1.01/` e enviada em JSON com o XML em GZip + Base64, com TLS mutuo.
- Modo teste ligado: a nota sai na **producao restrita** (homologacao) do Sistema Nacional, sem valor fiscal, e fica gravada como `nacional_homologacao`, com a ref prefixada por `homologacao:` para nao bloquear a mesma ref em producao. Da para testar o cancelamento ali.
- Cada nota guarda o ambiente em que saiu: notas antigas continuam sendo canceladas e consultadas na prefeitura.
- Sincronizacao continua so no municipal.

O que configurar no bloco **Sistema Nacional**:

| Campo | Para que serve |
|---|---|
| Percentual aproximado de tributos do Simples (`p_tot_trib_sn`) | Obrigatorio para ME/EPP (o indicador alternativo e proibido para esse regime). Sem valor a emissao e recusada antes de enviar. Confirme com o contador |
| Apuracao dos tributos (`reg_ap_trib_sn`) | 1 quando federais e ISSQN sao apurados pelo Simples |
| Serie e proximo numero da DPS | Serie numerica de 1 a 49999. O contador so avanca; a homologacao tem contador proprio |
| Municipio emissor | Codigo IBGE (Sao Paulo e `3550308`) |
| Informar inscricao municipal | A IM so vai na DPS se o prestador tiver registro complementar no cadastro nacional (CNC) do municipio |

Em cada servico: **codigo de tributacao nacional** (6 digitos, ex.: instrucao e treinamento `080201`) e, se quiser, o **NBS** (9 digitos).

Regras do Anexo I que o sistema ja segue: sem prefixo de namespace no XML, sem nome e endereco do prestador quando ele mesmo emite, sem aliquota para ME/EPP apurando pelo Simples sem retencao, e sem o grupo IBS/CBS (para o Simples ele vale a partir de 01/01/2027).

Protecao contra nota duplicada: a identificacao da DPS (municipio + CNPJ + serie + numero) fica gravada na nota. Se a rede cair no meio do envio, a nova tentativa da mesma `ref_externa` reaproveita essa identificacao e pergunta ao Sistema Nacional se a DPS ja virou nota antes de reenviar.

Hoje a emissao nacional cobre o prestador como emitente (ME/EPP do Simples). Substituicao de nota, demais eventos e o PDF proprio (DANFSe) ficam para depois.

## PDF da nota

O webservice devolve XML, nunca PDF. Quem gera o documento impresso e um endpoint publico do portal da NF-e paulistana, protegido pelo codigo de verificacao da nota. O sistema busca esse PDF server-side e entrega com nome de arquivo decente:

- `GET /api/notas/{id}/pdf` visualiza (inline)
- `GET /api/notas/{id}/pdf?download=true` baixa como `nfse-{numero}.pdf`

Na interface: logo apos emitir, a tela de confirmacao ja mostra o PDF junto com os botoes de baixar e abrir. Na lista em `/notas`, cada nota autorizada tem os botoes **PDF** e **Baixar**, e o dialog de detalhe mostra o documento inteiro.

Notas com erro ou ainda em processamento nao tem PDF: a rota responde 409, porque o documento so existe depois que a prefeitura autoriza.

No ambiente nacional a API de geracao do DANFSe foi suspensa em 03/08/2026 (NT 008). A nota nacional traz `pdf_url` com o link da Consulta Publica (`https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave=<chave>`, o mesmo do QR Code do DANFSe), e `GET /api/notas/{id}/pdf` responde 307 para esse link.

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

Abra http://localhost:8000, faca login, envie o certificado na tela Certificado e preencha a Configuracao (prestador, servicos, leiaute).

Para desenvolvimento do frontend com hot reload: `cd frontend && npm run dev` (proxy de `/api` para a porta 8000).

## Modo teste

Sao Paulo nao tem ambiente de homologacao: o jeito de testar e contra a producao mesmo. Por isso a config nasce com `modo_teste` ATIVO: a emissao chama `TesteEnvioLoteRPS`, que valida tudo na prefeitura (certificado, assinaturas, leiaute, schema, dados) e responde se passaria, **sem emitir nota**. Rode o smoke antes da primeira nota real:

```bash
set -a && source .env && set +a
backend/.venv/bin/python scripts/teste_envio_real.py
```

Com o smoke passando, desligue o modo teste na Configuracao. A primeira emissao real recomendada: nota de R$ 1,00 para voce mesmo, cancelada em seguida pela UI.

## Chaves de API

A tela **Chaves de API** cria e revoga as chaves que autenticam tanto a API REST quanto o servidor MCP. A chave completa aparece **uma unica vez**, na criacao: o banco guarda so o hash SHA-256, entao nem um vazamento do banco devolve a chave. A lista mostra apenas o prefixo, o suficiente para identificar qual e qual.

Revogar tem efeito imediato: a chave para de funcionar na API e no MCP na mesma hora, sem como reativar.

A variavel de ambiente `API_TOKEN` continua valendo em paralelo, para integracoes anteriores a essa tela.

## MCP: conectar um assistente de IA

O sistema expoe um servidor MCP em `/mcp` (transporte Streamable HTTP), autenticado com uma chave da tela de Chaves. Com ele, um assistente emite, consulta e cancela notas conversando com voce.

Em clientes que usam arquivo de configuracao:

```json
{
  "mcpServers": {
    "nfse": {
      "type": "http",
      "url": "https://SEU-DOMINIO/mcp",
      "headers": { "Authorization": "Bearer SUA_CHAVE" }
    }
  }
}
```

Ferramentas disponiveis:

| Ferramenta | O que faz |
|---|---|
| `consultar_configuracao` | ambiente, prestador, leiaute e se o modo teste esta ativo |
| `listar_notas` | lista com filtros de status e periodo |
| `consultar_nota` | detalhe de uma nota, com link do PDF (ou da Consulta Publica no nacional) |
| `emitir_nota` | emite no ambiente configurado; `competencia` opcional no nacional |
| `cancelar_nota` | cancela no ambiente em que a nota saiu; `motivo_codigo` e `motivo` no nacional |
| `sincronizar_notas` | puxa notas emitidas fora do sistema (so municipal) |

As descricoes avisam o modelo de que emitir gera documento fiscal real com o modo teste desligado e que cancelar e irreversivel, mas **o modo teste e quem garante**: deixe ativo enquanto estiver experimentando.

Uma observacao sobre `MCP_ALLOWED_HOSTS`: o SDK do MCP traz protecao contra DNS rebinding validando o header `Host` contra uma allowlist, e a lista vazia recusa qualquer dominio que nao seja localhost. Informe seus dominios nessa variavel (separados por virgula) para liga-la. Sem a variavel a protecao fica desligada, o que e seguro aqui porque a autenticacao e por chave no header, sem cookie de sessao: nao existe o ataque que ela previne.

## API

Autenticacao: header `Authorization: Bearer <chave>`, com uma chave da tela de Chaves de API ou o `API_TOKEN` do ambiente.

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
    "descricao": "Servico prestado - Pedido #1234",
    "ref_externa": "woo-1234"
  }'
```

- `ref_externa` (opcional) garante idempotencia: repetir a mesma ref devolve a nota ja emitida em vez de duplicar. Use o ID do pedido no seu sistema.
- Tomador CNPJ exige endereco no municipal (`tomador.endereco` com cep, logradouro, numero, bairro, codigo_municipio, uf). No nacional o endereco e opcional e so entra com municipio, CEP, logradouro e bairro.
- Campos fiscais (aliquota, iss_retido, deducoes, valores_retencao, fiscal) aceitam override por request no municipal; o default vem do cadastro do servico na Configuracao.
- `competencia` (AAAA-MM-DD, opcional, padrao hoje em Brasilia, nunca futura): data do servico na DPS do nacional. Ignorada no municipal.
- No nacional a resposta traz `chave_acesso`, `pdf_url` e, quando o Sistema Nacional mandar, `alertas`.

Outros endpoints:

| Metodo | Rota | Descricao |
|---|---|---|
| GET | `/api/notas?inicio=AAAA-MM-DD&fim=...&status=...` | listar notas |
| GET | `/api/notas/{id}` | detalhe com XMLs enviados/retornados |
| GET | `/api/notas/{id}/pdf` | PDF oficial da nota (`?download=true` para baixar); no nacional, 307 para a Consulta Publica |
| DELETE | `/api/notas/{id}` | cancelar a nota no ambiente em que saiu; no nacional aceita `?motivo_codigo=1\|2\|9&motivo=...` (15 a 255 caracteres, padrao "Erro na emissao da nota") |
| POST | `/api/notas/sync` | puxar da prefeitura as notas de um periodo (so municipal) |
| GET/POST | `/api/chaves` | listar e criar chaves de API (sessao da UI) |
| DELETE | `/api/chaves/{id}` | revogar chave (sessao da UI) |
| POST | `/mcp` | servidor MCP (Streamable HTTP) |
| GET | `/api/health` | healthcheck |

Erros: `422` payload, schema ou configuracao invalida, `400` recusa do emissor oficial (codigos originais em `erros_prefeitura` e quem recusou em `emissor`: "Prefeitura" ou "Sistema Nacional"), `409` certificado ausente/vencido, ref em processamento ou operacao indisponivel no ambiente, `502` emissor fora do ar ou certificado recusado no TLS.

## Deploy no Railway

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
backend/app/nfse/     nucleo municipal: builder XML, assinaturas, XSD, SOAP, parser
backend/app/nfse/nacional/  Sistema Nacional: DPS, evento, assinatura por Id, cliente REST, retorno
backend/app/api/      rotas REST
backend/app/core/     settings, db (com migracao de colunas), security, crypto
backend/schemas/      XSDs oficiais v02-5 da prefeitura
backend/schemas/nacional/  XSDs oficiais v1.01 do Sistema Nacional (ver LEIAME.md)
frontend/             React + shadcn
scripts/              smoke test real (TesteEnvioLoteRPS)
docs/                 spec, plano e guia de deploy
```

## Testes

```bash
cd backend && .venv/bin/pytest
```

262 testes no backend (pytest) e 17 no frontend (vitest): vetores oficiais da string de assinatura do manual, XML validado contra os XSDs oficiais nos dois leiautes municipais e na DPS nacional, assinatura XMLDSig conferida por verificador independente, fluxo completo com SOAP e Sefin simulados (inclusive falha de rede sem nota duplicada), API e MCP com TestClient e mascaras de entrada.

Nenhum teste toca a rede: os clientes SOAP e da Sefin e o download do PDF sao mockados, e o certificado e um A1 self-signed gerado em memoria pela fixture. Da pra rodar a suite inteira sem certificado nem credencial.

## Contribuindo

Issues e pull requests sao bem-vindos. Antes de abrir um PR:

```bash
cd backend && .venv/bin/pytest      # 262 testes
cd ../frontend && npm test          # 17 testes
```

Convencoes do projeto:

- Nada especifico de uma empresa em codigo, teste ou doc: sem CNPJ real, inscricao municipal real, dominio de deploy ou razao social. Os testes usam CNPJ ficticio `11222333000181` e "EMPRESA EXEMPLO LTDA"
- Mensagens de UI, comentarios e commits em portugues
- Mudanca no XML enviado a prefeitura precisa de teste que valide contra os XSDs oficiais em `backend/schemas/`
- Se a prefeitura publicar XSD novo, substitua a pasta inteira e rode a suite

Este projeto e independente e nao tem vinculo com a Prefeitura de Sao Paulo. Os XSDs em `backend/schemas/` sao os schemas publicos publicados por ela.

## Licenca

MIT. Veja [LICENSE](LICENSE).

## Referencias

Documentacao do projeto:

- [Guia de deploy no Railway](docs/deploy-railway.md): CLI e dashboard, passo a passo
- [Spec de design](docs/superpowers/specs/2026-07-30-nfse-design.md): arquitetura e decisoes
- [Plano de implementacao](docs/superpowers/plans/2026-07-30-nfse.md): tasks e criterios de teste
- `CLAUDE.md`: regras do projeto e fatos tecnicos dos leiautes 1 e 2 que custaram caro descobrir

Fontes externas:

- Manual do webservice v3.3.7 (Prefeitura de Sao Paulo)
- Schemas XSD v02-5 (reforma tributaria): `backend/schemas/`
- Endpoint (layouts 1 e 2): `https://nfews.prefeitura.sp.gov.br/lotenfe.asmx`
