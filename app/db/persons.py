"""People attached to a case: suspects, victims and witnesses."""

from __future__ import annotations

from app.db.auth import Repository
from app.db.connection import Database


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


class VictimRepository(Repository):
    def __init__(self, db: Database, actor: dict | None = None) -> None:
        super().__init__(db, actor)

    def for_case(self, case_id: int) -> list[dict]:
        return self.db.query(
            "SELECT * FROM victims WHERE case_id = %s ORDER BY name", (case_id,)
        )

    def list_all(self, search: str | None = None) -> list[dict]:
        where, params = "", []
        if search:
            where = "WHERE v.name LIKE %s OR c.case_no LIKE %s"
            params = [f"%{search}%", f"%{search}%"]
        return self.db.query(
            f"""
            SELECT v.*, c.case_no, c.status AS case_status
            FROM victims v JOIN crime_cases c ON c.case_id = v.case_id
            {where} ORDER BY v.created_at DESC
            """,
            params,
        )

    def create(self, case_id: int, name: str, *, age: int | None = None,
               gender: str = "unknown", phone: str | None = None,
               address: str | None = None, injury_level: str = "none",
               statement: str | None = None) -> int:
        return self.execute(
            """
            INSERT INTO victims (case_id, name, age, gender, phone, address,
                                 injury_level, statement)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (case_id, name.strip(), age, gender, phone, address, injury_level, statement),
        )

    def update(self, victim_id: int, **fields) -> None:
        allowed = {"name", "age", "gender", "phone", "address", "injury_level", "statement"}
        sets, values = [], []
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key} = %s")
                values.append(value)
        if not sets:
            return
        values.append(victim_id)
        self.execute(f"UPDATE victims SET {', '.join(sets)} WHERE victim_id = %s", values)

    def delete(self, victim_id: int) -> None:
        self.execute("DELETE FROM victims WHERE victim_id = %s", (victim_id,))


class WitnessRepository(Repository):
    def __init__(self, db: Database, actor: dict | None = None) -> None:
        super().__init__(db, actor)

    def for_case(self, case_id: int) -> list[dict]:
        return self.db.query(
            "SELECT * FROM witnesses WHERE case_id = %s ORDER BY name", (case_id,)
        )

    def list_all(self, search: str | None = None) -> list[dict]:
        where, params = "", []
        if search:
            where = "WHERE w.name LIKE %s OR c.case_no LIKE %s"
            params = [f"%{search}%", f"%{search}%"]
        return self.db.query(
            f"""
            SELECT w.*, c.case_no, c.status AS case_status
            FROM witnesses w JOIN crime_cases c ON c.case_id = w.case_id
            {where} ORDER BY w.created_at DESC
            """,
            params,
        )

    def create(self, case_id: int, name: str, *, phone: str | None = None,
               address: str | None = None, statement: str | None = None,
               is_reliable: bool = True) -> int:
        return self.execute(
            """
            INSERT INTO witnesses (case_id, name, phone, address, statement, is_reliable)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (case_id, name.strip(), phone, address, statement, is_reliable),
        )

    def update(self, witness_id: int, **fields) -> None:
        allowed = {"name", "phone", "address", "statement", "is_reliable"}
        sets, values = [], []
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key} = %s")
                values.append(value)
        if not sets:
            return
        values.append(witness_id)
        self.execute(f"UPDATE witnesses SET {', '.join(sets)} WHERE witness_id = %s", values)

    def delete(self, witness_id: int) -> None:
        self.execute("DELETE FROM witnesses WHERE witness_id = %s", (witness_id,))
