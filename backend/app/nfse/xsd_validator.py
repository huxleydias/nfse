"""Validacao local dos XMLs contra os XSDs oficiais da prefeitura (v02-5).

Roda ANTES de enviar ao webservice: campo faltando ou formato errado vira
erro claro aqui, nunca chega na prefeitura.
"""
from functools import lru_cache
from pathlib import Path

from lxml import etree

SCHEMAS_DIR = Path(__file__).resolve().parent.parent.parent / "schemas"


class XSDValidationError(Exception):
    def __init__(self, erros: list[str]):
        self.erros = erros
        super().__init__("; ".join(erros))


@lru_cache(maxsize=None)
def _schema(nome: str) -> etree.XMLSchema:
    caminho = SCHEMAS_DIR / nome
    return etree.XMLSchema(etree.parse(str(caminho)))


def validar(root: etree._Element, schema_name: str) -> None:
    """Valida o elemento contra o XSD. Levanta XSDValidationError se invalido."""
    schema = _schema(schema_name)
    if not schema.validate(root):
        erros = [
            f"linha {e.line}: {e.message}" for e in schema.error_log
        ]
        raise XSDValidationError(erros)
