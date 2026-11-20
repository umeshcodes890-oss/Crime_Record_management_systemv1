"""Who is allowed to read what.

The rules live here so that every repository applies them the same way.
A viewer is masked by the data layer, not by a screen that happens to
leave a column out, so the same rows stay masked for reports, exports
and anything else that asks the repository for them.
"""

from __future__ import annotations

from typing import Any, Iterable

from app.db.auth import ROLE_ADMIN, ROLE_OFFICER

# Shown in place of a value the signed-in user may not read.
RESTRICTED = "[restricted]"

# Roles entitled to personal and medical detail in full. Everyone else,
# including nobody being signed in at all, is masked.
PRIVILEGED_ROLES = (ROLE_ADMIN, ROLE_OFFICER)

# The confidentiality levels that mean "this person must not be named".
# 'internal' is the ordinary setting for a case record and only keeps the
# detail off public reports; it does not hide a participant from the
# staff and viewers reading the case inside the application.
CONFIDENTIAL_LEVELS = frozenset({"confidential", "restricted"})


def is_confidential(row: dict | None) -> bool:
    return bool(row) and row.get("confidentiality_level") in CONFIDENTIAL_LEVELS


def is_restricted(actor: dict | None) -> bool:
    """True when this actor may not read personal detail."""
    return (actor or {}).get("role") not in PRIVILEGED_ROLES


def mask_row(actor: dict | None, row: dict | None,
             fields: Iterable[str]) -> dict | None:
    """Return the row with the sensitive columns hidden for this actor."""
    if row is None or not is_restricted(actor):
        return row
    masked = dict(row)
    for field in fields:
        if masked.get(field) not in (None, ""):
            masked[field] = RESTRICTED
    return masked


def mask_rows(actor: dict | None, rows: Iterable[dict],
              fields: Iterable[str]) -> list[dict]:
    """Apply :func:`mask_row` to a list of rows."""
    return [mask_row(actor, row, fields) for row in rows]
