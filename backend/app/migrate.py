"""Tiny additive migration for SQLite databases created by an earlier version of the app.

`Base.metadata.create_all` creates missing TABLES but never adds new COLUMNS to existing ones. This adds any
column the models define that the live table lacks (nullable, or NOT NULL with a scalar default), so upgrading
needs no manual SQL and loses no data. It never drops, renames or retypes anything.
"""
import logging

from sqlalchemy.engine import Engine

from .database import Base

log = logging.getLogger(__name__)


def _sql_default(value) -> str:
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def add_missing_columns(engine: Engine) -> list[str]:
    if engine.dialect.name != "sqlite":
        return []  # use a real migration tool (Alembic) for other databases
    added: list[str] = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {row[1] for row in conn.exec_driver_sql(f'PRAGMA table_info("{table.name}")')}
            if not existing:
                continue  # table does not exist yet; create_all will build it whole
            for col in table.columns:
                if col.name in existing or col.primary_key:
                    continue
                default = ""
                if col.default is not None and getattr(col.default, "is_scalar", False):
                    default = f" DEFAULT {_sql_default(col.default.arg)}"
                if not col.nullable and not default:
                    log.warning("cannot auto-add NOT NULL column %s.%s without a default", table.name, col.name)
                    continue
                null = " NOT NULL" if not col.nullable else ""
                conn.exec_driver_sql(
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col.type.compile(engine.dialect)}{null}{default}'
                )
                added.append(f"{table.name}.{col.name}")
    if added:
        log.info("migrated database, added columns: %s", ", ".join(added))
    return added
