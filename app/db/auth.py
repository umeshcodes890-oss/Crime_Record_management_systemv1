"""User accounts, login and role checks."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from app.db.connection import Database, DatabaseError
from app.db.passwords import hash_password, verify_password

ROLE_ADMIN = "admin"
ROLE_OFFICER = "officer"
ROLE_VIEWER = "viewer"
ALL_ROLES = (ROLE_ADMIN, ROLE_OFFICER, ROLE_VIEWER)


class AccessDenied(DatabaseError):
    """The signed-in user is not allowed to perform this operation."""


def require_role(user: dict | None, *roles: str) -> None:
    """Raise unless the signed-in user holds one of the given roles."""
    if user is None:
        raise AccessDenied("You need to sign in to do that.")
    if user.get("role") not in roles:
        raise AccessDenied(
            f"Your role '{user.get('role', 'unknown')}' is not allowed to do that.")


class Repository:
    """Base for the repositories.

    Writes go through :meth:`execute` and :meth:`call` instead of
    touching the database directly, so every write is checked against
    the role of the signed-in user. Hiding a button in the UI is a
    convenience; this is the check that actually protects the data.
    """

    write_roles: tuple[str, ...] = (ROLE_ADMIN, ROLE_OFFICER)

    def __init__(self, db: Database, actor: dict | None = None) -> None:
        self.db = db
        self.actor = actor

    def require(self, *roles: str) -> None:
        require_role(self.actor, *roles)

    def user_id(self) -> int:
        """The signed-in user a record is attributed to."""
        user_id = (self.actor or {}).get("user_id")
        if user_id is None:
            raise DatabaseError("Nobody is signed in, so this cannot be attributed.")
        return user_id

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> int:
        self.require(*self.write_roles)
        return self.db.execute(sql, params)

    def execute_many(self, sql: str, seq_params: Iterable[Sequence[Any]]) -> int:
        self.require(*self.write_roles)
        return self.db.execute_many(sql, seq_params)

    def call(self, procedure: str, args: Sequence[Any] = ()) -> list[dict]:
        self.require(*self.write_roles)
        return self.db.call(procedure, args)

    # -- reads -------------------------------------------------------
    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[dict]:
        return self.db.query(sql, params)

    def query_one(self, sql: str, params: Sequence[Any] | None = None) -> dict | None:
        return self.db.query_one(sql, params)

    def scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        return self.db.scalar(sql, params)

    # -- audit trail -------------------------------------------------
    def log(self, entity: str, entity_id: int, action: str,
            summary: str | None = None, case_id: int | None = None) -> int:
        """Record a change in the audit trail, attributed to the actor.

        The audit table is append-only, so an entry stays even if the
        user or the case it refers to is deleted later: the username is
        stored alongside the id for that reason.
        """
        actor = self.actor or {}
        return self.execute(
            """
            INSERT INTO audit_log (entity, entity_id, case_id, action, summary,
                                   changed_by_user_id, username_snapshot)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (entity, entity_id, case_id, action, summary,
             actor.get("user_id"), actor.get("username")),
        )

    def parent_case(self, table: str, key_column: str, key_value: Any) -> int | None:
        """The case a row belongs to, so the audit entry can name it."""
        row = self.db.query_one(
            f"SELECT case_id FROM {table} WHERE {key_column} = %s", (key_value,))
        return row["case_id"] if row else None

    def case_of_child(self, table: str, key_column: str, parent_column: str,
                      parent_table: str, parent_key: str, key_value: Any) -> int | None:
        """The case a child record belongs to, via the row that owns it."""
        parent_id = self.db.scalar(
            f"SELECT {parent_column} FROM {table} WHERE {key_column} = %s", (key_value,))
        if parent_id is None:
            return None
        row = self.db.query_one(
            f"SELECT case_id FROM {parent_table} WHERE {parent_key} = %s", (parent_id,))
        return row["case_id"] if row else None

    # -- records that also belong in the audit trail -----------------
    def create_record(self, table: str, entity: str, *, editable: Iterable[str],
                      fixed: dict, values: dict, summary: str,
                      case_id: int | None = None) -> int:
        """INSERT a row and its audit entry together, or not at all.

        ``fixed`` holds the columns the caller cannot choose - the case or
        person the row belongs to and who recorded it. ``values`` is the
        caller's own data and is checked against ``editable`` first, so
        only real column names reach the SQL.
        """
        self.guard_fields(editable, values, entity)
        with self.db.transaction():
            record_id = self.insert_row(table, {**fixed, **values})
            self.log(entity, record_id, "create", summary, case_id=case_id)
        return record_id

    def edit_record(self, table: str, entity: str, key_column: str, key_value: int,
                    editable: Iterable[str], values: dict, *,
                    summary: str | None = None, action: str = "update",
                    case_id: int | None = None) -> None:
        """UPDATE a row and log the change together, or neither."""
        self.guard_fields(editable, values, entity)
        if not values:
            return
        with self.db.transaction():
            self.update_row(table, key_column, key_value, editable, values)
            self.log(entity, key_value, action,
                     summary or "Updated " + ", ".join(sorted(values)), case_id=case_id)

    def remove_record(self, table: str, entity: str, key_column: str, key_value: int,
                      *, summary: str | None = None,
                      case_id: int | None = None) -> None:
        """DELETE a row and log it, so the trail outlives the record."""
        with self.db.transaction():
            self.execute(f"DELETE FROM {table} WHERE {key_column} = %s", (key_value,))
            self.log(entity, key_value, "delete", summary, case_id=case_id)

    # -- statement helpers -------------------------------------------
    @staticmethod
    def guard_fields(allowed: Iterable[str], values: dict, label: str) -> None:
        """Reject field names the table does not own.

        Column names are written into the SQL as they are, so they are
        checked against a whitelist before a dict of user input is used.
        """
        unknown = set(values) - set(allowed)
        if unknown:
            raise DatabaseError(
                f"Unknown {label} field{'s' if len(unknown) > 1 else ''}: "
                f"{', '.join(sorted(unknown))}")

    def insert_row(self, table: str, row: dict) -> int:
        """INSERT a dict as one row and return the new primary key.

        Columns left out of the dict take their database default, which
        is why the repositories pass on only what the caller supplied.
        An empty string from a form entry is stored as NULL, because a
        blank date or number would otherwise be rejected.
        """
        values = {column: (None if value == "" else value)
                  for column, value in row.items()}
        columns = ", ".join(f"`{column}`" for column in values)
        placeholders = ", ".join(["%s"] * len(values))
        return self.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
            list(values.values()),
        )

    def update_row(self, table: str, key_column: str, key_value: Any,
                   allowed: Iterable[str], values: dict) -> None:
        """UPDATE the permitted columns of one row; do nothing if none is set."""
        permitted = set(allowed)
        sets: list[str] = []
        params: list[Any] = []
        for column, value in values.items():
            if column in permitted:
                sets.append(f"`{column}` = %s")
                params.append(None if value == "" else value)
        if not sets:
            return
        params.append(key_value)
        self.execute(
            f"UPDATE {table} SET {', '.join(sets)} WHERE {key_column} = %s", params)


