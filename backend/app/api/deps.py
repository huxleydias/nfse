"""Dependencies compartilhadas das rotas."""
from app.core.db import get_session


def db_session():
    session = get_session()
    try:
        yield session
    finally:
        session.close()
