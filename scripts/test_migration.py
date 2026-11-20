"""Prove the migrations work on a COPY of the live database.

    python scripts\\test_migration.py
    python scripts\\test_migration.py --keep

Nothing here writes to the database named in config.ini. The script
creates a scratch schema called <live>_migtest, clones the live tables
and rows into it, applies every migration, and then checks four things:

  1. no existing row was lost or altered,
  2. the new structures exist and were backfilled correctly,
  3. re-applying the same migrations changes nothing, and
  4. v1 behaviour is intact, by running scripts/selftest.py against the
     migrated copy.

The scratch schema is dropped when everything passes and kept when
something fails, so there is something left to inspect.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import mysql.connector

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.connection import Database, load_config  # noqa: E402
from app.db.migrations import (  # noqa: E402
    MIGRATIONS_DIR,
    MigrationError,
    checksum,
    migrate,
    plan,
    split_statements,
)
from app.db.repositories import Repositories  # noqa: E402

SELFTEST = PROJECT_ROOT / "scripts" / "selftest.py"

# Views, procedures and triggers are recreated from source rather than
# from SHOW CREATE output; those files are schema agnostic.
CLONED_ROUTINE_FILES = ("views.sql", "procedures.sql", "triggers.sql")

# The migration runner's own bookkeeping. It is rebuilt in the copy
# instead of copied, so that the migrations really run against the copy.
LEDGER_TABLE = "schema_migrations"

NEW_TABLES = [
    "victim_medical_records", "victim_contacts", "victim_compensation",
    "witness_statements", "witness_interviews", "witness_protection",
    "evidence_attachments", "evidence_custody_log", "forensic_examinations",
    "evidence_sequences", "audit_log", "schema_migrations",
]

NEW_TRIGGERS = [
    "trg_evidence_before_insert", "trg_evidence_before_custody",
    "trg_custody_log_before_update", "trg_custody_log_before_delete",
    "trg_audit_log_before_update", "trg_audit_log_before_delete",
]

PASSED = 0
FAILED = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok   {label}")
    else:
        FAILED += 1
        print(f"  FAIL {label}{(' - ' + detail) if detail else ''}")


def quote(name: str) -> str:
    return f"`{name}`"


def current_schema(cur) -> str:
    cur.execute("SELECT DATABASE()")
    return cur.fetchone()[0]


def table_names(cur, schema: str, kind: str = "BASE TABLE") -> list[str]:
    cur.execute(
        """
        SELECT TABLE_NAME FROM information_schema.TABLES
         WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = %s ORDER BY TABLE_NAME
        """,
        (schema, kind),
    )
    return [row[0] for row in cur.fetchall()]


def column_names(cur, schema: str, table: str) -> list[str]:
    cur.execute(
        """
        SELECT COLUMN_NAME FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
         ORDER BY ORDINAL_POSITION
        """,
        (schema, table),
    )
    return [row[0] for row in cur.fetchall()]


def primary_key(cur, schema: str, table: str) -> str | None:
    cur.execute(
        """
        SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE
         WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND CONSTRAINT_NAME = 'PRIMARY'
         ORDER BY ORDINAL_POSITION LIMIT 1
        """,
        (schema, table),
    )
    row = cur.fetchone()
    return row[0] if row else None


def all_rows(cur, schema: str, table: str, columns: list[str]) -> list[tuple]:
    order = primary_key(cur, schema, table)
    projection = ", ".join(quote(column) for column in columns)
    sql = f"SELECT {projection} FROM {quote(schema)}.{quote(table)}"
    if order:
        sql += f" ORDER BY {quote(order)}"
    cur.execute(sql)
    return list(cur.fetchall())


def row_count(cur, schema: str, table: str) -> int:
    cur.execute(f"SELECT COUNT(*) FROM {quote(schema)}.{quote(table)}")
    return cur.fetchone()[0]


def scalar(cur, sql: str, params=None):
    cur.execute(sql, tuple(params) if params else ())
    row = cur.fetchone()
    return row[0] if row else None


def refuses(cur, sql: str, params=None) -> str | None:
    """Run a statement expected to be rejected; return its error text."""
    try:
        cur.execute(sql, tuple(params) if params else ())
    except mysql.connector.Error as exc:
        return str(exc)
    return None


# ----------------------------------------------------------------------
# clone and snapshot
# ----------------------------------------------------------------------
def copyable_columns(cur, schema: str, table: str) -> list[str]:
    """The columns of a table that a row can be written to.

    Only a real generated column is left out. MySQL spells the default
    of a ``TIMESTAMP DEFAULT CURRENT_TIMESTAMP`` column as
    ``DEFAULT_GENERATED`` in ``EXTRA``, so matching on that word would
    drop ``created_at`` from the copy and let it take today's date;
    ``GENERATION_EXPRESSION`` is set only for a column the server derives.
    Leaving those out is what lets the copy recompute them.
    """
    cur.execute(
        """
        SELECT COLUMN_NAME FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
           AND IFNULL(GENERATION_EXPRESSION, '') = ''
         ORDER BY ORDINAL_POSITION
        """,
        (schema, table),
    )
    return [row[0] for row in cur.fetchall()]


def clone_schema(cur, src: str) -> list[str]:
    """Copy every table and its rows, then recreate the routines.

    The migration ledger is not copied. The point of the run is to apply
    the migrations to the copy and see what happens, and a ledger that
    says they are already applied would leave the copy without the v2
    triggers and procedures it is meant to be checked for.
    """
    tables = [table for table in table_names(cur, src) if table != LEDGER_TABLE]
    for table in tables:
        cur.execute(f"SHOW CREATE TABLE {quote(src)}.{quote(table)}")
        cur.execute(cur.fetchone()[1])
        columns = ", ".join(quote(column) for column in copyable_columns(cur, src, table))
        cur.execute(
            f"INSERT INTO {quote(table)} ({columns})"
            f" SELECT {columns} FROM {quote(src)}.{quote(table)}"
        )

    # Recreating the triggers after the rows are copied matters: v1's
    # trg_cases_before_insert would otherwise renumber every cloned case.
    for name in CLONED_ROUTINE_FILES:
        path = PROJECT_ROOT / "sql" / name
        for statement in split_statements(path.read_text(encoding="utf-8")):
            cur.execute(statement)
    return tables


def snapshot(cur, schema: str, tables: list[str]) -> dict[str, tuple[list[str], list[tuple]]]:
    """The v1 columns and every row of every table, taken before migrating."""
    captured = {}
    for table in tables:
        columns = column_names(cur, schema, table)
        captured[table] = (columns, all_rows(cur, schema, table, columns))
    return captured


def verify_preserved(cur, before) -> None:
    print("\nExisting records survive unchanged")
    dst = current_schema(cur)
    for table, (columns, rows) in sorted(before.items()):
        live_columns = column_names(cur, dst, table)
        missing = [column for column in columns if column not in live_columns]
        if missing:
            check(f"{table}: v1 columns still present", False, str(missing))
            continue
        after = all_rows(cur, dst, table, columns)
        check(f"{table}: {len(rows)} row(s) identical to the live data",
              after == rows, f"copy holds {len(after)} row(s)")


# ----------------------------------------------------------------------
# assertions
# ----------------------------------------------------------------------
def check_objects(cur) -> None:
    print("\nNew structures")
    schema = current_schema(cur)
    tables = set(table_names(cur, schema))
    for name in NEW_TABLES:
        check(f"table {name}", name in tables)

    triggers = {row[0] for row in _fetch(
        cur, "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = %s",
        (schema,))}
    for name in NEW_TRIGGERS:
        check(f"trigger {name}", name in triggers)
    for name in ("trg_evidence_after_insert",):
        check(f"broken trigger {name} is gone", name not in triggers)

    routines = {row[0] for row in _fetch(
        cur, "SELECT ROUTINE_NAME FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA = %s",
        (schema,))}
    for name in ("sp_add_column", "sp_modify_column", "sp_add_index"):
        check(f"ddl helper {name}", name in routines)


def _fetch(cur, sql, params=None):
    cur.execute(sql, tuple(params) if params else ())
    return cur.fetchall()


def check_ledger(db: Database) -> None:
    print("\nMigration ledger")
    entries = plan(db)
    not_applied = [f"{entry.filename}:{entry.state}" for entry in entries
                   if entry.state != "applied"]
    check("every migration file is recorded as applied", not not_applied, ", ".join(not_applied))

    rows = db.query("SELECT filename, checksum FROM schema_migrations")
    stale = [row["filename"] for row in rows
             if (MIGRATIONS_DIR / row["filename"]).exists()
             and row["checksum"] != checksum(MIGRATIONS_DIR / row["filename"])]
    check("stored checksums match the files on disk", not stale, ", ".join(stale))
    check("the ledger has one row per migration file",
          len(rows) == len(list(MIGRATIONS_DIR.glob("*.sql"))), f"{len(rows)} rows")


def check_backfills(cur) -> None:
    print("\nBackfill")
    with_statements = scalar(cur,
        "SELECT COUNT(*) FROM witnesses WHERE statement IS NOT NULL AND TRIM(statement) <> ''")
    seeded = scalar(cur, "SELECT COUNT(*) FROM witness_statements WHERE version = 1")
    check("one version 1 statement for each witness that had text",
          with_statements == seeded, f"{with_statements} witnesses, {seeded} statements")

    mismatched = scalar(cur, """
        SELECT COUNT(*) FROM witness_statements s
          JOIN witnesses w ON w.witness_id = s.witness_id
         WHERE s.version = 1 AND NOT (s.statement_body <=> w.statement)
    """)
    check("backfilled text matches the original column", mismatched == 0, str(mismatched))

    blank = scalar(cur,
        "SELECT COUNT(*) FROM evidence WHERE evidence_ref IS NULL OR evidence_ref = ''")
    check("every existing item was given a reference", blank == 0, str(blank))

    dupes = scalar(cur, """
        SELECT COUNT(*) FROM (
            SELECT evidence_ref FROM evidence GROUP BY evidence_ref HAVING COUNT(*) > 1
        ) x
    """)
    check("references are unique", dupes == 0, str(dupes))

    malformed = scalar(cur,
        "SELECT COUNT(*) FROM evidence WHERE evidence_ref NOT REGEXP '^EV/[0-9]{4}/[0-9]{6}$'")
    check("references follow EV/YYYY/NNNNNN", malformed == 0, str(malformed))

    untracked = scalar(cur, """
        SELECT COUNT(*) FROM evidence e
         WHERE NOT EXISTS (SELECT 1 FROM evidence_custody_log l WHERE l.evidence_id = e.evidence_id)
    """)
    check("every existing item has an opening custody entry", untracked == 0, str(untracked))

    wrong_open = scalar(cur, """
        SELECT COUNT(*) FROM evidence_custody_log WHERE sequence_no = 1 AND event_type <> 'collected'
    """)
    check("the opening entry is the collection event", wrong_open == 0, str(wrong_open))

    counter = scalar(cur, """
        SELECT COUNT(*) FROM evidence_sequences s
         WHERE s.last_seq < COALESCE((
             SELECT MAX(CAST(SUBSTRING_INDEX(e.evidence_ref, '/', -1) AS UNSIGNED))
               FROM evidence e
              WHERE SUBSTRING_INDEX(SUBSTRING_INDEX(e.evidence_ref, '/', 2), '/', -1) = s.yr), 0)
    """)
    check("the reference counter is ahead of every number already issued",
          counter == 0, str(counter))


def check_no_orphans(cur) -> None:
    print("\nReferential integrity")
    pairs = [
        ("victim_medical_records", "victim_id", "victims"),
        ("victim_contacts", "victim_id", "victims"),
        ("victim_compensation", "victim_id", "victims"),
        ("witness_statements", "witness_id", "witnesses"),
        ("witness_interviews", "witness_id", "witnesses"),
        ("witness_protection", "witness_id", "witnesses"),
        ("evidence_attachments", "evidence_id", "evidence"),
        ("evidence_custody_log", "evidence_id", "evidence"),
        ("forensic_examinations", "evidence_id", "evidence"),
    ]
    for child, column, parent in pairs:
        orphans = scalar(cur, f"""
            SELECT COUNT(*) FROM {quote(child)} c
             WHERE NOT EXISTS (SELECT 1 FROM {quote(parent)} p
                                WHERE p.{quote(column)} = c.{quote(column)})
        """)
        check(f"every {child} row points at a real parent", orphans == 0, str(orphans))


def check_statement_versions(cur) -> None:
    """Version history: one current version, older ones never rewritten."""
    print("\nStatement versioning")
    case_id = scalar(cur, "SELECT case_id FROM crime_cases ORDER BY case_id LIMIT 1")
    admin = scalar(cur, "SELECT user_id FROM users WHERE role = 'admin' ORDER BY user_id LIMIT 1")
    if not case_id or not admin:
        check("a case exists to hang a test witness on", False,
              "the live database has no cases to copy")
        return

    cur.execute("INSERT INTO witnesses (case_id, name) VALUES (%s, 'Version Probe')", (case_id,))
    witness_id = cur.lastrowid
    try:
        def insert(version: int, body: str) -> str | None:
            return refuses(cur, """
                INSERT INTO witness_statements
                    (witness_id, version, statement_body, recorded_by_user_id, recorded_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (witness_id, version, body, admin))

        check("the first version is accepted", insert(1, "First account") is None)
        check("a second current version is refused", insert(2, "A competing account") is not None)

        cur.execute("UPDATE witness_statements SET superseded_at = NOW() WHERE witness_id = %s AND version = 1",
                    (witness_id,))
        error = insert(2, "Superseding account")
        check("a new version is accepted once the old one is superseded", error is None, str(error))
        if error is None:
            check("exactly one version is current",
                  scalar(cur, "SELECT COUNT(*) FROM witness_statements "
                              "WHERE witness_id = %s AND superseded_at IS NULL", (witness_id,)) == 1)
            check("the earlier version is still stored",
                  scalar(cur, "SELECT COUNT(*) FROM witness_statements WHERE witness_id = %s",
                         (witness_id,)) == 2)
        check("a repeated version number is refused", insert(2, "Duplicate number") is not None)
    finally:
        cur.execute("DELETE FROM witnesses WHERE witness_id = %s", (witness_id,))


