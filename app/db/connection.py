"""Configuration loading and MySQL connection management.

The UI layer never imports mysql.connector directly - every query in
the application goes through this module, which owns the connection,
retries it once if the server has dropped it, and turns MySQL errors
into messages a user can act on.
"""

from __future__ import annotations

import configparser
import logging
import threading
from pathlib import Path
from typing import Any, Iterable, Sequence

import mysql.connector
from mysql.connector import Error as MySQLError

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.ini"


class DatabaseError(RuntimeError):
    """A database operation was rejected or failed."""


class ConnectionLost(DatabaseError):
    """The MySQL server could not be reached."""


class ConfigError(RuntimeError):
    """config.ini is missing or incomplete."""


# Constraint name -> message a user can act on.
_FRIENDLY_CONSTRAINTS = {
    "fk_case_station": "That police station cannot be deleted while cases still reference it.",
    "fk_case_officer": "That officer still has cases assigned and cannot be deleted.",
    "fk_case_filed_by": "That user still has cases filed against them and cannot be deleted.",
    "fk_officer_station": "That station still has officers posted to it.",
    "fk_station_incharge": "That officer is still in charge of a station.",
    "fk_case_offences_section": "That offence section is in use by a case and cannot be deleted.",
    "fk_evidence_officer": "That officer is referenced by evidence records.",
    "fk_arrest_officer": "That officer is referenced by arrest records.",
    "fk_user_officer": "That officer is linked to a user account.",
    "fk_suspect_case": "That case no longer exists.",
    "uq_user_username": "That username is already taken.",
    "uq_officer_badge": "That badge number is already in use.",
    "uq_station_name": "A station with that name already exists.",
    "uq_offence_law_section": "That section already exists for this law.",
    "uq_case_no": "That case number already exists.",
}


def load_config(path: Path | None = None) -> configparser.ConfigParser:
    config_path = path or CONFIG_PATH
    if not config_path.exists():
        raise ConfigError(
            f"config.ini not found at {config_path}.\n"
            "Copy config.ini.template to config.ini and fill in your MySQL password:\n"
            "    copy config.ini.template config.ini"
        )
    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")
    if not parser.has_section("database"):
        raise ConfigError(f"{config_path} is missing the [database] section.")
    return parser


class Database:
    """A thin, thread-safe wrapper around a single MySQL connection."""

    def __init__(self, config: configparser.ConfigParser | None = None,
                 connect: bool = True) -> None:
        self.config = config or load_config()
        self._lock = threading.RLock()
        self._conn: Any = None
        if connect:
            self.connect()

    # ------------------------------------------------------------------
    # connection lifecycle
    # ------------------------------------------------------------------
    def connect(self) -> None:
        section = self.config["database"]
        try:
            self._conn = mysql.connector.connect(
                host=section.get("host", "127.0.0.1"),
                port=int(section.get("port", 3306)),
                user=section.get("user", "root"),
                password=section.get("password", ""),
                database=section.get("database", "crime_records"),
                charset="utf8mb4",
                use_unicode=True,
                autocommit=True,
                connection_timeout=10,
            )
        except mysql.connector.Error as exc:
            raise ConnectionLost(self._friendly_connection_message(exc)) from exc
        logger.info("Connected to MySQL at %s:%s", section.get("host"), section.get("port"))

    @staticmethod
    def _friendly_connection_message(exc: MySQLError) -> str:
        code = getattr(exc, "errno", None)
        if code == 1045:
            return ("Access denied for that MySQL user. Check the user name and "
                    "password in config.ini.")
        if code == 1049:
            return ("The database does not exist yet. Run this first:\n"
                    "    py scripts\\setup_db.py")
        if code in (2003, 2002, 2013):
            return ("Cannot reach the MySQL server. Make sure MySQL is running and "
                    "the host and port in config.ini are correct.")
        return f"Could not connect to MySQL: {exc}"

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except MySQLError:
                    pass
                self._conn = None

    def is_connected(self) -> bool:
        with self._lock:
            return self._conn is not None and self._conn.is_connected()

    def _connection(self) -> Any:
        with self._lock:
            if self._conn is None or not self._conn.is_connected():
                self.connect()
            return self._conn

    # ------------------------------------------------------------------
    # query helpers
    # ------------------------------------------------------------------
    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[dict]:
        """Run a SELECT and return a list of dicts."""
        with self._lock:
            cursor = self._connection().cursor(dictionary=True)
            try:
                cursor.execute(sql, tuple(params) if params else ())
                return list(cursor.fetchall())
            except MySQLError as exc:
                raise self._translate(exc) from exc
            finally:
                cursor.close()

    def query_one(self, sql: str, params: Sequence[Any] | None = None) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        row = self.query_one(sql, params)
        if not row:
            return None
        return next(iter(row.values()))

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> int:
        """Run an INSERT/UPDATE/DELETE and return the last inserted id."""
        with self._lock:
            cursor = self._connection().cursor()
            try:
                cursor.execute(sql, tuple(params) if params else ())
                return cursor.lastrowid
            except MySQLError as exc:
                raise self._translate(exc) from exc
            finally:
                cursor.close()

    def execute_many(self, sql: str, seq_params: Iterable[Sequence[Any]]) -> int:
        with self._lock:
            cursor = self._connection().cursor()
            try:
                cursor.executemany(sql, [tuple(p) for p in seq_params])
                return cursor.rowcount
            except MySQLError as exc:
                raise self._translate(exc) from exc
            finally:
                cursor.close()

    def call(self, procedure: str, args: Sequence[Any] = ()) -> list[dict]:
        """Call a stored procedure and return its result rows."""
        with self._lock:
            cursor = self._connection().cursor(dictionary=True)
            try:
                cursor.callproc(procedure, list(args))
                rows: list[dict] = []
                for result in cursor.stored_results():
                    rows.extend(result.fetchall())
                return rows
            except MySQLError as exc:
                raise self._translate(exc) from exc
            finally:
                cursor.close()

    def ddl(self, sql: str) -> None:
        """Execute a DDL statement (used by the installer)."""
        with self._lock:
            cursor = self._connection().cursor()
            try:
                cursor.execute(sql)
            except MySQLError as exc:
                raise self._translate(exc) from exc
            finally:
                cursor.close()

    # ------------------------------------------------------------------
    # error translation
    # ------------------------------------------------------------------
    @staticmethod
    def _translate(exc: MySQLError) -> DatabaseError:
        errno = getattr(exc, "errno", None)
        message = str(exc)

        if errno in (2006, 2013, 2003, 2002):
            return ConnectionLost(
                "Lost the connection to MySQL. Check that the server is still running.")

        if isinstance(exc, mysql.connector.IntegrityError):
            for constraint, friendly in _FRIENDLY_CONSTRAINTS.items():
                if constraint in message:
                    return DatabaseError(friendly)
            if errno == 1062:
                return DatabaseError("That record already exists.")
            if errno == 1451:
                return DatabaseError("That record is still referenced by other records.")
            if errno == 1452:
                return DatabaseError("A referenced record does not exist.")
            return DatabaseError(f"Database rejected the change: {message}")

        if isinstance(exc, mysql.connector.OperationalError):
            if errno == 1644:
                return DatabaseError(message)
            return DatabaseError(f"Database error: {message}")

        if isinstance(exc, mysql.connector.ProgrammingError) and errno == 1644:
            return DatabaseError(message)

        return DatabaseError(message)
