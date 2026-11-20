"""Repository-layer checks: transactions, role gates, privacy and audit.

    python scripts\\test_repositories.py
    python scripts\\test_repositories.py --db crime_records_copy

Runs against the database named in config.ini, or against --db when you
want to test a copy. Like the self test, every check files its own case,
works inside that case and deletes it again at the end.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.auth import AccessDenied  # noqa: E402  (used as the default in refused())
from app.db.connection import Database, DatabaseError, load_config  # noqa: E402
from app.db.evidence import EvidenceRepository  # noqa: E402
from app.db.repositories import Repositories  # noqa: E402
from app.db.privacy import RESTRICTED  # noqa: E402

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


def refused(label: str, action, expected: type = AccessDenied) -> None:
    """Record a check that the repository rejects an operation."""
    try:
        action()
    except expected:
        check(label, True)
    except Exception as exc:
        check(label, False, f"{type(exc).__name__}: {exc}")
    else:
        check(label, False, "the operation was allowed")


class Fixtures:
    """A case of the test's own, plus the reference rows it needs."""

    def __init__(self, db: Database) -> None:
        self.db = db
        admin = next((u for u in Repositories(db).users.list_all() if u["role"] == "admin"), None)
        if admin is None:
            raise SystemExit("No admin account. Run python scripts\\setup_db.py first.")
        self.actor = {"user_id": admin["user_id"], "username": admin["username"], "role": "admin"}
        self.repos = Repositories(db, self.actor)

        stations = self.repos.stations.list_all()
        officers = self.repos.officers.options()
        sections = self.repos.offences.options()
        if not stations or not officers or len(sections) < 2:
            raise SystemExit("No reference data. Run python scripts\\setup_db.py first.")

        self.station = stations[0]
        self.officer = next((o for o in officers if o["station_id"] == self.station["station_id"]),
                            officers[0])
        self.other_officer = next((o for o in officers
                                   if o["officer_id"] != self.officer["officer_id"]),
                                  self.officer)
        self.section_ids = [sections[0]["section_id"], sections[1]["section_id"]]

        filed = self.repos.cases.file_case(
            station_id=self.station["station_id"],
            officer_id=self.officer["officer_id"],
            user_id=self.actor["user_id"],
            category="theft",
            offence_type="Repository test",
            occurrence_datetime="2026-04-01 10:00:00",
            reporting_datetime="2026-04-01 12:00:00",
            place_of_occurrence="Test address",
            description="Created by the repository test.",
            section_ids=self.section_ids,
        )
        self.case_id = filed["case_id"]

    # -- counts -------------------------------------------------------
    def count(self, table: str) -> int:
        column = {"victims": "victim_id", "witnesses": "witness_id",
                  "evidence": "evidence_id", "witness_statements": "statement_id",
                  "evidence_custody_log": "custody_id", "victim_medical_records":
                  "medical_record_id", "audit_log": "audit_id"}.get(table, "*")
        return int(self.db.scalar(f"SELECT COUNT({column}) FROM {table}") or 0)

    def audit_for(self, entity: str, entity_id: int, action: str) -> dict | None:
        return self.db.query_one(
            "SELECT * FROM audit_log WHERE entity = %s AND entity_id = %s AND action = %s"
            " ORDER BY audit_id DESC",
            (entity, entity_id, action),
        )

    def audit_count(self, entity: str, entity_id: int, action: str | None = None) -> int:
        sql = "SELECT COUNT(*) FROM audit_log WHERE entity = %s AND entity_id = %s"
        params: list = [entity, entity_id]
        if action:
            sql += " AND action = %s"
            params.append(action)
        return int(self.db.scalar(sql, params) or 0)

    def actor_as(self, role: str) -> dict:
        return {"user_id": self.actor["user_id"], "username": self.actor["username"],
                "role": role}

    def repos_as(self, role: str) -> Repositories:
        return Repositories(self.db, self.actor_as(role))

    def cleanup(self) -> None:
        self.db.execute("DELETE FROM crime_cases WHERE case_id = %s", (self.case_id,))


# ---------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------
def test_transaction_rolls_back_on_failure(fx: Fixtures) -> None:
    print("Transactions")
    before = fx.count("victims")
    try:
        with fx.db.transaction():
            fx.db.execute("INSERT INTO victims (case_id, name) VALUES (%s, %s)",
                          (fx.case_id, "Rolled back"))
            check("the row is visible inside its own transaction",
                  fx.count("victims") == before + 1)
            raise DatabaseError("something went wrong")
    except DatabaseError:
        pass
    check("a failed transaction leaves no rows behind", fx.count("victims") == before,
          f"{before} before, {fx.count('victims')} after")


def test_transaction_commits_on_success(fx: Fixtures) -> None:
    before = fx.count("victims")
    with fx.db.transaction():
        victim_id = fx.db.execute("INSERT INTO victims (case_id, name) VALUES (%s, %s)",
                                  (fx.case_id, "Committed"))
    check("a completed transaction keeps its rows", fx.count("victims") == before + 1)
    row = fx.db.query_one("SELECT name FROM victims WHERE victim_id = %s", (victim_id,))
    check("the committed row is readable", row is not None and row["name"] == "Committed")
    fx.db.execute("DELETE FROM victims WHERE victim_id = %s", (victim_id,))


def test_transaction_rolls_back_when_the_database_rejects_a_later_write(fx: Fixtures) -> None:
    """The realistic failure: the second table in a multi-table write is refused."""
    before_victims = fx.count("victims")
    try:
        with fx.db.transaction():
            fx.db.execute("INSERT INTO victims (case_id, name) VALUES (%s, %s)",
                          (fx.case_id, "Half written"))
            fx.db.execute(
                "INSERT INTO victim_medical_records (victim_id, facility, treatment_type,"
                " recorded_by_user_id) VALUES (%s, %s, %s, %s)",
                (999999, "Test hospital", "first_aid", fx.actor["user_id"]))
    except DatabaseError:
        pass
    check("a rejected write rolls the whole transaction back",
          fx.count("victims") == before_victims,
          f"{before_victims} before, {fx.count('victims')} after")