def check_evidence_lifecycle(cur, db: Database) -> None:
    """References, the append-only guards, and deleting a case that has them.

    MySQL documents that foreign key actions do not activate triggers. The
    point of testing on a copy is not to take that on trust: if a cascade
    did fire the append-only guards, deleting a case with evidence would
    break a feature that works today.
    """
    print("\nEvidence lifecycle, guards and cascades")
    admin_row = next((user for user in Repositories(db).users.list_all() if user["role"] == "admin"), None)
    stations = Repositories(db).stations.list_all()
    officers = Repositories(db).officers.options()
    sections = Repositories(db).offences.options()
    if not (admin_row and stations and officers and len(sections) > 1):
        check("reference data available for the probe", False,
              "the live database has no admin, station, officer or section to use")
        return

    actor = {"user_id": admin_row["user_id"], "username": admin_row["username"], "role": "admin"}
    repos = Repositories(db, actor)
    filed = repos.cases.file_case(
        station_id=stations[0]["station_id"],
        officer_id=officers[0]["officer_id"],
        user_id=admin_row["user_id"],
        category="theft",
        offence_type="Migration probe",
        occurrence_datetime="2026-01-15 10:30:00",
        reporting_datetime="2026-01-15 14:00:00",
        place_of_occurrence="Probe address",
        description="Created by the migration test and deleted again.",
        section_ids=[sections[0]["section_id"], sections[1]["section_id"]],
    )
    case_id = filed["case_id"]
    cleaned = False
    try:
        refs = []
        for label in ("First probe item", "Second probe item"):
            cur.execute(
                """
                INSERT INTO evidence (case_id, type, description, collected_by_officer_id,
                                      collected_datetime)
                VALUES (%s, 'physical', %s, %s, NOW())
                """,
                (case_id, label, officers[0]["officer_id"]),
            )
            refs.append((cur.lastrowid,
                         scalar(cur, "SELECT evidence_ref FROM evidence WHERE evidence_id = %s",
                                (cur.lastrowid,))))
        check("the trigger assigns a reference on insert",
              all(ref for _, ref in refs), str(refs))
        check("consecutive items get different references",
              len({ref for _, ref in refs}) == len(refs), str([ref for _, ref in refs]))

        evidence_id = refs[0][0]
        cur.execute(
            """
            INSERT INTO evidence_custody_log (evidence_id, sequence_no, event_type,
                                              occurred_at, recorded_by_user_id)
            VALUES (%s, 1, 'collected', NOW(), %s)
            """,
            (evidence_id, admin_row["user_id"]),
        )
        cur.execute(
            "INSERT INTO audit_log (entity, entity_id, case_id, action, changed_by_user_id, "
            "username_snapshot) VALUES ('evidence', %s, %s, 'create', %s, %s)",
            (evidence_id, case_id, admin_row["user_id"], admin_row["username"]),
        )

        error = refuses(cur, "UPDATE evidence_custody_log SET remarks = 'edited' WHERE evidence_id = %s",
                        (evidence_id,))
        check("custody history cannot be edited", error is not None and "append-only" in error, str(error))
        error = refuses(cur, "DELETE FROM evidence_custody_log WHERE evidence_id = %s", (evidence_id,))
        check("custody history cannot be deleted", error is not None and "append-only" in error, str(error))
        error = refuses(cur, "UPDATE audit_log SET summary = 'rewritten' WHERE entity_id = %s",
                        (evidence_id,))
        check("audit entries cannot be edited", error is not None and "append-only" in error, str(error))
        error = refuses(cur, "DELETE FROM audit_log WHERE entity_id = %s", (evidence_id,))
        check("audit entries cannot be deleted", error is not None and "append-only" in error, str(error))

        error = refuses(cur, "DELETE FROM crime_cases WHERE case_id = %s", (case_id,))
        cascade_ok = error is None
        check("a case with custody history can still be deleted", cascade_ok, str(error))
        if cascade_ok:
            check("cascading deletes are not blocked by the append-only guards",
                  scalar(cur, "SELECT COUNT(*) FROM evidence_custody_log WHERE evidence_id = %s",
                         (evidence_id,)) == 0,
                  scalar(cur, "SELECT COUNT(*) FROM evidence_custody_log WHERE evidence_id = %s",
                         (evidence_id,)))
            survived = scalar(cur,
                "SELECT COUNT(*) FROM audit_log WHERE entity = 'evidence' AND entity_id = %s",
                (evidence_id,))
            check("audit history outlives the record it describes",
                  survived == 1, f"{survived} row(s) left")
            still_linked = scalar(cur,
                "SELECT COUNT(*) FROM audit_log WHERE entity = 'evidence' AND entity_id = %s "
                "AND case_id IS NOT NULL",
                (evidence_id,))
            check("the audit row's case reference was nulled, not blocked",
                  still_linked == 0, f"{still_linked} row(s) still point at a deleted case")
            cleaned = True
        else:
            # The guards got in the way of an existing feature. Report it
            # above, then clear the probe rows so the rest of the run is
            # not poisoned by leftover data.
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            for name in ("trg_custody_log_before_delete", "trg_audit_log_before_delete"):
                cur.execute(f"DROP TRIGGER IF EXISTS {quote(name)}")
            cur.execute("DELETE FROM audit_log WHERE case_id = %s OR entity_id IN (%s)",
                        (case_id, evidence_id))
            cur.execute("DELETE FROM evidence_custody_log WHERE evidence_id = %s", (evidence_id,))
            cur.execute("DELETE FROM evidence WHERE case_id = %s", (case_id,))
            cur.execute("DELETE FROM crime_cases WHERE case_id = %s", (case_id,))
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")
            for statement in split_statements(
                    (MIGRATIONS_DIR / "003_evidence_management.sql").read_text(encoding="utf-8")):
                if "CREATE TRIGGER" in statement:
                    cur.execute(statement)
            for statement in split_statements(
                    (MIGRATIONS_DIR / "004_audit_logging.sql").read_text(encoding="utf-8")):
                if "CREATE TRIGGER" in statement:
                    cur.execute(statement)
            cleaned = True
    finally:
        if not cleaned:
            try:
                repos.cases.delete(case_id)
            except Exception as exc:  # noqa: BLE001 - cleanup must not hide the real failure
                print(f"       (could not remove probe case {case_id}: {exc})")


