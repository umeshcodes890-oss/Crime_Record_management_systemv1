"""Evidence register."""

from __future__ import annotations

from app.db.auth import Repository
from app.db.connection import Database


class EvidenceRepository(Repository):
    def __init__(self, db: Database, actor: dict | None = None) -> None:
        super().__init__(db, actor)

    def for_case(self, case_id: int) -> list[dict]:
        return self.db.query(
            """
            SELECT e.*, o.name AS collected_by_name, c.case_no
            FROM evidence e
            JOIN officers o    ON o.officer_id = e.collected_by_officer_id
            JOIN crime_cases c ON c.case_id = e.case_id
            WHERE e.case_id = %s
            ORDER BY e.collected_datetime DESC
            """,
            (case_id,),
        )

    def list_all(self, evidence_type: str | None = None,
                 search: str | None = None) -> list[dict]:
        clauses, params = [], []
        if evidence_type:
            clauses.append("e.type = %s")
            params.append(evidence_type)
        if search:
            clauses.append("(e.description LIKE %s OR c.case_no LIKE %s OR e.storage_location LIKE %s)")
            params.extend([f"%{search}%"] * 3)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.db.query(
            f"""
            SELECT e.*, o.name AS collected_by_name, c.case_no, c.status AS case_status
            FROM evidence e
            JOIN officers o     ON o.officer_id = e.collected_by_officer_id
            JOIN crime_cases c  ON c.case_id = e.case_id
            {where}
            ORDER BY e.collected_datetime DESC
            """,
            params,
        )

    def create(self, case_id: int, evidence_type: str, description: str,
               collected_by_officer_id: int, collected_datetime: str,
               seized_under: str | None = None, storage_location: str | None = None,
               chain_of_custody_datetime: str | None = None) -> int:
        return self.execute(
            """
            INSERT INTO evidence (case_id, type, description, collected_by_officer_id,
                                  collected_datetime, seized_under, storage_location,
                                  chain_of_custody_datetime)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (case_id, evidence_type, description.strip(), collected_by_officer_id,
             collected_datetime, seized_under, storage_location, chain_of_custody_datetime),
        )

    def update(self, evidence_id: int, **fields) -> None:
        allowed = {"type", "description", "collected_by_officer_id", "collected_datetime",
                   "seized_under", "storage_location", "chain_of_custody_datetime"}
        sets, values = [], []
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key} = %s")
                values.append(value)
        if not sets:
            return
        values.append(evidence_id)
        self.execute(f"UPDATE evidence SET {', '.join(sets)} WHERE evidence_id = %s", values)

    def delete(self, evidence_id: int) -> None:
        self.execute("DELETE FROM evidence WHERE evidence_id = %s", (evidence_id,))