def test_connection_works_normally_after_a_transaction(fx: Fixtures) -> None:
    """Rollback must not leave the connection sitting in an open transaction."""
    try:
        with fx.db.transaction():
            raise DatabaseError("forced rollback")
    except DatabaseError:
        pass
    victim_id = fx.db.execute("INSERT INTO victims (case_id, name) VALUES (%s, %s)",
                              (fx.case_id, "After rollback"))
    check("an autocommit write after a rollback is kept",
          fx.db.query_one("SELECT victim_id FROM victims WHERE victim_id = %s",
                          (victim_id,)) is not None)
    fx.db.execute("DELETE FROM victims WHERE victim_id = %s", (victim_id,))


def test_a_nested_transaction_joins_the_outer_one(fx: Fixtures) -> None:
    """A repository method may call transaction() inside another one.

    The inner block must not commit the outer writer's work.
    """
    before = fx.count("victims")
    try:
        with fx.db.transaction():
            fx.db.execute("INSERT INTO victims (case_id, name) VALUES (%s, %s)",
                          (fx.case_id, "Outer writer"))
            with fx.db.transaction():
                fx.db.execute("INSERT INTO victims (case_id, name) VALUES (%s, %s)",
                              (fx.case_id, "Inner writer"))
            raise DatabaseError("forced rollback of the outer block")
    except DatabaseError:
        pass
    check("a nested block does not commit the outer transaction",
          fx.count("victims") == before, f"{before} before, {fx.count('victims')} after")
    victim_id = fx.db.execute("INSERT INTO victims (case_id, name) VALUES (%s, %s)",
                              (fx.case_id, "After nesting"))
    check("autocommit is restored after nested blocks",
          fx.db.query_one("SELECT victim_id FROM victims WHERE victim_id = %s",
                          (victim_id,)) is not None)
    fx.db.execute("DELETE FROM victims WHERE victim_id = %s", (victim_id,))


# ---------------------------------------------------------------------
# Victims
# ---------------------------------------------------------------------
def test_victim_profile_stores_the_new_fields(fx: Fixtures) -> None:
    print("Victims")
    victim_id = fx.repos.victims.create(
        fx.case_id, "Test Victim", age=31, gender="male", phone="9999900000",
        address="Test street", injury_level="moderate",
        date_of_birth="1995-01-02", email="victim@example.test", occupation="Driver",
        national_id="AB123456", emergency_contact_name="A Relation",
        emergency_contact_phone="8888800000", relationship_to_accused="neighbour",
        incident_datetime="2026-04-01 09:15:00", incident_location="Test lane",
        medical_assistance_status="provided", hospital_name="Test Hospital",
        hospital_reference="TH-2026-1", special_assistance="visual impairment",
        confidentiality_level="confidential",
    )
    row = fx.repos.victims.get(victim_id)
    check("the victim profile keeps every new field",
          row is not None
          and row["national_id"] == "AB123456"
          and row["email"] == "victim@example.test"
          and row["occupation"] == "Driver"
          and row["emergency_contact_phone"] == "8888800000"
          and row["relationship_to_accused"] == "neighbour"
          and row["hospital_name"] == "Test Hospital"
          and row["special_assistance"] == "visual impairment"
          and str(row["incident_datetime"]) == "2026-04-01 09:15:00",
          str(row))
    check("the v1 columns still work",
          row["name"] == "Test Victim" and row["age"] == 31
          and row["injury_level"] == "moderate" and row["case_id"] == fx.case_id, str(row))
    check("confidentiality is stored", row["confidentiality_level"] == "confidential",
          str(row["confidentiality_level"]))


# ---------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------
def test_victim_changes_are_logged(fx: Fixtures) -> None:
    print("Audit trail")
    victim_id = fx.repos.victims.create(fx.case_id, "Logged Victim")

    created = fx.audit_for("victim", victim_id, "create")
    check("creating a victim is logged", created is not None)
    if created is None:
        return
    check("the audit entry names the user who made the change",
          created["changed_by_user_id"] == fx.actor["user_id"]
          and created["username_snapshot"] == fx.actor["username"], str(created))
    check("the audit entry links the case", created["case_id"] == fx.case_id,
          str(created["case_id"]))
    check("one entry per change", fx.audit_count("victim", victim_id, "create") == 1,
          str(fx.audit_count("victim", victim_id, "create")))

    fx.repos.victims.update(victim_id, phone="7777700000")
    check("changing a victim is logged",
          fx.audit_for("victim", victim_id, "update") is not None)

    fx.repos.victims.delete(victim_id)
    deleted = fx.audit_for("victim", victim_id, "delete")
    check("deleting a victim is logged", deleted is not None)
    check("the delete entry still points at the case",
          deleted is not None and deleted["case_id"] == fx.case_id, str(deleted))


# ---------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------
def test_a_viewer_cannot_change_victim_records(fx: Fixtures) -> None:
    print("Victim access control")
    viewer = fx.repos_as("viewer")
    victim_id = fx.repos.victims.create(fx.case_id, "Guarded Victim")

    refused("a viewer cannot record a victim",
            lambda: viewer.victims.create(fx.case_id, "Should not exist"))
    refused("a viewer cannot edit a victim",
            lambda: viewer.victims.update(victim_id, phone="123"))
    refused("a viewer cannot delete a victim",
            lambda: viewer.victims.delete(victim_id))
    refused("a viewer cannot add a medical record",
            lambda: viewer.victims.add_medical_record(victim_id, "Test hospital", "first_aid"))
    refused("a viewer cannot log contact with a victim",
            lambda: viewer.victims.add_contact(victim_id, "phone", "2026-04-02 10:00:00"))
    refused("a viewer cannot record compensation",
            lambda: viewer.victims.add_compensation(victim_id, "Test scheme"))


