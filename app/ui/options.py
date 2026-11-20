"""The choices a screen offers, spelled the way the database stores them.

These lists mirror the ENUM definitions in the schema. They live in one
place so that a filter on a register, a field on a form and a value read
back from MySQL are always written the same way.
"""

from __future__ import annotations

GENDERS = ["male", "female", "other", "unknown"]
CONFIDENTIALITY_LEVELS = ["public", "internal", "confidential", "restricted"]
YES_NO = ["Yes", "No"]

# Victims
INJURY_LEVELS = ["none", "minor", "moderate", "grievous", "fatal"]
MEDICAL_ASSISTANCE = ["none", "requested", "provided", "completed", "declined"]
CONTACT_TYPES = ["phone", "visit", "email", "letter", "court_appearance", "other"]
COMPENSATION_TYPES = ["monetary", "medical_support", "legal_aid", "employment", "other"]
COMPENSATION_STATUSES = [
    "not_applied", "applied", "under_review", "approved",
    "partially_paid", "paid", "rejected",
]

# Witnesses
WITNESS_TYPES = ["eyewitness", "expert", "character", "medical", "police", "other"]
AVAILABILITY = ["available", "unavailable", "deceased", "relocated", "unknown"]
INTERVIEW_OUTCOMES = [
    "scheduled", "completed", "adjourned", "witness_absent", "refused", "other",
]
PROTECTION_STATUSES = ["active", "revoked", "completed", "expired"]

# Evidence
EVIDENCE_TYPES = ["physical", "documentary", "digital", "forensic", "testimonial"]
EVIDENCE_CATEGORIES = [
    "physical", "documentary", "digital", "biological", "ballistic",
    "trace", "chemical", "firearm", "other",
]
EVIDENCE_CONDITIONS = ["intact", "damaged", "partial", "degraded", "unknown"]
EVIDENCE_STATUSES = [
    "seized", "sealed", "in_store", "issued_to_court",
    "under_examination", "returned", "destroyed",
]
FORENSIC_STATUSES = [
    "not_required", "pending", "sent", "under_examination", "reported",
]
CUSTODY_EVENTS = [
    "collected", "stored", "transferred", "received",
    "issued_to_court", "returned", "examined",
]
FORENSIC_RESULTS = ["pending", "inconclusive", "exculpatory", "incriminating", "other"]


def pretty(value: str | None) -> str:
    """An enum value the way a label reads it."""
    if not value:
        return "-"
    return str(value).replace("_", " ").capitalize()
