"""User accounts, login and role checks."""

from __future__ import annotations

from typing import Any, Sequence

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


class UserRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

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
        return self.db.execute(
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
        self.db.execute(
            """
            UPDATE users
               SET username = %s, role = %s, full_name = %s,
                   officer_id = %s, is_active = %s
             WHERE user_id = %s
            """,
            (username.strip(), role, full_name, officer_id, is_active, user_id),
        )

    def set_password(self, user_id: int, password: str) -> None:
        self.db.execute(
            "UPDATE users SET password_hash = %s WHERE user_id = %s",
            (hash_password(password), user_id),
        )

    def set_active(self, user_id: int, is_active: bool) -> None:
        self.db.execute(
            "UPDATE users SET is_active = %s WHERE user_id = %s", (is_active, user_id)
        )

    def delete(self, user_id: int) -> None:
        self.db.execute("DELETE FROM users WHERE user_id = %s", (user_id,))

    def count_active_admins(self) -> int:
        value = self.db.scalar(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = TRUE"
        )
        return int(value or 0)