def test_a_viewer_sees_masked_victim_details(fx: Fixtures) -> None:
    print("Victim privacy")
    victim_id = fx.repos.victims.create(
        fx.case_id, "Private Victim", phone="9000000001", address="12 Secret Lane",
        email="hidden@example.test", national_id="ZZ999111", date_of_birth="1990-05-05",
        emergency_contact_name="A Relation", emergency_contact_phone="9000000002",
        hospital_name="Secret Hospital",
    )
    admin = fx.repos.victims.get(victim_id)
    viewer = fx.repos_as("viewer").victims.get(victim_id)

    check("an administrator reads the real contact details",
          admin["phone"] == "9000000001" and admin["national_id"] == "ZZ999111",
          str(admin["phone"]))
    for field in ("phone", "address", "email", "national_id", "date_of_birth",
                  "emergency_contact_name", "emergency_contact_phone", "hospital_name"):
        check(f"a viewer does not see the victim {field.replace('_', ' ')}",
              viewer[field] == RESTRICTED, str(viewer[field]))
    check("a viewer still sees the work they are here for",
          viewer["name"] == "Private Victim" and viewer["injury_level"] == "none"
          and viewer["case_id"] == fx.case_id, str(viewer))

    row = next(r for r in fx.repos_as("viewer").victims.list_all()
               if r["victim_id"] == victim_id)
    check("the victim register masks the same fields", row["phone"] == RESTRICTED,
          str(row["phone"]))
    in_case = fx.repos_as("viewer").victims.for_case(fx.case_id)
    check("the case tab masks them too",
          any(v["victim_id"] == victim_id and v["address"] == RESTRICTED for v in in_case),
          str(in_case))
    check("a viewer cannot search for a hidden address",
          fx.repos_as("viewer").victims.list_all(search="Secret Lane") == [])
    check("an officer can search for it",
          any(v["victim_id"] == victim_id
              for v in fx.repos_as("officer").victims.list_all(search="Secret Lane")))


# ---------------------------------------------------------------------
# Victim records: medical, contact log, compensation
# ---------------------------------------------------------------------
def test_victim_records_are_kept_beside_the_profile(fx: Fixtures) -> None:
    print("Victim records")
    victims = fx.repos.victims
    victim_id = victims.create(fx.case_id, "Recorded Victim", statement="Initial account")

    medical_id = victims.add_medical_record(
        victim_id, "City Test Hospital", "surgery", treating_doctor="Dr Test",
        description="Stable after surgery", admitted_datetime="2026-04-02 09:00:00",
        discharged_datetime="2026-04-06 09:00:00", cost_incurred=15000.50,
        remarks="Awaiting bills")
    rows = victims.medical_records(victim_id)
    check("the medical record is filed against the victim",
          len(rows) == 1 and rows[0]["medical_record_id"] == medical_id, str(rows))
    check("the medical record says who recorded it",
          bool(rows) and rows[0]["recorded_by"] == fx.actor["username"], str(rows))
    check("the medical detail is stored",
          bool(rows) and rows[0]["facility"] == "City Test Hospital"
          and rows[0]["treating_doctor"] == "Dr Test"
          and rows[0]["cost_incurred"] == Decimal("15000.50"), str(rows))
    check("the medical record does not overwrite the profile",
          victims.get(victim_id)["statement"] == "Initial account")

    victims.update_medical_record(medical_id, remarks="Bills verified")
    check("a medical record can be corrected",
          victims.medical_records(victim_id)[0]["remarks"] == "Bills verified")

    contact_id = victims.add_contact(
        victim_id, "phone", "2026-04-03 11:00:00", made_by_officer_id=fx.officer["officer_id"],
        purpose="Recovery status", outcome="Reachable", follow_up_required=True,
        follow_up_datetime="2026-04-10 10:00:00")
    contacts = victims.contacts(victim_id)
    check("the contact log names the officer who made the call",
          len(contacts) == 1 and contacts[0]["made_by_name"] == fx.officer["name"],
          str(contacts))
    check("a follow-up is remembered",
          bool(contacts) and contacts[0]["follow_up_required"] and
          str(contacts[0]["follow_up_datetime"]) == "2026-04-10 10:00:00", str(contacts))

    compensation_id = victims.add_compensation(
        victim_id, "State Victim Compensation Scheme", compensation_type="monetary",
        application_date="2026-04-05", awarded_amount=50000, received_amount=10000,
        status="approved", sanctioning_authority="District Magistrate",
        order_reference="SVCS/2026/1")
    awards = victims.compensation(victim_id)
    check("compensation is tracked apart from the profile",
          len(awards) == 1 and awards[0]["scheme_name"].startswith("State Victim"),
          str(awards))
    victims.update_compensation(compensation_id, received_amount=50000)
    check("a later payment can be recorded against the same award",
          victims.compensation(victim_id)[0]["received_amount"] == Decimal("50000.00"))

    victims.delete_medical_record(medical_id)
    victims.delete_contact(contact_id)
    victims.delete_compensation(compensation_id)
    check("the child records can be removed",
          victims.medical_records(victim_id) == [] and victims.contacts(victim_id) == []
          and victims.compensation(victim_id) == [])


def test_the_database_refuses_an_impossible_medical_record(fx: Fixtures) -> None:
    victims = fx.repos.victims
    victim_id = victims.create(fx.case_id, "Impossible Dates")
    refused("a discharge before the admission is refused",
            lambda: victims.add_medical_record(
                victim_id, "City Test Hospital", "surgery",
                admitted_datetime="2026-04-06 09:00:00",
                discharged_datetime="2026-04-02 09:00:00"),
            DatabaseError)
    check("nothing half-written was left behind", victims.medical_records(victim_id) == [])
    refused("a field the record does not own is refused",
            lambda: victims.add_medical_record(
                victim_id, "City Test Hospital", "surgery", password="nope"),
            DatabaseError)


def test_medical_and_compensation_records_are_for_staff_only(fx: Fixtures) -> None:
    print("Victim record access")
    victim_id = fx.repos.victims.create(fx.case_id, "Staff Only Victim")
    medical_id = fx.repos.victims.add_medical_record(victim_id, "City Test Hospital",
                                                    "first_aid")
    compensation_id = fx.repos.victims.add_compensation(victim_id, "Test scheme")
    viewer = fx.repos_as("viewer").victims
    refused("a viewer cannot read the medical history",
            lambda: viewer.medical_records(victim_id))
    refused("a viewer cannot read the compensation record",
            lambda: viewer.compensation(victim_id))
    refused("a viewer cannot correct a medical record",
            lambda: viewer.update_medical_record(medical_id, remarks="nope"))
    refused("a viewer cannot delete a compensation record",
            lambda: viewer.delete_compensation(compensation_id))
    check("a viewer can still read the contact log",
          isinstance(viewer.contacts(victim_id), list))


