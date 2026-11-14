# NFS-e: emissão no Sistema Nacional NFS-e (Sefin Nacional)

Data: 2026-11-14
Status: implementado; falta a validação na produção restrita

## Contexto

A Resolução CGSN nº 191, de 04/08/2026, obriga microempresas e empresas de pequeno porte optantes do Simples Nacional (ME/EPP) a emitir NFS-e só pelo Emissor Nacional, web ou API, para competências a partir de 01/11/2026. A regra vale mesmo em município com sistema próprio.

Na prática, o webservice de São Paulo passou a recusar a emissão desses contribuintes com o erro 1647 ("deve emitir nota no ambiente nacional para fatos geradores a partir de 01/11/2026"). Trocar o leiaute não resolve: com leiaute 2 a recusa vira o erro 641 (Simples exige leiaute 1). O sistema de SP continua aceitando emissão retroativa de fatos geradores até 31/10/2026 e segue sendo o caminho do Regime Normal.

Fontes:

- Prefeitura de SP, aviso de 19/10/2026: https://notadomilhao.sf.prefeitura.sp.gov.br/noticias/migracao-de-contribuintes-do-simples-nacional-para-o-ambiente-nacional/
- Portal NFS-e, diretrizes de 29/10/2026: https://www.gov.br/nfse/pt-br/noticias/nfs-e-informa-diretrizes-sobre-a-obrigatoriedade-da-emissao-da-nfs-e-nacional-para-optantes-do-simples-nacional
- Documentação técnica atual (XSD v1.01 de 09/02/2026, Anexo I de leiaute e regras da DPS, Anexo II de eventos, manual das APIs v1.2): https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual
- URLs das APIs (produção restrita e produção): https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/apis-prod-restrita-e-producao
- NT 008 v1.02 (DANFSe, API de geração suspensa em 03/08/2026): https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/nt-008-se-cgnfse-danfse-20260714-v1-02.pdf

## Objetivo

Emitir, consultar e cancelar NFS-e no Sistema Nacional pela mesma API REST, pela mesma UI e pelas mesmas ferramentas MCP de hoje, sem mudar o fluxo de quem integra. O ambiente municipal de SP continua funcionando para quem precisa dele e para as notas antigas.

Critérios de sucesso:

1. DPS aceita na produção restrita (homologação) com o certificado A1 da instalação.
2. Cancelamento por evento aceito na produção restrita.
3. Primeira nota real autorizada em produção, com chave de acesso de 50 dígitos gravada.
4. Suíte de testes verde, incluindo a suíte atual do ambiente municipal.

## Fora de escopo

- DANFSe em PDF gerado pelo sistema (NT 008). A nota nacional usa o link da Consulta Pública. PDF próprio é uma etapa futura.
- Grupo IBS/CBS na DPS. Para optantes do Simples as regras de IBS/CBS valem a partir de 01/01/2027; esse grupo é a próxima etapa e precisa estar pronto antes dessa data.
- Sincronização com o Sistema Nacional (distribuição por NSU no ADN). A sincronização continua só para o ambiente municipal.
- Emissão nacional como tomador ou intermediário (tpEmit 2 e 3), substituição de NFS-e e demais eventos.

## Decisões

| Decisão | Escolha | Raciocínio |
|---|---|---|
| Como o nacional entra | Ao lado do municipal, escolhido por `ambiente` na configuração | Quem migra troca uma vez; Regime Normal segue em SP; notas antigas cancelam em SP |
| PDF da nota nacional | Link da Consulta Pública (`https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave=<chave>`) | API oficial de DANFSe suspensa; link é o mesmo do QR Code da NT 008 e sai sem dependência nova |
| Leiaute | DPS v1.01, sem grupo IBS/CBS | Simples ainda não exige IBS/CBS em 2026 |
| Contador de DPS | Próprio, separado do RPS de SP, um para produção e outro para homologação | Série da DPS é numérica e o teste não pode abrir lacuna na sequência real |
| Modo teste | Mesmo fluxo na produção restrita, com a nota gravada como de homologação | Permite testar o cancelamento de verdade antes da produção |
| Assinatura | XMLDSig enveloped por referência ao Id, RSA-SHA256, C14N inclusiva, sem prefixo de namespace | Bibliotecas abertas que emitem em produção usam SHA-256; a homologação confirma (ver Riscos) |
| Contrato da API | `dpsXmlGZipB64` e `pedidoRegistroEventoXmlGZipB64` em JSON, XML em GZip + Base64, mTLS com o certificado A1 | Swagger oficial (exige certificado para abrir; campos conferidos num espelho público e no manual) |

