"""People attached to a case: suspects, victims and witnesses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.auth import Repository
from app.db.connection import Database, DatabaseError
from app.db.privacy import (
    PRIVILEGED_ROLES, is_confidential, is_restricted, mask_row, mask_rows,
)


class SuspectRepository(Repository):
    def __init__(self, db: Database, actor: dict | None = None) -> None:
        super().__init__(db, actor)

    def for_case(self, case_id: int) -> list[dict]:
        return self.db.query(
            "SELECT * FROM v_suspect_summary WHERE case_id = %s ORDER BY name",
            (case_id,),
        )

    def list_all(self, status: str | None = None, search: str | None = None) -> list[dict]:
        clauses = []
        params: list = []
        if status:
            clauses.append("s.status = %s")
            params.append(status)
        if search:
            clauses.append("(s.name LIKE %s OR s.phone LIKE %s OR c.case_no LIKE %s)")
            params.extend([f"%{search}%"] * 3)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.db.query(
            f"""
            SELECT s.*, c.case_no, c.status AS case_status, c.category AS case_category,
                   (SELECT COUNT(*) FROM arrests a WHERE a.suspect_id = s.suspect_id)
                       AS arrest_count,
                   (SELECT COALESCE(SUM(cv.imprisonment_years), 0)
                      FROM convictions cv WHERE cv.suspect_id = s.suspect_id)
                       AS total_sentence_years
            FROM suspects s
            JOIN crime_cases c ON c.case_id = s.case_id
            {where}
            ORDER BY s.created_at DESC
            """,
            params,
        )

    def get(self, suspect_id: int) -> dict | None:
        return self.db.query_one(
            "SELECT * FROM suspects WHERE suspect_id = %s", (suspect_id,)
        )

    def create(self, case_id: int, name: str, *, alias: str | None = None,
               date_of_birth: str | None = None, gender: str = "unknown",
               address: str | None = None, phone: str | None = None,
               identifying_marks: str | None = None, status: str = "wanted") -> int:
        return self.execute(
            """
            INSERT INTO suspects (case_id, name, alias, date_of_birth, gender,
                                  address, phone, identifying_marks, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (case_id, name.strip(), alias, date_of_birth, gender, address,
             phone, identifying_marks, status),
        )

    def update(self, suspect_id: int, **fields) -> None:
        allowed = {"name", "alias", "date_of_birth", "gender", "address",
                   "phone", "identifying_marks", "status"}
        sets, values = [], []
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key} = %s")
                values.append(value)
        if not sets:
            return
        values.append(suspect_id)
        self.execute(f"UPDATE suspects SET {', '.join(sets)} WHERE suspect_id = %s", values)

    def delete(self, suspect_id: int) -> None:
        self.execute("DELETE FROM suspects WHERE suspect_id = %s", (suspect_id,))


# The columns each victim record owns. They are the whitelist for an INSERT
# or an UPDATE, so a stray keyword from the screen can never reach the SQL.
VICTIM_PROFILE = frozenset({
    "name", "age", "gender", "phone", "address", "injury_level", "statement",
    "date_of_birth", "email", "occupation", "national_id",
    "emergency_contact_name", "emergency_contact_phone", "relationship_to_accused",
    "incident_datetime", "incident_location", "medical_assistance_status",
    "hospital_name", "hospital_reference", "special_assistance", "confidentiality_level",
})

# Personal detail about a victim that a viewer is not entitled to read.
VICTIM_RESTRICTED = frozenset({
    "phone", "address", "email", "national_id", "date_of_birth",
    "emergency_contact_name", "emergency_contact_phone",
    "hospital_name", "hospital_reference",
})

VICTIM_MEDICAL_FIELDS = frozenset({
    "facility", "treating_doctor", "treatment_type", "description",
    "admitted_datetime", "discharged_datetime", "cost_incurred",
    "medical_report_path", "remarks",
})

VICTIM_CONTACT_FIELDS = frozenset({
    "contact_type", "contact_datetime", "made_by_officer_id", "purpose",
    "outcome", "follow_up_required", "follow_up_datetime",
})

VICTIM_COMPENSATION_FIELDS = frozenset({
    "scheme_name", "compensation_type", "application_date", "awarded_amount",
    "received_amount", "status", "sanctioning_authority", "order_reference",
    "remarks",
})


