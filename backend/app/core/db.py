"""Engine SQLite e sessao. Banco vive no volume persistente (DATA_DIR)."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .settings import data_dir


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        url = f"sqlite:///{data_dir() / 'nfse.db'}"
        _engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(_engine, "connect")
        def _fk_on(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")

    return _engine


def get_session():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal()


def init_db():
    from app.models import api_key, config_store, nota  # noqa: F401
    Base.metadata.create_all(get_engine())
    _adicionar_colunas_novas(get_engine())


def _adicionar_colunas_novas(engine) -> None:
    """create_all nao altera tabela existente: coluna nova em modelo antigo
    entra aqui com ALTER TABLE ADD COLUMN. Nada e apagado ou reescrito, e o
    server_default preenche as linhas que ja existiam."""
    with engine.begin() as conn:
        for tabela in Base.metadata.sorted_tables:
            existentes = {
                linha[1]
                for linha in conn.exec_driver_sql(f"PRAGMA table_info({tabela.name})")
            }
            for coluna in tabela.columns:
                if coluna.name in existentes:
                    continue
                tipo = coluna.type.compile(dialect=engine.dialect)
                ddl = f"ALTER TABLE {tabela.name} ADD COLUMN {coluna.name} {tipo}"
                padrao = coluna.server_default
                if padrao is not None:
                    ddl += f" NOT NULL DEFAULT '{padrao.arg}'"
                conn.exec_driver_sql(ddl)


def reset_engine_para_testes():
    """Descarta engine/sessao cacheados (usado nos testes com DATA_DIR temporario)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
