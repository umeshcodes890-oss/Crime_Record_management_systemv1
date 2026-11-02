"""Crime cases: filing, searching, status workflow and offences."""

from __future__ import annotations

import json
from typing import Any

from app.db.auth import ROLE_ADMIN, Repository
from app.db.connection import Database, DatabaseError


class CaseRepository(Repository):
    def __init__(self, db: Database, actor: dict | None = None) -> None:
        super().__init__(db, actor)

    # -- reads --------------------------------------------------------
    def search(
        self,
        *,
        case_no: str | None = None,
        station_id: int | None = None,
        officer_id: int | None = None,
        status: str | None = None,
        category: str | None = None,
        section_id: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        text: str | None = None,
        limit: int | None = 500,
    ) -> list[dict]:
        rows = self.db.call(
            "sp_search_cases",
            [case_no, station_id, officer_id, status, category, section_id,
             from_date, to_date, text, limit],
        )
        return rows

    def get(self, case_id: int) -> dict | None:
        rows = self.db.query(
            "SELECT * FROM v_case_overview WHERE case_id = %s", (case_id,)
        )
        return rows[0] if rows else None

    def recent(self, limit: int = 8) -> list[dict]:
        return self.db.query(
            "SELECT * FROM v_case_overview ORDER BY occurrence_datetime DESC LIMIT %s",
            (limit,),
        )

    def offences(self, case_id: int) -> list[dict]:
        return self.db.query(
            """
            SELECT co.case_id, co.section_id, co.accused_role, co.added_at,
                   sec.law_code, sec.section_no, sec.offence_name, sec.category,
                   sec.severity, sec.min_imprisonment_yrs, sec.max_imprisonment_yrs,
                   sec.fine_cap
            FROM case_offences co
            JOIN offence_sections sec ON sec.section_id = co.section_id
            WHERE co.case_id = %s
            ORDER BY sec.law_code, CAST(sec.section_no AS UNSIGNED)
            """,
            (case_id,),
        )

    def history(self, case_id: int) -> list[dict]:
        return self.db.query(
            """
            SELECT h.*, u.username AS changed_by, u.full_name AS changed_by_name
            FROM case_status_history h
            JOIN users u ON u.user_id = h.changed_by_user_id
            WHERE h.case_id = %s
            ORDER BY h.changed_at DESC, h.history_id DESC
            """,
            (case_id,),
        )

    def statuses(self) -> list[str]:
        return [
            "registered", "under_investigation", "charges_filed", "trial",
            "closed_convicted", "closed_acquitted", "closed_untraceable",
        ]

    # -- writes -------------------------------------------------------
    def file_case(
        self,
        *,
        station_id: int,
        officer_id: int,
        user_id: int,
        category: str,
        offence_type: str | None,
        occurrence_datetime: str,
        reporting_datetime: str,
        place_of_occurrence: str | None,
        description: str | None,
        section_ids: list[int],
    ) -> dict:
        rows = self.call(
            "sp_file_case",
            [
                station_id, officer_id, user_id, category, offence_type,
                occurrence_datetime, reporting_datetime, place_of_occurrence,
                description, json.dumps(section_ids),
            ],
        )
        if not rows:
            raise DatabaseError("The case could not be filed.")
        return rows[0]

    def update_status(self, case_id: int, new_status: str, user_id: int,
                      remark: str | None = None) -> dict:
        rows = self.call(
            "sp_update_case_status", [case_id, new_status, user_id, remark]
        )
        if not rows:
            raise DatabaseError("The case status could not be updated.")
        return rows[0]

    def assign_officer(self, case_id: int, officer_id: int, user_id: int) -> dict:
        rows = self.call(
            "sp_assign_officer", [case_id, officer_id, user_id]
        )
        if not rows:
            raise DatabaseError("The officer could not be assigned.")
        return rows[0]

    def update_details(self, case_id: int, **fields: Any) -> None:
        allowed = {
            "category", "offence_type", "occurrence_datetime", "reporting_datetime",
            "place_of_occurrence", "description", "summary",
        }
        sets = []
        values = []
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key} = %s")
                values.append(value)
        if not sets:
            return
        values.append(case_id)
        self.execute(
            f"UPDATE crime_cases SET {', '.join(sets)} WHERE case_id = %s", values
        )

    def add_offence(self, case_id: int, section_id: int,
                    accused_role: str = "primary") -> None:
        self.execute(
            """
            INSERT INTO case_offences (case_id, section_id, accused_role)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE accused_role = VALUES(accused_role)
            """,
            (case_id, section_id, accused_role),
        )

    def remove_offence(self, case_id: int, section_id: int) -> None:
        self.execute(
            "DELETE FROM case_offences WHERE case_id = %s AND section_id = %s",
            (case_id, section_id),
        )

    def delete(self, case_id: int) -> None:
        self.require(ROLE_ADMIN)
        self.execute("DELETE FROM crime_cases WHERE case_id = %s", (case_id,))