class VictimRepository(Repository):
    """The victim register, plus the medical, contact and compensation records."""

    def __init__(self, db: Database, actor: dict | None = None) -> None:
        super().__init__(db, actor)

    # -- reading ------------------------------------------------------
    def for_case(self, case_id: int) -> list[dict]:
        rows = self.db.query(
            "SELECT * FROM victims WHERE case_id = %s ORDER BY name", (case_id,)
        )
        return mask_rows(self.actor, rows, VICTIM_RESTRICTED)

    def list_all(self, search: str | None = None, *, case_id: int | None = None,
                 injury_level: str | None = None, gender: str | None = None,
                 medical_assistance_status: str | None = None,
                 confidentiality_level: str | None = None) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if search:
            columns = ["v.name", "c.case_no"]
            if not is_restricted(self.actor):
                # A viewer must not be able to probe a hidden address.
                columns.append("v.address")
            clauses.append("(" + " OR ".join(f"{column} LIKE %s" for column in columns) + ")")
            params.extend([f"%{search}%"] * len(columns))
        for column, value in (("case_id", case_id), ("injury_level", injury_level),
                              ("gender", gender),
                              ("medical_assistance_status", medical_assistance_status),
                              ("confidentiality_level", confidentiality_level)):
            if value:
                clauses.append(f"v.{column} = %s")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.db.query(
            f"""
            SELECT v.*, c.case_no, c.status AS case_status
            FROM victims v JOIN crime_cases c ON c.case_id = v.case_id
            {where} ORDER BY v.created_at DESC
            """,
            params,
        )
        return mask_rows(self.actor, rows, VICTIM_RESTRICTED)

    def get(self, victim_id: int) -> dict | None:
        row = self.db.query_one(
            "SELECT * FROM victims WHERE victim_id = %s", (victim_id,)
        )
        return mask_row(self.actor, row, VICTIM_RESTRICTED)

    # -- the profile --------------------------------------------------
    def create(self, case_id: int, name: str, **profile) -> int:
        """Record a victim.

        Anything the victim profile owns can be passed by name - age,
        injury_level, date_of_birth, national_id, the emergency contact,
        the hospital details and so on. Fields that are left out keep
        their database defaults.
        """
        return self.create_record(
            "victims", "victim", editable=VICTIM_PROFILE,
            fixed={"case_id": case_id, "name": name.strip()}, values=profile,
            summary=f"{name.strip()} recorded as a victim", case_id=case_id,
        )

    def update(self, victim_id: int, **fields) -> None:
        self.edit_record(
            "victims", "victim", "victim_id", victim_id, VICTIM_PROFILE, fields,
            case_id=self.parent_case("victims", "victim_id", victim_id),
        )

    def delete(self, victim_id: int) -> None:
        victim = self.get(victim_id)
        self.remove_record(
            "victims", "victim", "victim_id", victim_id,
            summary=f"{victim['name']} removed from the victim register" if victim else None,
            case_id=victim["case_id"] if victim else None,
        )

    # -- medical records ----------------------------------------------
    def add_medical_record(self, victim_id: int, facility: str, treatment_type: str,
                           **fields) -> int:
        self.guard_fields(VICTIM_MEDICAL_FIELDS - {"facility", "treatment_type"},
                          fields, "medical record")
        return self.create_record(
            "victim_medical_records", "victim_medical_record",
            editable=VICTIM_MEDICAL_FIELDS,
            fixed={"victim_id": victim_id, "facility": facility,
                   "treatment_type": treatment_type,
                   "recorded_by_user_id": self.user_id()},
            values=fields,
            summary=f"{treatment_type} at {facility}",
            case_id=self.parent_case("victims", "victim_id", victim_id),
        )

    def medical_records(self, victim_id: int) -> list[dict]:
        """Treatment details are for the staff working the case."""
        self.require(*PRIVILEGED_ROLES)
        return self.db.query(
            """
            SELECT m.*, u.username AS recorded_by
            FROM victim_medical_records m
            LEFT JOIN users u ON u.user_id = m.recorded_by_user_id
            WHERE m.victim_id = %s
            ORDER BY m.admitted_datetime DESC, m.medical_record_id DESC
            """,
            (victim_id,),
        )

    def update_medical_record(self, medical_record_id: int, **fields) -> None:
        self.edit_record(
            "victim_medical_records", "victim_medical_record",
            "medical_record_id", medical_record_id, VICTIM_MEDICAL_FIELDS, fields,
            case_id=self.case_of_child("victim_medical_records", "medical_record_id",
                                       "victim_id", "victims", "victim_id",
                                       medical_record_id),
        )

    def delete_medical_record(self, medical_record_id: int) -> None:
        self.remove_record(
            "victim_medical_records", "victim_medical_record",
            "medical_record_id", medical_record_id,
            summary="Medical record deleted",
            case_id=self.case_of_child("victim_medical_records", "medical_record_id",
                                       "victim_id", "victims", "victim_id",
                                       medical_record_id),
        )

    # -- contact log ---------------------------------------------------
    def add_contact(self, victim_id: int, contact_type: str, contact_datetime: str,
                    **fields) -> int:
        self.guard_fields(
            VICTIM_CONTACT_FIELDS - {"contact_type", "contact_datetime"},
            fields, "contact entry")
        return self.create_record(
            "victim_contacts", "victim_contact", editable=VICTIM_CONTACT_FIELDS,
            fixed={"victim_id": victim_id, "contact_type": contact_type,
                   "contact_datetime": contact_datetime},
            values=fields,
            summary=f"Contact with the victim ({contact_type})",
            case_id=self.parent_case("victims", "victim_id", victim_id),
        )

    def contacts(self, victim_id: int) -> list[dict]:
        return self.db.query(
            """
            SELECT k.*, o.name AS made_by_name
            FROM victim_contacts k
            LEFT JOIN officers o ON o.officer_id = k.made_by_officer_id
            WHERE k.victim_id = %s
            ORDER BY k.contact_datetime DESC
            """,
            (victim_id,),
        )

    def update_contact(self, contact_id: int, **fields) -> None:
        self.edit_record(
            "victim_contacts", "victim_contact", "contact_id", contact_id,
            VICTIM_CONTACT_FIELDS, fields,
            case_id=self.case_of_child("victim_contacts", "contact_id",
                                       "victim_id", "victims", "victim_id", contact_id),
        )

    def delete_contact(self, contact_id: int) -> None:
        self.remove_record(
            "victim_contacts", "victim_contact", "contact_id", contact_id,
            summary="Contact entry deleted",
            case_id=self.case_of_child("victim_contacts", "contact_id",
                                       "victim_id", "victims", "victim_id", contact_id),
        )

    # -- compensation --------------------------------------------------
    def add_compensation(self, victim_id: int, scheme_name: str, **fields) -> int:
        self.guard_fields(VICTIM_COMPENSATION_FIELDS - {"scheme_name"},
                          fields, "compensation record")
        return self.create_record(
            "victim_compensation", "victim_compensation",
            editable=VICTIM_COMPENSATION_FIELDS,
            fixed={"victim_id": victim_id, "scheme_name": scheme_name,
                   "recorded_by_user_id": self.user_id()},
            values=fields, summary=f"{scheme_name} compensation record",
            case_id=self.parent_case("victims", "victim_id", victim_id),
        )

    def compensation(self, victim_id: int) -> list[dict]:
        """What a victim was offered or paid is personal financial detail."""
        self.require(*PRIVILEGED_ROLES)
        return self.db.query(
            """
            SELECT p.*, u.username AS recorded_by
            FROM victim_compensation p
            LEFT JOIN users u ON u.user_id = p.recorded_by_user_id
            WHERE p.victim_id = %s
            ORDER BY p.created_at DESC
            """,
            (victim_id,),
        )

    def update_compensation(self, compensation_id: int, **fields) -> None:
        self.edit_record(
            "victim_compensation", "victim_compensation", "compensation_id",
            compensation_id, VICTIM_COMPENSATION_FIELDS, fields,
            case_id=self.case_of_child("victim_compensation", "compensation_id",
                                       "victim_id", "victims", "victim_id",
                                       compensation_id),
        )

    def delete_compensation(self, compensation_id: int) -> None:
        self.remove_record(
            "victim_compensation", "victim_compensation", "compensation_id",
            compensation_id, summary="Compensation record deleted",
            case_id=self.case_of_child("victim_compensation", "compensation_id",
                                       "victim_id", "victims", "victim_id",
                                       compensation_id),
        )