def test_a_victim_is_not_left_half_written_when_the_trail_fails(fx: Fixtures) -> None:
    """The profile and its audit entry are one unit of work."""
    print("Victim atomicity")
    before = fx.count("victims")
    ghost = Repositories(fx.db, {"user_id": 999999, "username": "ghost", "role": "admin"})
    try:
        ghost.victims.create(fx.case_id, "Half written")
        check("the create was refused", False, "it was accepted")
    except DatabaseError:
        check("the create was refused", True)
    check("the victim row was rolled back with it", fx.count("victims") == before,
          f"{before} before, {fx.count('victims')} after")


# ---------------------------------------------------------------------
# Witnesses
# ---------------------------------------------------------------------
def test_witness_profile_stores_the_new_fields(fx: Fixtures) -> None:
    print("Witnesses")
    witness_id = fx.repos.witnesses.create(
        fx.case_id, "Test Witness", phone="9111100000", address="1 Open Street",
        date_of_birth="1988-02-02", gender="female", email="witness@example.test",
        occupation="Shopkeeper", witness_type="eyewitness",
        relationship_to_victim="neighbour", relationship_to_accused="unknown",
        observation_datetime="2026-04-01 10:05:00", observation_location="Shop counter",
        statement_language="tamil", availability_status="available",
        protection_required=False, confidentiality_level="internal",
    )
    row = fx.repos.witnesses.get(witness_id)
    check("the witness profile keeps every new field",
          row is not None
          and row["witness_type"] == "eyewitness"
          and row["relationship_to_victim"] == "neighbour"
          and row["statement_language"] == "tamil"
          and row["availability_status"] == "available"
          and str(row["observation_datetime"]) == "2026-04-01 10:05:00", str(row))
    check("the v1 columns still work",
          row["name"] == "Test Witness" and row["phone"] == "9111100000"
          and row["case_id"] == fx.case_id, str(row))
    check("recording a witness is not an assessment",
          row["assessed_by_user_id"] is None and row["assessed_at"] is None, str(row))
    refused("the assessment cannot be written through the profile",
            lambda: fx.repos.witnesses.update(witness_id, assessed_by_user_id=1),
            DatabaseError)
    refused("credibility is not an ordinary profile field",
            lambda: fx.repos.witnesses.update(witness_id, is_reliable=False),
            DatabaseError)


def test_statement_versions_are_preserved(fx: Fixtures) -> None:
    print("Statement versions")
    witnesses = fx.repos.witnesses
    witness_id = witnesses.create(fx.case_id, "Talking Witness")

    first = witnesses.add_statement(witness_id, "The car came from the left.")
    second = witnesses.add_statement(witness_id, "The car came from the left, at speed.")
    check("each account is stored as its own version",
          [s["version"] for s in witnesses.statements(witness_id)] == [2, 1],
          str(witnesses.statements(witness_id)))
    check("the newest account is the current one",
          witnesses.current_statement(witness_id)["statement_id"] == second)
    check("the earlier account is still readable",
          witnesses.statements(witness_id)[1]["statement_id"] == first
          and witnesses.statements(witness_id)[1]["superseded_at"] is not None)
    check("exactly one version is current",
          witnesses.db.scalar(
              "SELECT COUNT(*) FROM witness_statements"
              " WHERE witness_id = %s AND superseded_at IS NULL", (witness_id,)) == 1)
    check("the v1 statement column shows the latest account",
          witnesses.get(witness_id)["statement"] == "The car came from the left, at speed.",
          str(witnesses.get(witness_id)["statement"]))
    check("who took each account is recorded",
          all(s["recorded_by_user_id"] == fx.actor["user_id"]
              for s in witnesses.statements(witness_id)))
    check("a statement is written once in the audit trail",
          fx.audit_count("witness_statement", second) == 1)

    for n in range(3):
        witnesses.add_statement(witness_id, f"Follow-up account {n}.")
    every = witnesses.statements(witness_id)
    check("several accounts taken one after another each keep their own version",
          [s["version"] for s in every] == [5, 4, 3, 2, 1]
          and sum(1 for s in every if s["superseded_at"] is None) == 1,
          str([(s["version"], s["superseded_at"]) for s in every]))


def test_the_first_account_from_the_old_screen_becomes_version_one(fx: Fixtures) -> None:
    """The v1 add-witness dialog passes the statement straight in."""
    witnesses = fx.repos.witnesses
    witness_id = witnesses.create(fx.case_id, "Legacy Dialog Witness",
                                  statement="Saw the whole thing.")
    rows = witnesses.statements(witness_id)
    check("the statement given when the witness was recorded is versioned",
          len(rows) == 1 and rows[0]["version"] == 1
          and rows[0]["statement_body"] == "Saw the whole thing.", str(rows))
    witnesses.update(witness_id, statement="Saw it, but it was raining.")
    rows = witnesses.statements(witness_id)
    check("editing the statement adds a version instead of overwriting",
          len(rows) == 2 and rows[0]["version"] == 2
          and rows[1]["statement_body"] == "Saw the whole thing.", str(rows))


def test_a_failed_statement_leaves_the_previous_version_current(fx: Fixtures) -> None:
    witness_id = fx.repos.witnesses.create(fx.case_id, "Unlucky Witness")
    first = fx.repos.witnesses.add_statement(witness_id, "Still the current account.")
    ghost = Repositories(fx.db, {"user_id": 999999, "username": "ghost", "role": "admin"})
    try:
        ghost.witnesses.add_statement(witness_id, "This one cannot be attributed.")
        check("the unattributable statement was refused", False, "it was accepted")
    except DatabaseError:
        check("the unattributable statement was refused", True)
    rows = fx.repos.witnesses.statements(witness_id)
    check("the earlier version was never superseded",
          len(rows) == 1 and rows[0]["statement_id"] == first
          and rows[0]["superseded_at"] is None, str(rows))
    check("the witness profile still shows the earlier account",
          fx.repos.witnesses.get(witness_id)["statement"] == "Still the current account.")