Descartado: escolha automática do ambiente por regime e competência (mais regra para testar, e quem migra não volta), e trocar o municipal pelo nacional de vez (quebra Regime Normal e o cancelamento das notas antigas).

## Arquitetura

### Módulos novos em `backend/app/nfse/nacional/`

| Módulo | Responsabilidade |
|---|---|
| `dps.py` | Monta o XML da DPS v1.01 a partir dos dados da emissão; calcula o Id |
| `evento.py` | Monta o pedido de registro de evento de cancelamento (e101101) |
| `assinatura.py` | Assina `infDPS` e `infPedReg` por referência ao atributo Id |
| `cliente.py` | `SefinClient`: REST com mTLS, GZip + Base64, URLs de produção e produção restrita |
| `retorno.py` | Decodifica e lê a NFS-e autorizada, o evento e as mensagens de erro |
| `emissor.py` | Orquestra emitir, recuperar e cancelar no nacional (mantém `emitter.py` do tamanho de hoje) |

XSDs oficiais v1.01 em `backend/schemas/nacional/1.01/`. O `xsd_validator` passa a aceitar a pasta do schema.

`emitter.emitir` e `emitter.cancelar` continuam sendo a porta de entrada da API REST e do MCP: leem `ambiente` (na emissão) ou `nota.ambiente` (no cancelamento) e delegam ao nacional quando for o caso.

### Configuração

Chaves novas, com default que não muda o comportamento de quem já usa o sistema:

```json
{
  "ambiente": "municipal",
  "nacional": {
    "serie_dps": "1",
    "proximo_numero_dps": 1,
    "proximo_numero_dps_homologacao": 1,
    "c_loc_emi": "3550308",
    "op_simp_nac": 3,
    "reg_ap_trib_sn": 1,
    "reg_esp_trib": 0,
    "p_tot_trib_sn": null,
    "informar_im": true
  }
}
```

Em cada serviço de `servicos`: `c_trib_nac` (código de tributação nacional, 6 dígitos, ex.: `05762` corresponde a `080201`) e `c_nbs` opcional. O `c_loc_prestacao` que já existe é reaproveitado.

Regras:

- `serie_dps` aceita de 1 a 49999 (faixa de aplicativo próprio na regra E0010). No Id e no XML vai com 5 dígitos.
- `p_tot_trib_sn` é obrigatório no nacional para ME/EPP (indTotTrib é proibido para ME/EPP, regra E0712). Sem valor configurado, a emissão é recusada localmente com mensagem clara. Placeholder nunca vira valor fiscal.
- Os contadores só avançam, como o de RPS.

### Modelo `Nota`

Colunas novas: `ambiente` (`municipal`, `nacional` ou `nacional_homologacao`, default `municipal`), `chave_acesso` (50), `serie_dps`, `numero_dps`, `competencia` (AAAA-MM-DD) e `xml_evento` (XML do cancelamento, para `xml_retorno` continuar com a NFS-e autorizada).

O banco existente ganha essas colunas no boot: `init_db` lê `PRAGMA table_info(notas)` e roda `ALTER TABLE ADD COLUMN` para o que faltar. Nada é apagado e as notas atuais ficam como `municipal`.

Notas de homologação gravam `ref_externa` como `homologacao:<ref>`, para não bloquear a mesma referência em produção (a coluna é única).

### API, MCP e UI

