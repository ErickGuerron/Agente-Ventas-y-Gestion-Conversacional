"""Database engine factory. Repositories receive the engine; they never build their own."""

from sqlalchemy import Engine, create_engine


def make_engine(database_url: str) -> Engine:
    if not database_url:
        raise ValueError("DATABASE_URL is not set")

    connect_args = {}
    # Supabase / PgBouncer transaction poolers require disabling prepared statements
    if "pooler.supabase.com" in database_url or ":6543" in database_url:
        connect_args["prepare_threshold"] = None

    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