def check_idempotent(cur, db: Database, before) -> None:
    """Apply every migration a second time over an already migrated copy."""
    print("\nRe-running every migration")
    schema = current_schema(cur)
    counts = {table: row_count(cur, schema, table)
              for table in table_names(cur, schema) if table != "schema_migrations"}
    # Measured here, not from the pre-migration snapshot: the probes above
    # file and delete a case of their own, which legitimately advances the
    # case number counter.
    rows = {table: all_rows(cur, schema, table, columns)
            for table, (columns, _) in before.items()}

    cur.execute("DELETE FROM schema_migrations")
    try:
        for path in sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda item: item.name):
            for statement in split_statements(path.read_text(encoding="utf-8")):
                cur.execute(statement)
        error = None
    except mysql.connector.Error as exc:
        error = str(exc)
    check("every migration applied a second time", error is None, error or "")
    if error:
        return

    changed = {table: (counts[table], row_count(cur, schema, table))
               for table in counts if row_count(cur, schema, table) != counts[table]}
    check("no table gained or lost rows on the second pass", not changed, str(changed))

    altered = [table for table, captured in rows.items()
               if all_rows(cur, schema, table, before[table][0]) != captured]
    check("existing rows are byte for byte unchanged", not altered, ", ".join(altered))

    # Running the files by hand leaves the ledger empty on purpose, so the
    # runner is pointed at the same database again: it re-applies and this
    # time records what it did.
    applied = migrate(db, log=lambda message: print(f"       {message.strip()}"))
    check("the runner re-applies and re-records every file",
          applied == len(list(MIGRATIONS_DIR.glob("*.sql"))), str(applied))
    drifted = [f"{entry.filename}:{entry.state}" for entry in plan(db)
               if entry.state != "applied"]
    check("the ledger ends up clean", not drifted, ", ".join(drifted))


