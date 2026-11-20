"""Apply the versioned schema migrations to a database.

    python scripts\\migrate.py --status
    python scripts\\migrate.py

Use --db to work on a different schema than the one in config.ini, which
is how the migration dry run in scripts/test_migration.py is aimed at a
copy rather than the live data.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.connection import Database, DatabaseError, load_config  # noqa: E402
from app.db.migrations import MigrationError, migrate, status  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Crime Record System schema migrations.")
    parser.add_argument("--status", action="store_true",
                        help="report what would be applied without changing anything")
    parser.add_argument("--db", metavar="SCHEMA",
                        help="use this schema instead of the database in config.ini")
    args = parser.parse_args()

    config = load_config()
    if args.db:
        config["database"]["database"] = args.db

    try:
        db = Database(config)
    except DatabaseError as exc:
        print(f"[x] {exc}")
        return 1

    schema = config["database"].get("database", "crime_records")
    try:
        if args.status:
            entries = status(db)
            print(f"Migrations for {schema}")
            for entry in entries:
                detail = f" - {entry.detail}" if entry.detail else ""
                print(f"  {entry.state:<8} {entry.filename}{detail}")
            pending = [e for e in entries if e.state == "pending"]
            drifted = [e for e in entries if e.state == "drift"]
            print(f"\n{len(pending)} to apply, {len(drifted)} drifted, "
                  f"{len(entries) - len(pending) - len(drifted)} up to date")
            return 1 if drifted else 0

        print(f"Applying migrations to {schema} ...")
        applied_count = migrate(db)
        print(f"\nDone. {applied_count} migration(s) applied.")
        return 0
    except (MigrationError, DatabaseError) as exc:
        print(f"[x] {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
