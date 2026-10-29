import pytest
from sqlalchemy import text

from shared.database.engine import make_engine


@pytest.mark.integration
def test_database_accepts_connections(database_url: str) -> None:
    engine = make_engine(database_url)

    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar() == 1