def test_reliability_is_an_authorized_human_decision(fx: Fixtures) -> None:
    print("Witness reliability")
    witnesses = fx.repos.witnesses
    witness_id = witnesses.create(fx.case_id, "Assessed Witness")
    check("a new witness is not assessed by the system",
          witnesses.get(witness_id)["reliability_remark"] is None)

    witnesses.assess_reliability(witness_id, True, "Consistent with the CCTV.")
    row = witnesses.get(witness_id)
    check("an officer's assessment is stored",
          bool(row["is_reliable"]) and row["reliability_remark"] == "Consistent with the CCTV.")
    check("the assessment is attributed to the person who made it",
          row["assessed_by_user_id"] == fx.actor["user_id"] and row["assessed_at"] is not None)
    check("the assessment is in the audit trail",
          fx.audit_count("witness", witness_id) >= 2, str(fx.audit_count("witness", witness_id)))

    refused("a viewer cannot assess a witness",
            lambda: fx.repos_as("viewer").witnesses.assess_reliability(witness_id, False, "x"))


def test_interviews_can_be_scheduled_and_held(fx: Fixtures) -> None:
    print("Witness interviews")
    witnesses = fx.repos.witnesses
    witness_id = witnesses.create(fx.case_id, "Interviewed Witness")
    interview_id = witnesses.schedule_interview(
        witness_id, "2026-05-04 11:00:00", location="Station interview room 2",
        interviewer_officer_id=fx.officer["officer_id"], notes="Bring the case file")
    scheduled = witnesses.interviews(witness_id)
    check("the interview is booked against the witness",
          len(scheduled) == 1 and scheduled[0]["interview_id"] == interview_id
          and scheduled[0]["outcome"] == "scheduled", str(scheduled))
    check("the booking names the interviewing officer",
          bool(scheduled) and scheduled[0]["interviewer_name"] == fx.officer["name"],
          str(scheduled))

    witnesses.mark_interview(interview_id, "completed",
                             held_datetime="2026-05-04 11:20:00", duration_minutes=45,
                             notes="Account matches the first statement.")
    held = witnesses.interviews(witness_id)[0]
    check("the result is recorded on the same booking",
          held["outcome"] == "completed" and held["duration_minutes"] == 45
          and str(held["held_datetime"]) == "2026-05-04 11:20:00", str(held))

    witnesses.delete_interview(interview_id)
    check("a booking can be cancelled", witnesses.interviews(witness_id) == [])


def test_protection_records_and_the_flag_move_together(fx: Fixtures) -> None:
    print("Witness protection")
    witnesses = fx.repos.witnesses
    witness_id = witnesses.create(fx.case_id, "Protected Witness")
    protection_id = witnesses.add_protection(
        witness_id, "Escort to court", "Threats reported to the SHO",
        "2026-05-01", end_date="2026-08-01", review_datetime="2026-06-01 10:00:00",
        remarks="Two officers per trip")
    rows = witnesses.protection_records(witness_id)
    check("the measure is recorded",
          len(rows) == 1 and rows[0]["measure"] == "Escort to court"
          and rows[0]["status"] == "active", str(rows))
    check("the authorisation is attributed",
          bool(rows) and rows[0]["authorised_by"] == fx.actor["username"], str(rows))
    check("the witness is flagged as needing protection",
          bool(witnesses.get(witness_id)["protection_required"]))

    witnesses.update_protection(protection_id, status="revoked")
    check("revoking the last active measure clears the flag",
          not witnesses.get(witness_id)["protection_required"]
          and witnesses.protection_records(witness_id)[0]["status"] == "revoked")

    second = witnesses.add_protection(witness_id, "Safe house", "Court order", "2026-06-01")
    check("a new measure sets the flag again",
          bool(witnesses.get(witness_id)["protection_required"]))
    witnesses.delete_protection(second)
    check("deleting it clears the flag", not witnesses.get(witness_id)["protection_required"])


def test_a_viewer_cannot_read_a_confidential_witness(fx: Fixtures) -> None:
    print("Witness privacy")
    witnesses = fx.repos.witnesses
    secret_id = witnesses.create(fx.case_id, "Hidden Helper", phone="9222200000",
                                 address="An address", email="secret@example.test",
                                 confidentiality_level="restricted", protection_required=True)
    open_id = witnesses.create(fx.case_id, "Ordinary Witness", phone="9333300000")

    viewer = fx.repos_as("viewer").witnesses
    row = viewer.get(secret_id)
    check("a viewer does not learn who a confidential witness is",
          row["name"] == RESTRICTED and row["phone"] == RESTRICTED
          and row["address"] == RESTRICTED and row["email"] == RESTRICTED,
          f"name={row['name']} phone={row['phone']} email={row['email']}")
    check("the row stays in the register so the case still shows a witness exists",
          row["witness_id"] == secret_id and row["case_id"] == fx.case_id)
    ordinary = viewer.get(open_id)
    check("an ordinary witness is still named to a viewer",
          ordinary["name"] == "Ordinary Witness", f"name={ordinary['name']}")
    check("but a viewer is not given their contact details either",
          ordinary["phone"] == RESTRICTED, f"phone={ordinary['phone']}")
    check("the officer sees the confidential witness in full",
          witnesses.get(secret_id)["name"] == "Hidden Helper")
    listed = {w["witness_id"]: w for w in viewer.list_all()}
    check("the register masks the confidential witness too",
          listed[secret_id]["name"] == RESTRICTED
          and listed[open_id]["name"] == "Ordinary Witness",
          f"confidential={listed[secret_id]['name']} ordinary={listed[open_id]['name']}")
    check("a viewer cannot search for a confidential witness by name",
          viewer.list_all(search="Hidden Helper") == [])
    check("the case tab masks them as well",
          all(w["name"] != "Hidden Helper" for w in viewer.for_case(fx.case_id)))


def test_a_protected_witness_record_is_for_staff(fx: Fixtures) -> None:
    witnesses = fx.repos.witnesses
    witness_id = witnesses.create(fx.case_id, "Restricted Statements Witness",
                                  confidentiality_level="confidential")
    witnesses.add_statement(witness_id, "What I saw that night.")
    refused("a viewer cannot read a confidential witness's statements",
            lambda: fx.repos_as("viewer").witnesses.statements(witness_id))
    refused("a viewer cannot read protection records",
            lambda: fx.repos_as("viewer").witnesses.protection_records(witness_id))
    check("an officer reads them both",
          len(witnesses.statements(witness_id)) == 1
          and witnesses.protection_records(witness_id) == [])