def check_drift_guard(cur, db: Database) -> None:
    """An applied file that is edited afterwards must be caught, not ignored."""
    print("\nDrift guard")
    edited = Path("001_victim_management.sql")
    cur.execute("UPDATE schema_migrations SET checksum = %s WHERE filename = %s",
                ("0" * 64, edited.name))
    try:
        states = {entry.filename: entry.state for entry in plan(db)}
        check("a file whose recorded checksum no longer matches is reported as drift",
              states.get(edited.name) == "drift", str(states))
        try:
            migrate(db, log=lambda message: None)
            check("the runner refuses to continue past a drifted file", False,
                  "it applied migrations anyway")
        except MigrationError:
            check("the runner refuses to continue past a drifted file", True)
    finally:
        cur.execute("UPDATE schema_migrations SET checksum = %s WHERE filename = %s",
                    (checksum(MIGRATIONS_DIR / edited.name), edited.name))
        check("the ledger is usable again once the checksum is restored",
              all(entry.state == "applied" for entry in plan(db)))


def run_selftest(dst: str) -> None:
    print("\nv1 regression suite against the migrated copy")
    result = subprocess.run([sys.executable, str(SELFTEST), "--db", dst],
                            capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    summary = (result.stdout or "").strip().splitlines()
    check("scripts/selftest.py passes on the migrated copy", result.returncode == 0,
          summary[-1] if summary else (result.stderr or "")[-300:])
    if summary:
        print(f"       {summary[-1]}")
    if result.returncode != 0:
        failures = [line for line in summary if line.lstrip().startswith("FAIL")]
        for line in failures[:20]:
            print(f"       {line.strip()}")
        if result.stderr.strip():
            print("       " + result.stderr.strip().splitlines()[-1])


def drop_scratch(section: dict, dst: str) -> None:
    connection = mysql.connector.connect(
        host=section.get("host", "127.0.0.1"),
        port=int(section.get("port", 3306)),
        user=section.get("user", "root"),
        password=section.get("password", ""),
        autocommit=True,
    )
    try:
        connection.cursor().execute(f"DROP DATABASE IF EXISTS {quote(dst)}")
    finally:
        connection.close()


def install_legacy_v1_trigger(cur) -> None:
    """Stand in for a database installed before the trigger was corrected.

    The clone is built from the current source files, which already hold
    the fixed custody trigger, so v1's broken version is put back by hand.
    Without this, nothing would prove migration 003 clears it out of a real
    existing install - and while it is present, recording evidence with a
    blank custody date fails with MySQL error 1442.
    """
    cur.execute("DROP TRIGGER IF EXISTS trg_evidence_before_custody")
    cur.execute(
        """
        CREATE TRIGGER trg_evidence_after_insert
        AFTER INSERT ON evidence
        FOR EACH ROW
        BEGIN
            IF NEW.chain_of_custody_datetime IS NULL THEN
                UPDATE evidence
                   SET chain_of_custody_datetime = NEW.collected_datetime
                 WHERE evidence_id = NEW.evidence_id;
            END IF;
        END
        """
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test the schema migrations on a copy of the live database.")
    parser.add_argument("--keep", action="store_true", help="leave the scratch schema in place")
    parser.add_argument("--db", metavar="SCHEMA", help="name for the scratch schema")
    args = parser.parse_args()

    config = load_config()
    section = config["database"]
    src = section.get("database", "crime_records")
    dst = args.db or f"{src}_migtest"

    # A slipped finger here could point the script at live data, and the
    # first thing it does is drop the schema it was given.
    if dst == src or not dst.startswith(f"{src}_"):
        print(f"[x] Refusing to use '{dst}' as the scratch schema. "
              f"It must start with '{src}_' and may not be the live schema.")
        return 2

    print(f"Copying {src} into {dst} (the live schema is only read from) ...")
    connection = mysql.connector.connect(
        host=section.get("host", "127.0.0.1"),
        port=int(section.get("port", 3306)),
        user=section.get("user", "root"),
        password=section.get("password", ""),
        charset="utf8mb4",
        autocommit=True,
        connection_timeout=10,
    )
    cur = connection.cursor()
    db = None
    completed = False
    try:
        cur.execute(f"DROP DATABASE IF EXISTS {quote(dst)}")
        cur.execute(f"CREATE DATABASE {quote(dst)} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cur.execute(f"USE {quote(dst)}")
        # Tables are copied in alphabetical order, which does not respect
        # the foreign keys, so the checks stay off until the copy is
        # complete. Every migration statement after this point runs with
        # them back on, which is what the assertions depend on.
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        tables = clone_schema(cur, src)
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        print(f"  {len(tables)} tables and "
              f"{sum(row_count(cur, dst, table) for table in tables)} rows copied")

        before = snapshot(cur, src, tables)
        if LEDGER_TABLE in table_names(cur, src):
            # The live database has already been migrated, so the copy
            # starts out with the v2 structures in it and the migrations
            # are applied over the top of them - which is the re-runnable
            # DDL being proved. Putting v1's broken trigger back here
            # would break the very inserts the migration is supposed to
            # enable, so that simulation only runs on a v1 source.
            print("  note: the live schema is already migrated; its ledger was "
                  "left behind so every migration runs again on the copy")
        else:
            install_legacy_v1_trigger(cur)

        config["database"]["database"] = dst
        db = Database(config)
        print(f"\nApplying migrations to {dst} ...")
        migrate(db)

        check_objects(cur)
        check_ledger(db)
        verify_preserved(cur, before)
        check_backfills(cur)
        check_no_orphans(cur)
        check_statement_versions(cur)
        check_evidence_lifecycle(cur, db)
        check_idempotent(cur, db, before)
        check_drift_guard(cur, db)
        run_selftest(dst)
        completed = FAILED == 0
    except Exception as exc:  # noqa: BLE001 - the run must still report and clean up
        print(f"\n[x] The migration test stopped: {type(exc).__name__}: {exc}")
    finally:
        if db is not None:
            db.close()
        cur.close()
        connection.close()
        if completed and not args.keep:
            drop_scratch(section, dst)
            print(f"\nScratch schema '{dst}' removed.")
        else:
            print(f"\nScratch schema '{dst}' left in place "
                  f"- drop it with: DROP DATABASE {dst}")

    print(f"\n{PASSED} passed, {FAILED} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
