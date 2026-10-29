from pathlib import Path

import pytest

from shared.database.migrate import (
    Migration,
    load_migrations,
    pending_migrations,
)


def _write(directory: Path, name: str, sql: str) -> None:
    (directory / name).write_text(sql, encoding="utf-8")


def test_load_migrations_orders_by_version_and_ignores_other_files(tmp_path: Path) -> None:
    _write(tmp_path, "0002_second.sql", "select 2;")
    _write(tmp_path, "0001_first.sql", "select 1;")
    _write(tmp_path, "notes.md", "not a migration")
    _write(tmp_path, "bad-name.sql", "select 0;")

    migrations = load_migrations(tmp_path)

    assert [m.name for m in migrations] == ["0001_first.sql", "0002_second.sql"]
    assert migrations[0].checksum != migrations[1].checksum


def test_load_migrations_rejects_duplicate_versions(tmp_path: Path) -> None:
    _write(tmp_path, "0001_a.sql", "select 1;")
    _write(tmp_path, "0001_b.sql", "select 2;")

    with pytest.raises(ValueError, match="duplicate"):
        load_migrations(tmp_path)


def test_pending_skips_applied_and_keeps_order() -> None:
    first = Migration("0001", "0001_first.sql", "select 1;", "aaa")
    second = Migration("0002", "0002_second.sql", "select 2;", "bbb")

    todo = pending_migrations([first, second], applied={"0001": "aaa"})

    assert todo == [second]


def test_pending_rejects_applied_migration_that_changed() -> None:
    first = Migration("0001", "0001_first.sql", "select 1; -- edited", "changed")

    with pytest.raises(ValueError, match="modified after it was applied"):
        pending_migrations([first], applied={"0001": "original"})


def test_real_migrations_directory_is_loadable() -> None:
    migrations = load_migrations()

    assert migrations, "backend/migrations must contain at least 0001_init.sql"
    assert migrations[0].version == "0001"