# ---------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------
def _item(fx: Fixtures, **fields) -> int:
    """Record one item with the v1 arguments already filled in."""
    values: dict = {"seized_under": "Section 102 CrPC"}
    values.update(fields)
    return fx.repos.evidence.create(
        fx.case_id, "physical", "Recovered from the scene.",
        fx.officer["officer_id"], "2026-04-02 09:00:00", **values)


def _file(folder: Path, name: str, payload: bytes) -> Path:
    path = folder / name
    path.write_bytes(payload)
    return path


def test_evidence_profile_stores_the_new_fields(fx: Fixtures) -> None:
    print("Evidence profile")
    evidence = fx.repos.evidence
    item_id = _item(fx, item_name="Motorbike number plate",
                    evidence_category="trace",
                    detailed_description="Bent plate with blue paint transfer.",
                    collection_location="Km 14, Outer Ring Road",
                    collection_method="Lifted from the carriageway",
                    condition="damaged", packaging_type="Paper envelope",
                    seal_number="SEAL-PL-0001", storage_location="Sealed store, rack B")
    row = evidence.get(item_id)
    check("the item is named, described and categorised",
          row["item_name"] == "Motorbike number plate"
          and row["evidence_category"] == "trace"
          and row["detailed_description"].startswith("Bent plate"))
    check("how and where it was seized is recorded",
          row["collection_location"].startswith("Km 14")
          and row["collection_method"].startswith("Lifted")
          and row["condition"] == "damaged"
          and row["packaging_type"] == "Paper envelope")
    check("a reference number is issued to the item",
          str(row["evidence_ref"]).startswith("EV/2026/"), str(row["evidence_ref"]))
    check("a new item starts its life seized and unexamined",
          row["evidence_status"] == "seized"
          and row["forensic_status"] == "not_required")
    check("the columns the old screen used still work",
          row["type"] == "physical" and row["seized_under"] == "Section 102 CrPC"
          and row["description"] == "Recovered from the scene.")

    evidence.update(item_id, item_name="Motorbike number plate (front)",
                    condition="intact", seal_number="SEAL-PL-0002")
    row = evidence.get(item_id)
    check("the profile can be edited",
          row["item_name"].endswith("(front)") and row["condition"] == "intact"
          and row["seal_number"] == "SEAL-PL-0002")
    check("an edit is recorded against the case",
          fx.audit_count("evidence", item_id, "update") == 1
          and fx.audit_for("evidence", item_id, "update")["case_id"] == fx.case_id)
    check("the register finds an item by its name",
          [e["evidence_id"] for e in evidence.list_all(case_id=fx.case_id,
                                                       search="number plate")] == [item_id])
    check("the register can be filtered by category",
          len(evidence.list_all(case_id=fx.case_id, category="trace")) == 1
          and evidence.list_all(case_id=fx.case_id, category="firearm") == [])
    check("the register can be filtered by status",
          [e["evidence_id"] for e in evidence.list_all(case_id=fx.case_id,
                                                       status="seized")] == [item_id]
          and evidence.list_all(case_id=fx.case_id, status="destroyed") == [])
    check("the case tab shows the reference alongside the item",
          [(e["item_name"], e["evidence_ref"] != None)
           for e in evidence.for_case(fx.case_id)][0][1])

    viewer = fx.repos_as("viewer").evidence
    refused("a viewer cannot record evidence",
            lambda: viewer.create(fx.case_id, "physical", "No.",
                                  fx.officer["officer_id"], "2026-04-02 09:00:00"))
    refused("a viewer cannot edit evidence",
            lambda: viewer.update(item_id, item_name="Rewritten"))
    refused("a viewer cannot delete evidence", lambda: viewer.delete(item_id))
    refused("a field the table does not have is refused",
            lambda: evidence.update(item_id, is_reliable=True), DatabaseError)
    refused("a field the table does not have is refused on create too",
            lambda: _item(fx, halflife="none"), DatabaseError)


def test_two_items_cannot_share_a_reference_or_a_seal(fx: Fixtures) -> None:
    print("Evidence identity")
    evidence = fx.repos.evidence
    first = _item(fx, item_name="First knife", seal_number="SEAL-KN-0001")
    second = _item(fx, item_name="Second knife", seal_number="SEAL-KN-0002")
    refs = {evidence.get(first)["evidence_ref"], evidence.get(second)["evidence_ref"]}
    check("each item gets a reference of its own", len(refs) == 2, str(sorted(refs)))
    refused("the reference number is not something a user can rewrite",
            lambda: evidence.update(first, evidence_ref="EV/1999/000001"), DatabaseError)

    before = fx.count("evidence")
    refused("a seal number already in use is refused",
            lambda: _item(fx, item_name="Copycat knife", seal_number="SEAL-KN-0001"),
            DatabaseError)
    check("the refused item left no row behind", fx.count("evidence") == before)


def test_recording_evidence_opens_the_custody_history(fx: Fixtures) -> None:
    print("Custody history")
    evidence = fx.repos.evidence
    item_id = _item(fx, item_name="Custody start")
    history = evidence.custody_history(item_id)
    check("collection is the first link in the chain",
          len(history) == 1 and history[0]["sequence_no"] == 1
          and history[0]["event_type"] == "collected", f"{len(history)} entries")
    check("it names the officer who took it in",
          history[0]["to_officer_id"] == fx.officer["officer_id"])
    check("it is dated from the collection",
          str(history[0]["occurred_at"]) == "2026-04-02 09:00:00",
          str(history[0]["occurred_at"]))
    check("it is attributed to the user who recorded the item",
          history[0]["recorded_by_user_id"] == fx.actor["user_id"])
    check("and the item itself is in the audit trail",
          fx.audit_count("evidence", item_id, "create") == 1)


