"""Create the crime_records database and apply every SQL file.

    py scripts\\setup_db.py

Safe to run more than once: tables use CREATE TABLE IF NOT EXISTS,
views use CREATE OR REPLACE, routines and triggers are dropped before
being recreated, and reference rows use INSERT IGNORE.
"""

from __future__ import annotations

import sys
from pathlib import Path

import mysql.connector

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.connection import ConfigError, load_config  # noqa: E402
from app.db.passwords import hash_password  # noqa: E402

SQL_DIR = PROJECT_ROOT / "sql"

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"


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


def apply_file(cursor, path: Path) -> int:
    script = path.read_text(encoding="utf-8")
    statements = split_statements(script)
    for statement in statements:
        cursor.execute(statement)
    return len(statements)


def ensure_admin_user(cursor) -> bool:
    """Create the default admin account. Returns True if it was created."""
    cursor.execute("SELECT user_id FROM users WHERE username = %s", (DEFAULT_ADMIN_USERNAME,))
    if cursor.fetchone():
        return False
    cursor.execute(
        """
        INSERT INTO users (username, password_hash, role, full_name, is_active)
        VALUES (%s, %s, 'admin', %s, TRUE)
        """,
        (DEFAULT_ADMIN_USERNAME, hash_password(DEFAULT_ADMIN_PASSWORD), "System Administrator"),
    )
    return True


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"[x] {exc}")
        return 1

    section = config["database"]
    db_name = section.get("database", "crime_records")

    print(f"Connecting to MySQL at {section.get('host', '127.0.0.1')}:"
          f"{section.get('port', 3306)} as {section.get('user', 'root')} ...")
    try:
        connection = mysql.connector.connect(
            host=section.get("host", "127.0.0.1"),
            port=int(section.get("port", 3306)),
            user=section.get("user", "root"),
            password=section.get("password", ""),
            charset="utf8mb4",
            autocommit=True,
            connection_timeout=10,
        )
    except mysql.connector.Error as exc:
        print(f"[x] Could not connect to MySQL: {exc}")
        print("    Check that the server is running and that config.ini is correct.")
        return 1

    cursor = connection.cursor()
    try:
        print(f"Applying schema to '{db_name}' ...")
        for name in ("schema.sql", "views.sql", "procedures.sql",
                     "triggers.sql", "reference_data.sql"):
            path = SQL_DIR / name
            if not path.exists():
                print(f"[x] Missing SQL file: {path}")
                return 1
            count = apply_file(cursor, path)
            print(f"  ok  {name:<20} {count} statements")

        created = ensure_admin_user(cursor)

        cursor.execute("SELECT COUNT(*) FROM crime_cases")
        case_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM offence_sections")
        offence_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM police_stations")
        station_count = cursor.fetchone()[0]

        print()
        print("Database ready.")
        print(f"  police stations : {station_count}")
        print(f"  offence sections: {offence_count}")
        print(f"  cases           : {case_count}")
        if created:
            print()
            print(f"  Default login   : {DEFAULT_ADMIN_USERNAME} / {DEFAULT_ADMIN_PASSWORD}")
            print("  Change it from the Users screen after signing in.")
        else:
            print()
            print("  Admin account already exists; its password was left unchanged.")
        print()
        print("Start the application with:  py main.py")
        return 0
    except mysql.connector.Error as exc:
        print(f"[x] Setup failed: {exc}")
        return 1
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