- `emitir_nota` (MCP) e `POST /api/notas`: campo opcional `competencia` (AAAA-MM-DD, padrão hoje no fuso de São Paulo, não pode ser futura). No municipal o campo é ignorado.
- `cancelar_nota` (MCP) e `DELETE /api/notas/{id}`: `motivo_codigo` opcional (1 erro na emissão, 2 serviço não prestado, 9 outros; padrão 1) e `motivo` opcional (15 a 255 caracteres; padrão "Erro na emissao da nota"). No municipal são ignorados.
- `consultar_configuracao`: passa a devolver `ambiente` e o bloco `nacional`.
- `consultar_nota` e retornos de emissão: nota nacional traz `chave_acesso` e `pdf_url` com o link da Consulta Pública.
- `GET /api/notas/{id}/pdf`: nota nacional responde 307 para o link da Consulta Pública.
- `sincronizar_notas`: no nacional devolve erro "Sincronizacao disponivel so no ambiente municipal".
- Instruções do servidor MCP e descrições das ferramentas passam a citar os dois ambientes.
- UI: Configuração ganha seletor de ambiente, campos do bloco `nacional` e `c_trib_nac` por serviço; Emitir ganha o campo opcional de competência; Notas mostra o ambiente e abre o link oficial na nota nacional.

## Fluxo de emissão no nacional

1. Validação do payload e idempotência por `ref_externa`, iguais às de hoje.
2. Reserva do número da DPS no contador do ambiente (produção ou homologação).
3. Id da DPS: `"DPS"` + `c_loc_emi` (7) + tipo de inscrição (`2` para CNPJ, `1` para CPF) + inscrição federal (14, CPF com zeros à esquerda) + série (5) + número (15).
4. Montagem da DPS (namespace `http://www.sped.fazenda.gov.br/nfse`, sem prefixo, `versao="1.01"`):

| Campo | Valor |
|---|---|
| `tpAmb` | 1 em produção, 2 em homologação |
| `dhEmi` | agora, com fuso `-03:00` |
| `verAplic` | `nfse-<versao do sistema>` |
| `serie`, `nDPS` | da configuração e do contador |
| `dCompet` | competência informada ou hoje |
| `tpEmit` | 1 (prestador) |
| `cLocEmi` | `nacional.c_loc_emi` |
| `prest` | `CNPJ`; `IM` se `informar_im`; sem `xNome` e sem `end` (regras E0121 e E0128 para tpEmit 1); `regTrib` com `opSimpNac`, `regApTribSN` (só quando `opSimpNac` = 3) e `regEspTrib` |
| `toma` | `CPF` ou `CNPJ`, `xNome`, `email` se houver, `end` (endNac com cMun e CEP) se vier no payload |
| `serv` | `locPrest/cLocPrestacao`, `cServ` com `cTribNac`, `xDescServ` (descrição) e `cNBS` se configurado |
| `valores` | `vServPrest/vServ`; `trib/tribMun` com `tribISSQN` 1 e `tpRetISSQN` 1; sem `pAliq` (proibido para ME/EPP pelo Simples sem retenção, regras E0625 e E0631); `totTrib/pTotTribSN` |

5. Assinatura do `infDPS`, validação contra o XSD oficial, GZip + Base64, `POST /nfse`.
6. Resposta:
   - 201: nota `autorizada` com `chave_acesso` (Id da NFS-e sem o prefixo `NFS`), `numero_nfse` (`nNFSe`), XML enviado e XML da NFS-e. `codigo_verificacao` fica vazio (não existe no nacional).
   - 400 com `erros`: nota `erro` com a lista no formato de hoje (`codigo`, `descricao`, mais `complemento` quando vier).
   - Falha de rede ou HTTP 5xx: nota `erro`, mantendo `serie_dps` e `numero_dps`.
7. Nova tentativa da mesma `ref_externa` com nota em `erro`: reaproveita a série e o número da DPS. Antes de enviar, consulta `GET /dps/{id}`. Se a DPS já virou NFS-e, busca a nota em `GET /nfse/{chave}` e grava como `autorizada` (resultado `idempotente: true`). Se não virou, envia de novo com o mesmo número. Assim uma falha de rede no meio do envio nunca gera nota duplicada.
8. Modo teste ligado: o mesmo fluxo vai para a produção restrita, com `tpAmb` 2, contador de homologação e nota gravada com `ambiente = nacional_homologacao`. O retorno do MCP e da API sinaliza `teste: true`.