def test_custody_transfers_are_appended_in_order(fx: Fixtures) -> None:
    evidence = fx.repos.evidence
    item_id = _item(fx, item_name="Laptop", storage_location="Memorandum room")

    evidence.record_transfer(item_id, to_officer_id=fx.other_officer["officer_id"],
                             purpose="For forensic imaging",
                             occurred_at="2026-04-03 11:30:00")
    history = evidence.custody_history(item_id)
    check("the transfer is the second link",
          len(history) == 2 and history[1]["sequence_no"] == 2
          and history[1]["event_type"] == "transferred", f"{len(history)} entries")
    check("it records who gave the item up and who took it over",
          history[1]["from_officer_id"] == fx.officer["officer_id"]
          and history[1]["to_officer_id"] == fx.other_officer["officer_id"])
    check("and why it moved", history[1]["purpose"] == "For forensic imaging")

    evidence.record_transfer(item_id, event_type="issued_to_court",
                             purpose="Produced before the magistrate",
                             occurred_at="2026-04-10 10:00:00", seal_intact=False,
                             status="issued_to_court")
    history = evidence.custody_history(item_id)
    check("a third link follows the second",
          len(history) == 3 and history[2]["sequence_no"] == 3
          and history[2]["event_type"] == "issued_to_court", f"{len(history)} entries")
    check("it carries on from whoever held the item",
          history[2]["from_officer_id"] == fx.other_officer["officer_id"])
    check("a seal broken in transit is recorded as broken",
          not history[2]["seal_intact"])
    check("the item's own status moved with it",
          evidence.get(item_id)["evidence_status"] == "issued_to_court")
    check("each movement is in the audit trail",
          fx.audit_count("evidence", item_id, "status_change") == 2)

    refused("a viewer cannot move evidence",
            lambda: fx.repos_as("viewer").evidence.record_transfer(
                item_id, purpose="No", occurred_at="2026-04-11 10:00:00"))


def test_the_custody_history_cannot_be_rewritten(fx: Fixtures) -> None:
    item_id = _item(fx, item_name="Unalterable")
    custody_id = fx.repos.evidence.custody_history(item_id)[0]["custody_id"]
    before = fx.db.query_one(
        "SELECT purpose FROM evidence_custody_log WHERE custody_id = %s", (custody_id,))

    refused("the database refuses to edit a custody entry",
            lambda: fx.db.execute(
                "UPDATE evidence_custody_log SET purpose = 'Rewritten' WHERE custody_id = %s",
                (custody_id,)), DatabaseError)
    refused("the database refuses to delete a custody entry",
            lambda: fx.db.execute(
                "DELETE FROM evidence_custody_log WHERE custody_id = %s", (custody_id,)),
            DatabaseError)
    after = fx.db.query_one(
        "SELECT purpose FROM evidence_custody_log WHERE custody_id = %s", (custody_id,))
    check("the entry still says what it said", before == after, str(after))


def test_a_failed_custody_update_leaves_no_entry_behind(fx: Fixtures) -> None:
    evidence = fx.repos.evidence
    item_id = _item(fx, item_name="Rollback")
    before = fx.count("evidence_custody_log")

    refused("a transfer to a status the database does not know is refused",
            lambda: evidence.record_transfer(item_id, purpose="Nowhere",
                                             occurred_at="2026-04-04 09:00:00",
                                             status="melted"), DatabaseError)
    check("the custody log did not gain the first half of that write",
          fx.count("evidence_custody_log") == before,
          f"{fx.count('evidence_custody_log')} entries, was {before}")
    check("the item is still where it was",
          evidence.get(item_id)["evidence_status"] == "seized")
    check("and no audit entry claims a change that did not happen",
          fx.audit_count("evidence", item_id, "status_change") == 0)


def test_forensic_examinations_are_sent_and_reported(fx: Fixtures) -> None:
    print("Forensics")
    evidence = fx.repos.evidence
    item_id = _item(fx, item_name="Blood vial", evidence_category="biological")

    examination_id = evidence.send_to_forensics(
        item_id, laboratory_name="FSL Gandhi Hospital", examination_type="DNA profiling",
        sent_datetime="2026-04-05 11:00:00")
    row = evidence.get(item_id)
    check("sending an item to a laboratory is recorded on the item",
          row["forensic_status"] == "sent"
          and row["laboratory_name"] == "FSL Gandhi Hospital")
    opened = evidence.examinations(item_id)
    check("the request has a reference of its own",
          len(opened) == 1 and bool(opened[0]["request_no"]),
          str([o["request_no"] for o in opened]))
    check("it is open until the laboratory reports",
          opened[0]["result_status"] == "pending"
          and opened[0]["completed_datetime"] is None
          and opened[0]["examination_type"] == "DNA profiling")

    evidence.record_examination_result(
        examination_id, result_status="incriminating",
        result_summary="Profile matches the suspect.",
        completed_datetime="2026-04-20 15:00:00", examiner_name="Dr A. Rao")
    reported = evidence.examinations(item_id)[0]
    check("the result closes that request",
          reported["result_status"] == "incriminating"
          and reported["completed_datetime"] is not None
          and reported["examiner_name"] == "Dr A. Rao")
    check("the item carries the outcome",
          evidence.get(item_id)["forensic_status"] == "reported"
          and evidence.get(item_id)["examination_result"] == "Profile matches the suspect.")
    check("the register can be filtered to the items with a report",
          item_id in [e["evidence_id"]
                      for e in evidence.list_all(forensic_status="reported")])
    check("the handover to the laboratory was a link in the chain",
          [h["event_type"] for h in evidence.custody_history(item_id)]
          == ["collected", "transferred"]
          and evidence.custody_history(item_id)[1]["purpose"]
          .startswith("Forensic examination"),
          str([h["event_type"] for h in evidence.custody_history(item_id)]))

    second_id = evidence.send_to_forensics(
        item_id, laboratory_name="Territorial Army Lab", sent_datetime="2026-05-01 10:00:00")
    check("an item can be sent again for a second opinion",
          len(evidence.examinations(item_id)) == 2
          and evidence.get(item_id)["forensic_status"] == "sent")
    check("the two requests keep separate references",
          len({o["request_no"] for o in evidence.examinations(item_id)}) == 2)
    check("the first result is still on file",
          evidence.examinations(item_id)[0]["result_summary"]
          == "Profile matches the suspect.")

    refused("an examination cannot be completed before it was sent",
            lambda: evidence.record_examination_result(
                second_id, result_status="other", completed_datetime="2026-04-01 10:00:00"),
            DatabaseError)
    check("the refused result left that request open",
          evidence.examinations(item_id)[1]["result_status"] == "pending")
    check("and did not mark the item as reported",
          evidence.get(item_id)["forensic_status"] == "sent")
    refused("a viewer cannot send evidence to a laboratory",
            lambda: fx.repos_as("viewer").evidence.send_to_forensics(
                item_id, laboratory_name="No", sent_datetime="2026-05-02 10:00:00"))
    check("the forensic work is in the audit trail",
          fx.audit_count("evidence", item_id, "status_change") >= 2)


