"""Database engine factory. Repositories receive the engine; they never build their own."""

from sqlalchemy import Engine, create_engine


def make_engine(database_url: str) -> Engine:
    if not database_url:
        raise ValueError("DATABASE_URL is not set")
    return create_engine(database_url, pool_pre_ping=True)
