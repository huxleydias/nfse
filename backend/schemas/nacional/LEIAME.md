# Schemas do Sistema Nacional NFS-e

Duas pastas, uma por leiaute. O sistema escolhe a pasta pelo leiaute vigente no ambiente de destino (`leiaute_vigente` em `app/nfse/nacional/__init__.py`).

| Pasta | Leiaute | Onde vale | Origem |
|---|---|---|---|
| `1.01/` | NT 004 (+ NT 007) | Produção até 30/11/2026 | `nfse-esquemas_xsd-v1-01-20260209.zip`, em https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual |
| `1.01-nt009/` | NT 009 release 1 | Produção restrita desde 20/10/2026; produção a partir de 01/12/2026 | `esquemas_prod_restrita_20261020.zip`, em https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/producao-restrita |

Para atualizar: substituir a pasta do leiaute inteira pela versão nova, reaplicar o ajuste abaixo quando o padrão antigo voltar e rodar a suíte. Os releases 2 e 3 da NT 009 chegam primeiro na produção restrita: quando o governo publicar um zip novo nessa página, ele substitui `1.01-nt009/`.

Diferenças que afetam a DPS montada aqui: na NT 009 o `finNFSe` (0, NFS-e regular) é obrigatório em `infDPS`, logo depois de `tpEmit`, e em `cServ` o `xDescServ` vai para o fim (depois de `cNBS` e `cIntContrib`). Na NT 004 não há `finNFSe` nesse ponto e `xDescServ` vem antes de `cNBS`; trocar a ordem dá E1235.

Quando a NT 009 estiver em produção e a pasta `1.01/` não for mais usada, ela pode ser removida junto com `LEIAUTE_NT004`.

## Ajuste local (só em `1.01/`)

`tiposSimples_v1.01.xsd`, tipo `TSSerieDPS`: o padrão oficial é `^0{0,4}\d{1,5}$`. Na sintaxe de expressão regular do XSD, `^` e `$` são caracteres literais, não âncoras, e o libxml2 recusa toda série válida (`00001` exige os caracteres `^` e `$` na string). O validador do Sistema Nacional trata como âncora. A cópia local usa `0{0,4}\d{1,5}`, que é o mesmo padrão sem os caracteres literais, com um comentário no próprio arquivo.

Em `1.01-nt009/` o governo trocou o padrão por `[0-9]{1,4}|[0-8][0-9]{4}`, sem os caracteres literais, e os arquivos ficam como vieram.
