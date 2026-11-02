"""Master data: police stations, officers and the law library."""

from __future__ import annotations

from app.db.auth import ROLE_ADMIN, Repository
from app.db.connection import Database


class StationRepository(Repository):
    write_roles = (ROLE_ADMIN,)

    def __init__(self, db: Database, actor: dict | None = None) -> None:
        super().__init__(db, actor)

    def list_all(self) -> list[dict]:
        return self.db.query(
            """
            SELECT s.station_id, s.name, s.district, s.address, s.phone,
                   s.incharge_officer_id, o.name AS incharge_name,
                   (SELECT COUNT(*) FROM crime_cases c WHERE c.station_id = s.station_id)
                       AS case_count
            FROM police_stations s
            LEFT JOIN officers o ON o.officer_id = s.incharge_officer_id
            ORDER BY s.name
            """
        )

    def options(self) -> list[dict]:
        return self.db.query(
            "SELECT station_id, name, district FROM police_stations ORDER BY name"
        )

    def get(self, station_id: int) -> dict | None:
        return self.db.query_one(
            "SELECT * FROM police_stations WHERE station_id = %s", (station_id,)
        )

    def create(self, name: str, district: str, address: str | None,
               phone: str | None, incharge_officer_id: int | None = None) -> int:
        return self.execute(
            """
            INSERT INTO police_stations (name, district, address, phone, incharge_officer_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (name.strip(), district.strip(), address, phone, incharge_officer_id),
        )

    def update(self, station_id: int, name: str, district: str,
               address: str | None, phone: str | None,
               incharge_officer_id: int | None) -> None:
        self.execute(
            """
            UPDATE police_stations
               SET name = %s, district = %s, address = %s, phone = %s,
                   incharge_officer_id = %s
             WHERE station_id = %s
            """,
            (name.strip(), district.strip(), address, phone, incharge_officer_id, station_id),
        )

    def delete(self, station_id: int) -> None:
        self.execute("DELETE FROM police_stations WHERE station_id = %s", (station_id,))


class OfficerRepository(Repository):
    write_roles = (ROLE_ADMIN,)

    def __init__(self, db: Database, actor: dict | None = None) -> None:
        super().__init__(db, actor)

    def list_all(self) -> list[dict]:
        return self.db.query(
            "SELECT * FROM v_officer_workload ORDER BY open_cases DESC, name"
        )

    def options(self, station_id: int | None = None) -> list[dict]:
        if station_id:
            return self.db.query(
                """
                SELECT officer_id, name, badge_no, `rank`, station_id
                FROM officers WHERE is_active = TRUE AND station_id = %s
                ORDER BY name
                """,
                (station_id,),
            )
        return self.db.query(
            """
            SELECT officer_id, name, badge_no, `rank`, station_id
            FROM officers WHERE is_active = TRUE ORDER BY name
            """
        )

    def get(self, officer_id: int) -> dict | None:
        return self.db.query_one(
            """
            SELECT o.*, ps.name AS station_name
            FROM officers o
            JOIN police_stations ps ON ps.station_id = o.station_id
            WHERE o.officer_id = %s
            """,
            (officer_id,),
        )

    def create(self, badge_no: str, name: str, rank: str, station_id: int,
               phone: str | None, join_date: str | None) -> int:
        return self.execute(
            """
            INSERT INTO officers (badge_no, name, `rank`, station_id, phone, join_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (badge_no.strip(), name.strip(), rank, station_id, phone, join_date),
        )

    def update(self, officer_id: int, badge_no: str, name: str, rank: str,
               station_id: int, phone: str | None, join_date: str | None,
               is_active: bool) -> None:
        self.execute(
            """
            UPDATE officers
               SET badge_no = %s, name = %s, `rank` = %s, station_id = %s,
                   phone = %s, join_date = %s, is_active = %s
             WHERE officer_id = %s
            """,
            (badge_no.strip(), name.strip(), rank, station_id, phone, join_date,
             is_active, officer_id),
        )

    def delete(self, officer_id: int) -> None:
        self.execute("DELETE FROM officers WHERE officer_id = %s", (officer_id,))


class OffenceRepository(Repository):
    write_roles = (ROLE_ADMIN,)

    def __init__(self, db: Database, actor: dict | None = None) -> None:
        super().__init__(db, actor)

    def list_all(self, law_code: str | None = None) -> list[dict]:
        if law_code:
            return self.db.query(
                """
                SELECT section_id, law_code, section_no, offence_name, category,
                       severity, min_imprisonment_yrs, max_imprisonment_yrs,
                       fine_cap, description
                FROM offence_sections WHERE law_code = %s
                ORDER BY CAST(section_no AS UNSIGNED), section_no
                """,
                (law_code,),
            )
        return self.db.query(
            """
            SELECT section_id, law_code, section_no, offence_name, category,
                   severity, min_imprisonment_yrs, max_imprisonment_yrs,
                   fine_cap, description
            FROM offence_sections
            ORDER BY law_code, CAST(section_no AS UNSIGNED), section_no
            """
        )

    def options(self) -> list[dict]:
        return self.db.query(
            """
            SELECT section_id, law_code, section_no, offence_name, severity
            FROM offence_sections ORDER BY law_code, CAST(section_no AS UNSIGNED)
            """
        )

    def get(self, section_id: int) -> dict | None:
        return self.db.query_one(
            "SELECT * FROM offence_sections WHERE section_id = %s", (section_id,)
        )

    def create(self, law_code: str, section_no: str, offence_name: str,
               category: str, severity: str, min_years: float | None,
               max_years: float | None, fine_cap: float | None,
               description: str | None) -> int:
        return self.execute(
            """
            INSERT INTO offence_sections
                (law_code, section_no, offence_name, category, severity,
                 min_imprisonment_yrs, max_imprisonment_yrs, fine_cap, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (law_code, section_no.strip(), offence_name.strip(), category, severity,
             min_years, max_years, fine_cap, description),
        )

    def update(self, section_id: int, law_code: str, section_no: str,
               offence_name: str, category: str, severity: str,
               min_years: float | None, max_years: float | None,
               fine_cap: float | None, description: str | None) -> None:
        self.execute(
            """
            UPDATE offence_sections
               SET law_code = %s, section_no = %s, offence_name = %s,
                   category = %s, severity = %s, min_imprisonment_yrs = %s,
                   max_imprisonment_yrs = %s, fine_cap = %s, description = %s
             WHERE section_id = %s
            """,
            (law_code, section_no.strip(), offence_name.strip(), category, severity,
             min_years, max_years, fine_cap, description, section_id),
        )

    def delete(self, section_id: int) -> None:
        self.execute("DELETE FROM offence_sections WHERE section_id = %s", (section_id,))
