"""Versioned SQL migrations.

Applies every ``backend/migrations/NNNN_name.sql`` file not yet recorded in the
``schema_migrations`` table. The whole run is one transaction guarded by an advisory
lock, so two concurrent runs cannot apply the same file twice.

Usage (from the repository root)::

    DATABASE_URL=postgresql+psycopg://... PYTHONPATH=backend/src python -m shared.database.migrate
"""

from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, text

from shared.config.settings import get_settings
from shared.database.engine import make_engine

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"
_FILE_PATTERN = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
_LOCK_KEY = 728311004  # advisory lock reserved for migrations
_CREATE_HISTORY = """
create table if not exists public.schema_migrations (
    version text primary key,
    name text not null,
    checksum text not null,
    applied_at timestamptz not null default now()
)
"""


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    sql: str
    checksum: str


def load_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    migrations: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        match = _FILE_PATTERN.match(path.name)
        if match is None:
            continue
        sql = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        migrations.append(Migration(match.group(1), path.name, sql, checksum))

    versions = [migration.version for migration in migrations]
    if len(versions) != len(set(versions)):
        raise ValueError("duplicate migration version in migrations directory")
    return migrations


def pending_migrations(migrations: list[Migration], applied: dict[str, str]) -> list[Migration]:
    """Return the migrations not yet applied. ``applied`` maps version -> checksum.

    Raises if an already-applied file was edited afterwards: applied migrations are
    immutable, so changes must go into a new file.
    """
    for migration in migrations:
        recorded = applied.get(migration.version)
        if recorded is not None and recorded != migration.checksum:
            raise ValueError(f"{migration.name} was modified after it was applied")
    return [m for m in migrations if m.version not in applied]


def migrate(engine: Engine, migrations: list[Migration] | None = None) -> list[str]:
    """Apply pending migrations and return their file names in application order."""
    if migrations is None:
        migrations = load_migrations()

    with engine.begin() as connection:
        connection.execute(text("select pg_advisory_xact_lock(:key)"), {"key": _LOCK_KEY})
        connection.exec_driver_sql(_CREATE_HISTORY)
        rows = connection.execute(text("select version, checksum from schema_migrations"))
        applied = {row.version: row.checksum for row in rows}

        todo = pending_migrations(migrations, applied)
        for migration in todo:
            connection.exec_driver_sql(migration.sql)
            connection.execute(
                text(
                    "insert into schema_migrations (version, name, checksum) "
                    "values (:version, :name, :checksum)"
                ),
                {
                    "version": migration.version,
                    "name": migration.name,
                    "checksum": migration.checksum,
                },
            )
    return [migration.name for migration in todo]


def main() -> int:
    engine = make_engine(get_settings().database_url)
    applied = migrate(engine)
    if applied:
        print("applied: " + ", ".join(applied))
    else:
        print("database is up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
