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
    from app.models import nota, config_store  # noqa: F401
    Base.metadata.create_all(get_engine())


def reset_engine_para_testes():
    """Descarta engine/sessao cacheados (usado nos testes com DATA_DIR temporario)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
