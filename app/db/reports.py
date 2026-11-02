"""Aggregations for the dashboard and reports."""

from __future__ import annotations

from app.db.connection import Database


class ReportRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def summary(self) -> dict:
        rows = self.db.call("sp_dashboard_summary")
        return rows[0] if rows else {}

    def by_status(self) -> list[dict]:
        return self.db.query(
            """
            SELECT status, COUNT(*) AS total FROM crime_cases
            GROUP BY status ORDER BY total DESC
            """
        )

    def by_category(self) -> list[dict]:
        return self.db.query(
            """
            SELECT category, COUNT(*) AS total FROM crime_cases
            GROUP BY category ORDER BY total DESC
            """
        )

    def monthly(self, months: int = 12) -> list[dict]:
        return self.db.query(
            """
            SELECT month, cases_registered, cases_closed, cases_convicted
            FROM v_monthly_caseload
            ORDER BY month DESC LIMIT %s
            """,
            (months,),
        )

    def top_offences(self, limit: int = 8) -> list[dict]:
        return self.db.query(
            """
            SELECT section_no, offence_name, severity, law_code, case_count
            FROM v_offence_statistics
            WHERE case_count > 0
            ORDER BY case_count DESC, offence_name LIMIT %s
            """,
            (limit,),
        )

    def by_station(self) -> list[dict]:
        return self.db.query(
            """
            SELECT station_name, district, total_cases, open_cases, convicted_cases,
                   clearance_rate
            FROM v_station_statistics
            ORDER BY total_cases DESC
            """
        )

    def officer_workload(self, limit: int = 8) -> list[dict]:
        return self.db.query(
            """
            SELECT name, badge_no, station_name, total_cases, open_cases,
                   avg_days_to_close
            FROM v_officer_workload
            WHERE total_cases > 0
            ORDER BY open_cases DESC, total_cases DESC LIMIT %s
            """,
            (limit,),
        )

    def upcoming_hearings(self, limit: int = 8) -> list[dict]:
        return self.db.query(
            """
            SELECT case_no, court_name, next_hearing_datetime, days_until, stage
            FROM v_upcoming_hearings LIMIT %s
            """,
            (limit,),
        )

    def status_breakdown(self) -> list[dict]:
        """Cases per month split by status, for the stacked trend chart."""
        return self.db.query(
            """
            SELECT DATE_FORMAT(occurrence_datetime, '%Y-%m') AS month, status, COUNT(*) AS total
            FROM crime_cases
            GROUP BY month, status
            ORDER BY month
            """
        )