def test_an_attachment_is_validated_hashed_and_kept(fx: Fixtures) -> None:
    print("Evidence attachments")
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp)
        store = source / "store"
        evidence = EvidenceRepository(fx.db, fx.actor, files_dir=store,
                                      max_file_bytes=1000)
        item_id = _item(fx, item_name="CCTV clip", evidence_category="digital")
        png = b"\x89PNG\r\n\x1a\n" + b"x" * 200

        attachment_id = evidence.add_attachment(
            item_id, _file(source, "scene.png", png), notes="Still from the clip")
        row = evidence.attachments(item_id)[0]
        digest = hashlib.sha256(png).hexdigest()
        check("the file is recorded with its hash and size",
              row["sha256"] == digest and row["size_bytes"] == len(png),
              f"sha256={row['sha256'][:12]}… size={row['size_bytes']}")
        check("the original name is kept for display",
              row["original_name"] == "scene.png")
        check("a copy is filed under the evidence store",
              (store / row["stored_path"]).is_file(), row["stored_path"])
        check("nothing is left in the folder it came from",
              row["stored_path"] != str(source / "scene.png"))
        check("the item's own hash is taken from its first original",
              evidence.get(item_id)["digital_hash_sha256"] == digest)
        check("the upload is in the audit trail",
              fx.audit_for("evidence_attachment", attachment_id, "file_attach") is not None)

        refused("a file type that is not evidence is refused",
                lambda: evidence.add_attachment(
                    item_id, _file(source, "malware.exe", b"MZ" * 100)), DatabaseError)
        refused("an empty file is refused",
                lambda: evidence.add_attachment(
                    item_id, _file(source, "nothing.pdf", b"")), DatabaseError)
        refused("a file larger than the limit is refused",
                lambda: evidence.add_attachment(
                    item_id, _file(source, "huge.pdf", b"y" * 5000)), DatabaseError)
        check("a refused upload leaves nothing recorded",
              len(evidence.attachments(item_id)) == 1)
        check("and nothing written into the store",
              not [p for p in store.rglob("*") if p.suffix in (".exe", ".bin")],
              str([p.name for p in store.rglob("*")]))

        refused("the same bytes cannot be attached to the item twice",
                lambda: evidence.add_attachment(item_id, source / "scene.png"),
                DatabaseError)

        other_id = evidence.add_attachment(
            item_id, _file(source, "scene.png", b"\x89PNG\r\n\x1a\n" + b"y" * 300))
        listed = evidence.attachments(item_id)
        check("a different file is kept beside it", len(listed) == 2, f"{len(listed)} files")
        check("the first file was not overwritten",
              (store / listed[0]["stored_path"]).read_bytes() == png)
        check("the two are held at different paths",
              listed[0]["stored_path"] != listed[1]["stored_path"])

        check("the recorded hash still matches the bytes on file",
              evidence.verify_attachment(attachment_id) is True)
        (store / listed[0]["stored_path"]).write_bytes(b"tampered")
        results = evidence.verify_integrity(item_id)
        check("tampering with a stored file is caught",
              results[attachment_id] is False and results[other_id] is True, str(results))

        refused("a viewer cannot attach a file",
                lambda: EvidenceRepository(fx.db, fx.actor_as("viewer"), files_dir=store)
                .add_attachment(item_id, source / "scene.png"))
        check("a viewer can still see what is filed, and its hash",
              [a["sha256"] for a in fx.repos_as("viewer").evidence.attachments(item_id)]
              == [a["sha256"] for a in evidence.attachments(item_id)])


TESTS = [
    test_transaction_rolls_back_on_failure,    test_transaction_commits_on_success,
    test_transaction_rolls_back_when_the_database_rejects_a_later_write,
    test_connection_works_normally_after_a_transaction,
    test_a_nested_transaction_joins_the_outer_one,
    test_victim_profile_stores_the_new_fields,
    test_victim_changes_are_logged,
    test_a_viewer_cannot_change_victim_records,
    test_a_viewer_sees_masked_victim_details,
    test_victim_records_are_kept_beside_the_profile,
    test_the_database_refuses_an_impossible_medical_record,
    test_medical_and_compensation_records_are_for_staff_only,
    test_a_victim_is_not_left_half_written_when_the_trail_fails,
    test_witness_profile_stores_the_new_fields,
    test_statement_versions_are_preserved,
    test_the_first_account_from_the_old_screen_becomes_version_one,
    test_a_failed_statement_leaves_the_previous_version_current,
    test_reliability_is_an_authorized_human_decision,
    test_interviews_can_be_scheduled_and_held,
    test_protection_records_and_the_flag_move_together,
    test_a_viewer_cannot_read_a_confidential_witness,
    test_a_protected_witness_record_is_for_staff,
    test_evidence_profile_stores_the_new_fields,
    test_two_items_cannot_share_a_reference_or_a_seal,
    test_recording_evidence_opens_the_custody_history,
    test_custody_transfers_are_appended_in_order,
    test_the_custody_history_cannot_be_rewritten,
    test_a_failed_custody_update_leaves_no_entry_behind,
    test_forensic_examinations_are_sent_and_reported,
    test_an_attachment_is_validated_hashed_and_kept,
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the repository layer.")
    parser.add_argument("--db", metavar="SCHEMA",
                        help="test this schema instead of the database in config.ini")
    parser.add_argument("--only", metavar="SUBSTRING",
                        help="run the tests whose name contains this text")
    args = parser.parse_args()

    config = load_config()
    if args.db:
        config["database"]["database"] = args.db

    db = Database(config)
    print(f"Testing {db.config['database'].get('database')}\n")
    fx = Fixtures(db)
    print(f"Using case {fx.case_id}\n")
    try:
        for test in TESTS:
            if args.only and args.only not in test.__name__:
                continue
            try:
                test(fx)
            except Exception as exc:
                global FAILED
                FAILED += 1
                print(f"  FAIL {test.__name__} raised {type(exc).__name__}: {exc}")
    finally:
        fx.cleanup()
        db.close()

    print(f"\n{PASSED} passed, {FAILED} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
