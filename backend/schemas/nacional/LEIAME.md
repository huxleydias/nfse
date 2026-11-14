# Schemas do Sistema Nacional NFS-e

Pasta `1.01/`: cópia dos esquemas oficiais v1.01 de 09/02/2026 (`nfse-esquemas_xsd-v1-01-20260209.zip`), baixados em
https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual

Para atualizar: substituir a pasta inteira pela versão nova, reaplicar o ajuste abaixo e rodar a suíte.

## Ajuste local

`tiposSimples_v1.01.xsd`, tipo `TSSerieDPS`: o padrão oficial é `^0{0,4}\d{1,5}$`. Na sintaxe de expressão regular do XSD, `^` e `$` são caracteres literais, não âncoras, e o libxml2 recusa toda série válida (`00001` exige os caracteres `^` e `$` na string). O validador do Sistema Nacional trata como âncora. A cópia local usa `0{0,4}\d{1,5}`, que é o mesmo padrão sem os caracteres literais, com um comentário no próprio arquivo.