## Cancelamento no nacional

1. Só para nota `autorizada` com `chave_acesso`.
2. Pedido de registro de evento `e101101`: Id `"PRE"` + chave (50) + `101101`; `tpAmb` igual ao da nota; `dhEvento` agora; `CNPJAutor`; `chNFSe`; `xDesc` "Cancelamento de NFS-e"; `cMotivo` e `xMotivo`.
3. Assinatura do `infPedReg`, validação contra o XSD de evento, `POST /nfse/{chave}/eventos`.
4. 201: nota `cancelada`, XML do evento guardado em `xml_evento`. Erro: mensagem no formato de hoje. Prazo e limites são parametrizados pelo município (regras E0822 a E0824) e voltam como recusa.

Nota `municipal` continua cancelando pelo webservice de SP.

## Erros

| Situação | Comportamento |
|---|---|
| Configuração incompleta (`p_tot_trib_sn` vazio, serviço sem `c_trib_nac`, série fora da faixa) | `EmissaoInvalidaError` antes de reservar número |
| XML fora do XSD | `XSDValidationError`, nada é enviado |
| HTTP 400 ou 401 com mensagens | `PrefeituraRecusouError` com a lista de mensagens; texto do MCP passa a ser "Sistema Nacional recusou a emissao" (a chave `erros_prefeitura` se mantém para quem já integra) |
| HTTP 403 | Erro de certificado: "Sistema Nacional recusou o certificado (HTTP 403)" |
| Rede ou HTTP 5xx | `SefinIndisponivelError`, tratado como `PrefeituraIndisponivelError` hoje |

## Testes

Sem chamada real ao governo:

- DPS com dados fictícios (CNPJ `11222333000181`, CCM `12345678`) válida contra o XSD v1.01, para tomador CPF e CNPJ, com e sem endereço, com e sem IM.
- Id da DPS e do pedido de evento no tamanho e no padrão do XSD.
- Assinatura conferida com a chave pública do certificado de teste, sem prefixo de namespace.
- GZip + Base64 ida e volta.
- `SefinClient` com HTTP simulado: 201, 400 com erros, 403, rede, 5xx.
- Recuperação: falha de rede seguida de nova tentativa que encontra a DPS já convertida.
- Escolha do ambiente na emissão e no cancelamento; contadores separados.
- Migração do banco a partir de um SQLite com o esquema atual.
- Ferramentas MCP e rotas REST nos dois ambientes.
- Suíte atual do municipal sem alteração de comportamento.

Validação real, depois do deploy: modo teste ligado e ambiente nacional na UI, emissões na produção restrita até a DPS ser aceita, cancelamento na produção restrita, e só então emissão real com modo teste desligado.

## Achados da implementação

- O c14n de subárvore do lxml emite `xmlns=""` espúrio em filhos da Signature; a assinatura sairia inválida para qualquer verificador padrão. A canonicalização reparseia o elemento como documento isolado, e um teste com `signxml` (verificador independente) pega regressão.
- O padrão oficial de `TSSerieDPS` usa `^` e `$`, literais na sintaxe de XSD, e o libxml2 recusa toda série válida. A cópia local remove os dois caracteres (`backend/schemas/nacional/LEIAME.md`).
- Emissão nacional limitada a `op_simp_nac` = 3 (ME/EPP); MEI e não optante têm regras diferentes de valores e tributos e ficam de fora até alguém precisar.

## Riscos e pontos a confirmar na homologação

- Algoritmo da assinatura: bibliotecas abertas divergem (SHA-256 na maioria, SHA-1 em uma). O algoritmo fica numa constante; se a produção restrita recusar com E0714, troca-se para SHA-1.
- IM do prestador: só deve ir se houver registro complementar no CNC do município (regras do campo `prest/IM` no Anexo I). Controlado por `informar_im`.
- Convênio do município emissor ativo na produção restrita (regras E0037 e E1270).
- Campos JSON da API vieram de um espelho público do Swagger oficial; a produção restrita confirma.
- IBS/CBS para o Simples a partir de 01/01/2027: sem esse grupo a DPS deixa de atender a regra nessa data.
