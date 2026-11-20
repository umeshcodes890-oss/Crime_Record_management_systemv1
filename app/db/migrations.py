"""Versioned schema migrations.

sql/schema.sql stays the frozen v1 baseline so a fresh install still
reproduces byte-for-byte. Everything added since then lives in
sql/migrations/NNN_*.sql and is applied here, in filename order, once
each.

The ledger table schema_migrations records the filename and a SHA-256 of
its contents. A file that changes after being applied is therefore
detectable: silently editing an applied migration is how a developer's
database and a colleague's stop agreeing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.db.connection import Database, PROJECT_ROOT

MIGRATIONS_DIR = PROJECT_ROOT / "sql" / "migrations"
LEDGER_TABLE = "schema_migrations"

# Migration 000 creates the ledger and the DDL helpers, so it has to be
# applied before the ledger can be read.
HELPER_FILE = "000_migration_helpers.sql"


class MigrationError(RuntimeError):
    """A migration could not be planned or applied."""


def split_statements(script: str) -> list[str]:
    """Split a SQL script into individual statements, honouring DELIMITER."""
    statements: list[str] = []
    delimiter = ";"
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        text = "\n".join(buffer).strip()
        buffer = []
        if text:
            statements.append(text)

    for raw_line in script.splitlines():
        stripped = raw_line.strip()

        if stripped.upper().startswith("DELIMITER "):
            flush()
            delimiter = stripped.split(None, 1)[1].strip()
            continue

        if not stripped or stripped.startswith("--"):
            continue

        buffer.append(raw_line)
        if stripped.endswith(delimiter):
            buffer[-1] = stripped[: -len(delimiter)].rstrip()
            flush()

    flush()
    return statements


def migration_files(directory: Path | None = None) -> list[Path]:
    """Every migration script, in the order they must be applied."""
    directory = directory or MIGRATIONS_DIR
    if not directory.is_dir():
        raise MigrationError(f"No migrations directory at {directory}")
    return sorted(directory.glob("*.sql"), key=lambda path: path.name)


def checksum(path: Path) -> str:
    """SHA-256 of a script's text, normalised so line endings do not matter."""
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def applied(db: Database) -> dict[str, str]:
    """Filename -> checksum, for every migration already in this database."""
    if not db.query_one(
        """
        SELECT TABLE_NAME FROM information_schema.TABLES
         WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        """,
        (LEDGER_TABLE,),
    ):
        return {}
    return {row["filename"]: row["checksum"]
            for row in db.query(f"SELECT filename, checksum FROM {LEDGER_TABLE}")}


@dataclass
class MigrationPlan:
    filename: str
    state: str  # pending | applied | drift
    detail: str = ""


def plan(db: Database) -> list[MigrationPlan]:
    """Classify every migration file against this database's ledger."""
    ledger = applied(db)
    entries: list[MigrationPlan] = []
    for path in migration_files():
        recorded = ledger.get(path.name)
        if recorded is None:
            entries.append(MigrationPlan(path.name, "pending"))
        elif recorded != checksum(path):
            entries.append(MigrationPlan(
                path.name, "drift",
                "file changed after it was applied to this database"))
        else:
            entries.append(MigrationPlan(path.name, "applied"))
    return entries


def apply_statement(db: Database, statement: str) -> None:
    try:
        db.ddl(statement)
    except Exception as exc:  # noqa: BLE001 - re-raised with the statement that failed
        raise MigrationError(f"{exc}\n  while running: {one_line(statement)}") from exc


def one_line(statement: str, limit: int = 160) -> str:
    collapsed = " ".join(statement.split())
    return collapsed if len(collapsed) <= limit else collapsed[:limit] + " ..."


def apply_file(db: Database, path: Path) -> int:
    """Run one migration script and record it in the ledger."""
    statements = split_statements(path.read_text(encoding="utf-8"))
    for statement in statements:
        apply_statement(db, statement)
    db.execute(
        f"""
        INSERT INTO {LEDGER_TABLE} (filename, checksum)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE checksum = VALUES(checksum)
        """,
        (path.name, checksum(path)),
    )
    return len(statements)


def migrate(db: Database, log: Callable[[str], None] = print) -> int:
    """Apply every pending migration. Returns how many were applied."""
    entries = plan(db)

    drifted = [entry for entry in entries if entry.state == "drift"]
    if drifted:
        names = ", ".join(entry.filename for entry in drifted)
        raise MigrationError(
            f"Migration file(s) changed after being applied: {names}.\n"
            "Revert the edit, or add a new migration file instead of rewriting history."
        )

    pending = [entry for entry in entries if entry.state == "pending"]
    if not pending:
        log("Database is up to date; nothing to apply.")
        return 0

    to_apply = len(pending)
    by_name = {path.name: path for path in migration_files()}

    # 000 holds the ledger table and the DDL helpers the rest depend on.
    if any(entry.filename == HELPER_FILE for entry in pending):
        count = apply_file(db, by_name[HELPER_FILE])
        log(f"  ok  {HELPER_FILE:<34} {count} statements")
        pending = [entry for entry in pending if entry.filename != HELPER_FILE]
    elif not applied(db):
        raise MigrationError(f"{HELPER_FILE} has not been applied and is not pending.")

    for entry in pending:
        count = apply_file(db, by_name[entry.filename])
        log(f"  ok  {entry.filename:<34} {count} statements")

    return to_apply


def status(db: Database) -> list[MigrationPlan]:
    """Classify every migration file against this database."""
    return plan(db)
