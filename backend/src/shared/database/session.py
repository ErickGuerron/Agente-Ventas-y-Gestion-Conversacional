"""Database session generator for FastAPI dependency injection."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from shared.config.settings import get_settings
from shared.database.engine import make_engine

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = make_engine(settings.database_url)
    return _engine


def get_db_session() -> Generator[Session, None, None]:
    engine = get_engine()
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
