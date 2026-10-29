import pytest
from sqlalchemy import text

from shared.database.engine import make_engine
from shared.database.migrate import migrate


@pytest.mark.integration
def test_migrations_apply_once_and_are_idempotent(database_url: str) -> None:
    engine = make_engine(database_url)

    migrate(engine)
    second_run = migrate(engine)

    assert second_run == []
    with engine.connect() as connection:
        tables = (
            connection.execute(
                text(
                    "select table_name from information_schema.tables "
                    "where table_schema = 'public' and table_name = 'conversations'"
                )
            )
            .scalars()
            .all()
        )
    assert tables == ["conversations"]
