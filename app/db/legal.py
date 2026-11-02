"""Custody and court records: arrests, proceedings and convictions."""

from __future__ import annotations

from app.db.auth import Repository
from app.db.connection import Database


class ArrestRepository(Repository):
    def __init__(self, db: Database, actor: dict | None = None) -> None:
        super().__init__(db, actor)

    def for_case(self, case_id: int) -> list[dict]:
        return self.db.query(
            """
            SELECT a.*, su.name AS suspect_name, o.name AS arrested_by_name
            FROM arrests a
            JOIN suspects su ON su.suspect_id = a.suspect_id
            JOIN officers o   ON o.officer_id = a.arrested_by_officer_id
            WHERE a.case_id = %s
            ORDER BY a.arrest_datetime DESC
            """,
            (case_id,),
        )

    def list_all(self, search: str | None = None) -> list[dict]:
        where, params = "", []
        if search:
            where = "WHERE su.name LIKE %s OR c.case_no LIKE %s"
            params = [f"%{search}%", f"%{search}%"]
        return self.db.query(
            f"""
            SELECT a.*, su.name AS suspect_name, o.name AS arrested_by_name, c.case_no
            FROM arrests a
            JOIN suspects su ON su.suspect_id = a.suspect_id
            JOIN officers o   ON o.officer_id = a.arrested_by_officer_id
            JOIN crime_cases c ON c.case_id = a.case_id
            {where} ORDER BY a.arrest_datetime DESC
            """,
            params,
        )

    def record(self, case_id: int, suspect_id: int, officer_id: int,
               arrest_datetime: str, place: str | None,
               remand_status: str = "not_remanded",
               bail_amount: float | None = None) -> int:
        rows = self.call(
            "sp_record_arrest",
            [case_id, suspect_id, officer_id, arrest_datetime, place,
             remand_status, bail_amount],
        )
        return int(rows[0]["arrest_id"]) if rows else 0

    def delete(self, arrest_id: int) -> None:
        self.execute("DELETE FROM arrests WHERE arrest_id = %s", (arrest_id,))


class ProceedingRepository(Repository):
    def __init__(self, db: Database, actor: dict | None = None) -> None:
        super().__init__(db, actor)

    def for_case(self, case_id: int) -> list[dict]:
        return self.db.query(
            """
            SELECT * FROM court_proceedings WHERE case_id = %s
            ORDER BY hearing_datetime DESC
            """,
            (case_id,),
        )

    def list_all(self, upcoming_only: bool = False) -> list[dict]:
        where = "WHERE p.next_hearing_datetime IS NOT NULL" if upcoming_only else ""
        return self.db.query(
            f"""
            SELECT p.*, c.case_no, c.status AS case_status, s.name AS station_name
            FROM court_proceedings p
            JOIN crime_cases c     ON c.case_id = p.case_id
            JOIN police_stations s ON s.station_id = c.station_id
            {where}
            ORDER BY COALESCE(p.next_hearing_datetime, p.hearing_datetime) DESC
            """
        )

    def create(self, case_id: int, court_name: str, hearing_datetime: str,
               stage: str = "first_hearing", judge_name: str | None = None,
               next_hearing_datetime: str | None = None,
               remarks: str | None = None) -> int:
        return self.execute(
            """
            INSERT INTO court_proceedings (case_id, court_name, hearing_datetime, stage,
                                           judge_name, next_hearing_datetime, remarks)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (case_id, court_name.strip(), hearing_datetime, stage, judge_name,
             next_hearing_datetime, remarks),
        )

    def update(self, proceeding_id: int, **fields) -> None:
        allowed = {"court_name", "hearing_datetime", "stage", "judge_name",
                   "next_hearing_datetime", "remarks"}
        sets, values = [], []
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key} = %s")
                values.append(value)
        if not sets:
            return
        values.append(proceeding_id)
        self.execute(
            f"UPDATE court_proceedings SET {', '.join(sets)} WHERE proceeding_id = %s", values
        )

    def delete(self, proceeding_id: int) -> None:
        self.execute(
            "DELETE FROM court_proceedings WHERE proceeding_id = %s", (proceeding_id,)
        )


class ConvictionRepository(Repository):
    def __init__(self, db: Database, actor: dict | None = None) -> None:
        super().__init__(db, actor)

    def for_case(self, case_id: int) -> list[dict]:
        return self.db.query(
            """
            SELECT cv.*, su.name AS suspect_name
            FROM convictions cv
            JOIN suspects su ON su.suspect_id = cv.suspect_id
            WHERE cv.case_id = %s ORDER BY cv.created_at DESC
            """,
            (case_id,),
        )

    def list_all(self, verdict: str | None = None) -> list[dict]:
        where, params = "", []
        if verdict:
            where = "WHERE cv.verdict = %s"
            params = [verdict]
        return self.db.query(
            f"""
            SELECT cv.*, su.name AS suspect_name, c.case_no, c.category AS case_category
            FROM convictions cv
            JOIN suspects su ON su.suspect_id = cv.suspect_id
            JOIN crime_cases c ON c.case_id = cv.case_id
            {where} ORDER BY cv.created_at DESC
            """,
            params,
        )

    def record(self, case_id: int, suspect_id: int, user_id: int, court_name: str,
               verdict: str, sentence_type: str = "none",
               imprisonment_years: float | None = None,
               fine_amount: float | None = None,
               sentence_start: str | None = None,
               release_expected: str | None = None) -> int:
        rows = self.call(
            "sp_record_conviction",
            [case_id, suspect_id, user_id, court_name, verdict, sentence_type,
             imprisonment_years, fine_amount, sentence_start, release_expected],
        )
        return int(rows[0]["conviction_id"]) if rows else 0

    def delete(self, conviction_id: int) -> None:
        self.execute("DELETE FROM convictions WHERE conviction_id = %s", (conviction_id,))