WITNESS_PROFILE = frozenset({
    "name", "phone", "address", "date_of_birth", "gender", "email", "occupation",
    "witness_type", "relationship_to_victim", "relationship_to_accused",
    "observation_datetime", "observation_location", "statement_language",
    "availability_status", "protection_required", "confidentiality_level",
})

# What a viewer may not read about an ordinary witness.
WITNESS_CONTACT = frozenset({
    "phone", "address", "email", "date_of_birth", "observation_location",
})

# What nobody outside case staff may read about a confidential witness:
# not just how to reach them, but who they are.
WITNESS_IDENTITY = WITNESS_CONTACT | frozenset({
    "name", "occupation", "relationship_to_victim", "relationship_to_accused",
})

WITNESS_INTERVIEW_FIELDS = frozenset({
    "scheduled_datetime", "held_datetime", "location", "interviewer_officer_id",
    "duration_minutes", "outcome", "notes",
})

WITNESS_PROTECTION_FIELDS = frozenset({
    "measure", "basis", "start_date", "end_date", "status", "review_datetime", "remarks",
})


class WitnessRepository(Repository):
    """Witness profiles, their statement versions, interviews and protection."""

    def __init__(self, db: Database, actor: dict | None = None) -> None:
        super().__init__(db, actor)

    # -- reading ------------------------------------------------------
    def for_case(self, case_id: int) -> list[dict]:
        rows = self.db.query(
            "SELECT * FROM witnesses WHERE case_id = %s ORDER BY name", (case_id,)
        )
        return [self._shield(row) for row in rows]

    def list_all(self, search: str | None = None, *, case_id: int | None = None,
                 witness_type: str | None = None, gender: str | None = None,
                 availability_status: str | None = None,
                 protection_required: bool | None = None,
                 confidentiality_level: str | None = None) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if search:
            columns = ["w.name", "c.case_no"]
            if not is_restricted(self.actor):
                columns += ["w.phone", "w.address"]
            clauses.append("(" + " OR ".join(f"{column} LIKE %s" for column in columns) + ")")
            params.extend([f"%{search}%"] * len(columns))
            if is_restricted(self.actor):
                # Searching must not become a way to check whether a
                # protected witness is connected to a case, so a viewer's
                # search only ever reaches witnesses who are public.
                clauses.append("w.confidentiality_level = 'public'")
        for column, value in (("case_id", case_id), ("witness_type", witness_type),
                              ("gender", gender),
                              ("availability_status", availability_status),
                              ("confidentiality_level", confidentiality_level)):
            if value:
                clauses.append(f"w.{column} = %s")
                params.append(value)
        if protection_required is not None:
            clauses.append("w.protection_required = %s")
            params.append(bool(protection_required))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.db.query(
            f"""
            SELECT w.*, c.case_no, c.status AS case_status
            FROM witnesses w JOIN crime_cases c ON c.case_id = w.case_id
            {where} ORDER BY w.created_at DESC
            """,
            params,
        )
        return [self._shield(row) for row in rows]

    def get(self, witness_id: int) -> dict | None:
        row = self.db.query_one(
            "SELECT * FROM witnesses WHERE witness_id = %s", (witness_id,)
        )
        return self._shield(row)

    def _shield(self, row: dict | None) -> dict | None:
        """Hide who a witness is from a user who is not entitled to know."""
        if row is None or not is_restricted(self.actor):
            return row
        return mask_row(self.actor, row,
                        WITNESS_IDENTITY if is_confidential(row) else WITNESS_CONTACT)

    # -- the profile --------------------------------------------------
    def create(self, case_id: int, name: str, *, statement: str | None = None,
               is_reliable: bool = True, **profile) -> int:
        """Record a witness.

        ``statement`` is how the v1 screen hands over the first account;
        it is filed as version 1 rather than as a column to be
        overwritten later. ``is_reliable`` is the note the recording
        officer makes at the same time - it is not an assessment, and the
        assessed-by columns stay empty until someone assesses the witness.
        """
        self.guard_fields(WITNESS_PROFILE, profile, "witness")
        with self.db.transaction():
            witness_id = self.insert_row(
                "witnesses",
                {"case_id": case_id, "name": name.strip(), "is_reliable": bool(is_reliable),
                 **profile})
            if statement:
                self._file_statement(witness_id, statement,
                                     language=profile.get("statement_language"))
            self.log("witness", witness_id, "create",
                     f"{name.strip()} recorded as a witness", case_id=case_id)
        return witness_id

    def update(self, witness_id: int, **fields) -> None:
        if "statement" in fields:
            statement = fields.pop("statement")
            if statement and statement.strip():
                self.add_statement(witness_id, statement)
        if fields:
            self.edit_record(
                "witnesses", "witness", "witness_id", witness_id, WITNESS_PROFILE, fields,
                case_id=self.parent_case("witnesses", "witness_id", witness_id),
            )

    def delete(self, witness_id: int) -> None:
        witness = self.get(witness_id)
        self.remove_record(
            "witnesses", "witness", "witness_id", witness_id,
            summary=f"{witness['name']} removed from the witness register" if witness else None,
            case_id=witness["case_id"] if witness else None,
        )

    # -- statements, kept as versions ---------------------------------
    def add_statement(self, witness_id: int, body: str, *, language: str | None = None,
                      remark: str | None = None) -> int:
        """File what the witness says now, without losing what they said before."""
        with self.db.transaction():
            statement_id = self._file_statement(witness_id, body, language=language,
                                                remark=remark)
            self.log("witness_statement", statement_id, "create",
                     f"Statement filed for witness {witness_id}",
                     case_id=self.parent_case("witnesses", "witness_id", witness_id))
        return statement_id

    def _file_statement(self, witness_id: int, body: str, *, language: str | None = None,
                        remark: str | None = None) -> int:
        body = (body or "").strip()
        if not body:
            raise DatabaseError("A statement has to say something.")
        witness = self.db.query_one(
            "SELECT case_id, statement_language FROM witnesses WHERE witness_id = %s",
            (witness_id,))
        if witness is None:
            raise DatabaseError("That witness is not on any case.")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.execute(
            "UPDATE witness_statements SET superseded_at = %s"
            " WHERE witness_id = %s AND superseded_at IS NULL",
            (now, witness_id),
        )
        version = int(self.db.scalar(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM witness_statements WHERE witness_id = %s",
            (witness_id,)) or 1)
        statement_id = self.insert_row(
            "witness_statements",
            {"witness_id": witness_id, "version": version, "statement_body": body,
             "language": language or witness["statement_language"] or "en",
             "recorded_by_user_id": self.user_id(), "recorded_at": now, "remark": remark},
        )
        # The v1 screens read the account straight off the witness row.
        self.update_row("witnesses", "witness_id", witness_id, {"statement"},
                        {"statement": body})
        return statement_id

    def statements(self, witness_id: int) -> list[dict]:
        """The history of a witness's accounts, newest first."""
        self.require(*PRIVILEGED_ROLES)
        return self.db.query(
            """
            SELECT s.*, u.username AS recorded_by,
                   (s.superseded_at IS NULL) AS is_current
            FROM witness_statements s
            LEFT JOIN users u ON u.user_id = s.recorded_by_user_id
            WHERE s.witness_id = %s
            ORDER BY s.version DESC
            """,
            (witness_id,),
        )

    def current_statement(self, witness_id: int) -> dict | None:
        self.require(*PRIVILEGED_ROLES)
        return self.db.query_one(
            """
            SELECT s.*, u.username AS recorded_by
            FROM witness_statements s
            LEFT JOIN users u ON u.user_id = s.recorded_by_user_id
            WHERE s.witness_id = %s AND s.superseded_at IS NULL
            """,
            (witness_id,),
        )

    # -- reliability, decided by a person -----------------------------
    def assess_reliability(self, witness_id: int, is_reliable: bool,
                           remark: str) -> None:
        """Record a person's judgement of a witness, and who made it.

        Nothing in this system decides credibility on its own: the flag
        only moves when somebody signs their name to a reason.
        """
        self.require(*PRIVILEGED_ROLES)
        remark = (remark or "").strip()
        if not remark:
            raise DatabaseError("Say why the witness is, or is not, believed.")
        case_id = self.parent_case("witnesses", "witness_id", witness_id)
        with self.db.transaction():
            self.update_row(
                "witnesses", "witness_id", witness_id,
                {"is_reliable", "reliability_remark"},
                {"is_reliable": bool(is_reliable), "reliability_remark": remark})
            self.execute(
                "UPDATE witnesses SET assessed_by_user_id = %s, assessed_at = NOW()"
                " WHERE witness_id = %s",
                (self.user_id(), witness_id),
            )
            self.log("witness", witness_id, "status_change",
                     f"{'Believed' if is_reliable else 'Not believed'}: {remark}",
                     case_id=case_id)

    # -- interviews ---------------------------------------------------
    def schedule_interview(self, witness_id: int, scheduled_datetime: str, *,
                           location: str | None = None,
                           interviewer_officer_id: int | None = None,
                           notes: str | None = None) -> int:
        return self.create_record(
            "witness_interviews", "witness_interview",
            editable=WITNESS_INTERVIEW_FIELDS,
            fixed={"witness_id": witness_id, "scheduled_datetime": scheduled_datetime,
                   "recorded_by_user_id": self.user_id()},
            values={"location": location, "interviewer_officer_id": interviewer_officer_id,
                    "notes": notes},
            summary=f"Interview booked for witness {witness_id}",
            case_id=self.parent_case("witnesses", "witness_id", witness_id),
        )

    def interviews(self, witness_id: int) -> list[dict]:
        self.require(*PRIVILEGED_ROLES)
        return self.db.query(
            """
            SELECT i.*, o.name AS interviewer_name, u.username AS recorded_by
            FROM witness_interviews i
            LEFT JOIN officers o ON o.officer_id = i.interviewer_officer_id
            LEFT JOIN users u    ON u.user_id = i.recorded_by_user_id
            WHERE i.witness_id = %s
            ORDER BY i.scheduled_datetime DESC
            """,
            (witness_id,),
        )

    def mark_interview(self, interview_id: int, outcome: str, *,
                       held_datetime: str | None = None, duration_minutes: int | None = None,
                       notes: str | None = None) -> None:
        """Record how the interview went, without wiping what was booked."""
        fields = {"outcome": outcome, "held_datetime": held_datetime,
                  "duration_minutes": duration_minutes, "notes": notes}
        self.edit_record(
            "witness_interviews", "witness_interview", "interview_id", interview_id,
            WITNESS_INTERVIEW_FIELDS,
            {key: value for key, value in fields.items() if value is not None},
            summary=f"Interview {outcome}",
            case_id=self.case_of_child("witness_interviews", "interview_id",
                                       "witness_id", "witnesses", "witness_id", interview_id),
        )

    def delete_interview(self, interview_id: int) -> None:
        self.remove_record(
            "witness_interviews", "witness_interview", "interview_id", interview_id,
            summary="Interview booking removed",
            case_id=self.case_of_child("witness_interviews", "interview_id",
                                       "witness_id", "witnesses", "witness_id", interview_id),
        )

    # -- protection ---------------------------------------------------
    def add_protection(self, witness_id: int, measure: str, basis: str, start_date: str,
                       **fields) -> int:
        self.guard_fields(
            WITNESS_PROTECTION_FIELDS - {"measure", "basis", "start_date"},
            fields, "protection record")
        with self.db.transaction():
            protection_id = self.create_record(
                "witness_protection", "witness_protection",
                editable=WITNESS_PROTECTION_FIELDS,
                fixed={"witness_id": witness_id, "measure": measure, "basis": basis,
                       "start_date": start_date,
                       "authorised_by_user_id": self.user_id()},
                values=fields, summary=f"Protection ordered: {measure}",
                case_id=self.parent_case("witnesses", "witness_id", witness_id),
            )
            self._sync_protection_flag(witness_id)
        return protection_id

    def protection_records(self, witness_id: int) -> list[dict]:
        """Who is being protected, and why, is restricted to case staff."""
        self.require(*PRIVILEGED_ROLES)
        return self.db.query(
            """
            SELECT p.*, u.username AS authorised_by
            FROM witness_protection p
            LEFT JOIN users u ON u.user_id = p.authorised_by_user_id
            WHERE p.witness_id = %s
            ORDER BY p.start_date DESC
            """,
            (witness_id,),
        )

    def update_protection(self, protection_id: int, **fields) -> None:
        witness_id = self.db.scalar(
            "SELECT witness_id FROM witness_protection WHERE protection_id = %s",
            (protection_id,))
        with self.db.transaction():
            self.edit_record(
                "witness_protection", "witness_protection", "protection_id", protection_id,
                WITNESS_PROTECTION_FIELDS, fields,
                case_id=self.parent_case("witnesses", "witness_id", witness_id)
                if witness_id else None,
            )
            if witness_id:
                self._sync_protection_flag(witness_id)

    def delete_protection(self, protection_id: int) -> None:
        witness_id = self.db.scalar(
            "SELECT witness_id FROM witness_protection WHERE protection_id = %s",
            (protection_id,))
        with self.db.transaction():
            self.remove_record(
                "witness_protection", "witness_protection", "protection_id", protection_id,
                summary="Protection record removed",
                case_id=self.parent_case("witnesses", "witness_id", witness_id)
                if witness_id else None,
            )
            if witness_id:
                self._sync_protection_flag(witness_id)

    def _sync_protection_flag(self, witness_id: int) -> None:
        """The witness needs protection when an active order says so."""
        active = self.db.scalar(
            "SELECT COUNT(*) FROM witness_protection WHERE witness_id = %s AND status = 'active'",
            (witness_id,))
        self.update_row("witnesses", "witness_id", witness_id, {"protection_required"},
                        {"protection_required": bool(active)})
