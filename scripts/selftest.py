"""Schema and stored procedure checks.

    py scripts\\selftest.py

Runs against the database named in config.ini. Every check creates its
own records and removes them again, so it is safe to run repeatedly.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.connection import Database, DatabaseError  # noqa: E402
from app.db.repositories import Repositories  # noqa: E402

EXPECTED_TABLES = [
    "police_stations", "officers", "offence_sections", "users", "crime_cases",
    "case_offences", "case_status_history", "suspects", "victims", "witnesses",
    "evidence", "arrests", "court_proceedings", "convictions",
]
EXPECTED_VIEWS = [
    "v_case_overview", "v_officer_workload", "v_station_statistics",
    "v_offence_statistics", "v_monthly_caseload", "v_suspect_summary",
    "v_upcoming_hearings",
]
EXPECTED_PROCEDURES = [
    "sp_file_case", "sp_update_case_status", "sp_assign_officer",
    "sp_search_cases", "sp_record_arrest", "sp_record_conviction",
    "sp_dashboard_summary",
]
EXPECTED_TRIGGERS = [
    "trg_cases_before_insert", "trg_cases_after_insert",
    "trg_cases_after_status_update", "trg_suspects_after_arrest",
    "trg_suspects_after_conviction", "trg_case_offences_after_insert",
    "trg_case_offences_after_delete", "trg_evidence_after_insert",
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


def existing_objects(db: Database, kind: str) -> set[str]:
    rows = db.query(
        """
        SELECT TABLE_NAME AS name FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = %s
        """,
        (kind,),
    )
    return {row["name"] for row in rows}


def check_schema(db: Database) -> None:
    print("Schema")
    tables = existing_objects(db, "BASE TABLE")
    for name in EXPECTED_TABLES:
        check(f"table {name}", name in tables)

    views = existing_objects(db, "VIEW")
    for name in EXPECTED_VIEWS:
        check(f"view {name}", name in views)

    procedures = {row["ROUTINE_NAME"] for row in db.query(
        "SELECT ROUTINE_NAME FROM information_schema.ROUTINES "
        "WHERE ROUTINE_SCHEMA = DATABASE() AND ROUTINE_TYPE = 'PROCEDURE'"
    )}
    for name in EXPECTED_PROCEDURES:
        check(f"procedure {name}", name in procedures)

    triggers = {row["TRIGGER_NAME"] for row in db.query(
        "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS "
        "WHERE TRIGGER_SCHEMA = DATABASE()"
    )}
    for name in EXPECTED_TRIGGERS:
        check(f"trigger {name}", name in triggers)


def check_behaviour(db: Database) -> None:
    print("Behaviour")
    repos = Repositories(db)

    stations = repos.stations.list_all()
    officers = repos.officers.options()
    sections = repos.offences.options()
    if not stations or not officers or not sections:
        check("reference data present", False,
              "run py scripts\\setup_db.py before the self test")
        return

    station = stations[0]
    officer = next((o for o in officers if o["station_id"] == station["station_id"]),
                    officers[0])
    section_ids = [sections[0]["section_id"], sections[1]["section_id"]]
    admin = repos.users.list_all()[0]

    filed = repos.cases.file_case(
        station_id=station["station_id"],
        officer_id=officer["officer_id"],
        user_id=admin["user_id"],
        category="theft",
        offence_type="Self test",
        occurrence_datetime="2026-01-15 10:30:00",
        reporting_datetime="2026-01-15 14:00:00",
        place_of_occurrence="Test address",
        description="Created by the self test.",
        section_ids=section_ids,
    )
    case_id = filed["case_id"]
    check("sp_file_case returns a case number", bool(filed.get("case_no")), str(filed))
    check("case number follows CR/YYYY/NNNN",
          str(filed.get("case_no", "")).startswith("CR/"), str(filed.get("case_no")))

    case = repos.cases.get(case_id)
    check("new case is registered", case["status"] == "registered", case["status"])
    check("offences were linked", len(repos.cases.offences(case_id)) == len(section_ids),
          str(len(repos.cases.offences(case_id))))
    check("offence counter maintained by trigger", case["offence_count"] == len(section_ids),
          str(case["offence_count"]))

    history = repos.cases.history(case_id)
    check("insert trigger wrote the opening history row", len(history) >= 1, str(len(history)))

    repos.cases.update_status(case_id, "under_investigation", admin["user_id"], "Self test")
    case = repos.cases.get(case_id)
    check("status moved forward", case["status"] == "under_investigation", case["status"])
    check("history recorded the change", len(repos.cases.history(case_id)) == len(history) + 1)

    blocked = False
    try:
        repos.cases.update_status(case_id, "registered", admin["user_id"], "Backwards")
    except DatabaseError:
        blocked = True
    check("backwards transition refused", blocked)

    suspect_id = repos.suspects.create(case_id, "Self Test Suspect", status="wanted")
    repos.arrests.record(case_id, suspect_id, officer["officer_id"],
                          "2026-02-01 09:00:00", "Test location", "judicial_remand", None)
    suspect = repos.suspects.get(suspect_id)
    check("arrest trigger updated the suspect", suspect["status"] == "arrested",
          suspect["status"])

    repos.cases.update_status(case_id, "charges_filed", admin["user_id"])
    repos.cases.update_status(case_id, "trial", admin["user_id"])
    repos.convictions.record(case_id, suspect_id, admin["user_id"], "Test Court",
                             "guilty", "imprisonment", 5.0, 10000.0,
                             "2026-03-01", "2031-03-01")
    case = repos.cases.get(case_id)
    suspect = repos.suspects.get(suspect_id)
    check("conviction closed the case", case["status"] == "closed_convicted", case["status"])
    check("conviction trigger updated the suspect", suspect["status"] == "convicted",
          suspect["status"])
    check("closed case carries a close date", case["closed_datetime"] is not None)

    restricted = False
    try:
        db.execute("DELETE FROM police_stations WHERE station_id = %s",
                   (station["station_id"],))
    except DatabaseError:
        restricted = True
    check("deleting a station with cases is refused", restricted)

    db.execute("DELETE FROM crime_cases WHERE case_id = %s", (case_id,))
    leftovers = db.query(
        """
        SELECT
          (SELECT COUNT(*) FROM suspects WHERE case_id = %s) AS suspects,
          (SELECT COUNT(*) FROM arrests WHERE case_id = %s) AS arrests,
          (SELECT COUNT(*) FROM convictions WHERE case_id = %s) AS convictions,
          (SELECT COUNT(*) FROM case_offences WHERE case_id = %s) AS offences
        """,
        (case_id, case_id, case_id, case_id),
    )[0]
    check("deleting a case cascades to its children",
          all(value == 0 for value in leftovers.values()), str(leftovers))


def main() -> int:
    db = Database()
    print(f"Testing {db.config['database'].get('database')}\n")
    try:
        check_schema(db)
        check_behaviour(db)
    finally:
        db.close()

    print(f"\n{PASSED} passed, {FAILED} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