class UserRepository(Repository):
    write_roles = (ROLE_ADMIN,)

    def authenticate(self, username: str, password: str) -> dict | None:
        row = self.db.query_one(
            """
            SELECT user_id, username, password_hash, role, officer_id, full_name,
                   is_active, created_at, last_login_at
            FROM users WHERE username = %s
            """,
            (username.strip(),),
        )
        if row is None:
            return None
        if not row["is_active"]:
            raise DatabaseError("That account has been deactivated. Contact an administrator.")
        if not verify_password(password, row["password_hash"]):
            return None
        self.db.execute(
            "UPDATE users SET last_login_at = NOW() WHERE user_id = %s", (row["user_id"],)
        )
        row.pop("password_hash", None)
        return row

    def list_all(self) -> list[dict]:
        return self.db.query(
            """
            SELECT u.user_id, u.username, u.role, u.officer_id, u.full_name,
                   u.is_active, u.created_at, u.last_login_at, o.name AS officer_name
            FROM users u
            LEFT JOIN officers o ON o.officer_id = u.officer_id
            ORDER BY u.username
            """
        )

    def create(self, username: str, password: str, role: str, *,
               full_name: str | None = None, officer_id: int | None = None) -> int:
        if role not in ALL_ROLES:
            raise DatabaseError(f"Unknown role '{role}'.")
        return self.execute(
            """
            INSERT INTO users (username, password_hash, role, full_name, officer_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (username.strip(), hash_password(password), role, full_name, officer_id),
        )

    def update(self, user_id: int, *, username: str, role: str,
               full_name: str | None = None, officer_id: int | None = None,
               is_active: bool = True) -> None:
        if role not in ALL_ROLES:
            raise DatabaseError(f"Unknown role '{role}'.")
        self.execute(
            """
            UPDATE users
               SET username = %s, role = %s, full_name = %s,
                   officer_id = %s, is_active = %s
             WHERE user_id = %s
            """,
            (username.strip(), role, full_name, officer_id, is_active, user_id),
        )

    def set_password(self, user_id: int, password: str) -> None:
        self.execute(
            "UPDATE users SET password_hash = %s WHERE user_id = %s",
            (hash_password(password), user_id),
        )

    def set_active(self, user_id: int, is_active: bool) -> None:
        self.execute(
            "UPDATE users SET is_active = %s WHERE user_id = %s", (is_active, user_id)
        )

    def delete(self, user_id: int) -> None:
        self.execute("DELETE FROM users WHERE user_id = %s", (user_id,))

    def count_active_admins(self) -> int:
        value = self.db.scalar(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = TRUE"
        )
        return int(value or 0)
