"""Suspects, victims and witnesses registers."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from app.ui.dialogs import FormDialog
from app.ui.theme import PAD, PAD_LG, RADIUS, fonts
from app.ui.views.base import BaseView
from app.ui.widgets import PALETTE, Column, DataTable, FormPanel, confirm

SUSPECT_STATUSES = [
    "wanted", "arrested", "in_custody", "bailed", "released",
    "convicted", "acquitted", "untraceable",
]
GENDERS = ["male", "female", "other", "unknown"]
INJURY_LEVELS = ["none", "minor", "moderate", "grievous", "fatal"]


class _PersonDialog(FormDialog):
    """Base for the add-person dialogs."""

    def __init__(self, master, title: str, size=(680, 560)) -> None:
        super().__init__(master, title, size=size)

    def on_save(self, values: dict[str, Any]) -> None:
        raise NotImplementedError


class SuspectDialog(_PersonDialog):
    def __init__(self, master, repos, case_id: int) -> None:
        self.repos = repos
        self.case_id = case_id
        super().__init__(master, "Add a suspect", size=(700, 600))

    def build(self, form: FormPanel) -> None:
        form.add_entry("name", "Full name", placeholder="Name of the suspect", required=True)
        form.add_entry("alias", "Alias", placeholder="Known alias")
        form.add_date("dob", "Date of birth")
        form.add_choice("gender", "Gender", GENDERS)
        form.add_entry("phone", "Phone")
        form.add_entry("address", "Address")
        form.add_entry("marks", "Identifying marks", placeholder="Scars, tattoos, mannerisms")
        form.add_choice("status", "Status", SUSPECT_STATUSES)
        form.add_text("note", "Notes", height=90)

    def on_save(self, values: dict[str, Any]) -> None:
        self.repos.suspects.create(
            self.case_id, values["name"], alias=values.get("alias") or None,
            date_of_birth=values.get("dob") or None, gender=values.get("gender", "unknown"),
            address=values.get("address") or None, phone=values.get("phone") or None,
            identifying_marks=values.get("marks") or None,
            status=values.get("status", "wanted"),
        )


class VictimDialog(_PersonDialog):
    def __init__(self, master, repos, case_id: int) -> None:
        self.repos = repos
        self.case_id = case_id
        super().__init__(master, "Add a victim", size=(680, 560))

    def build(self, form: FormPanel) -> None:
        form.add_entry("name", "Full name", placeholder="Name of the victim", required=True)
        form.add_entry("age", "Age")
        form.add_choice("gender", "Gender", GENDERS)
        form.add_entry("phone", "Phone")
        form.add_entry("address", "Address")
        form.add_choice("injury", "Injury level", INJURY_LEVELS)
        form.add_text("statement", "Statement", height=110)

    def on_save(self, values: dict[str, Any]) -> None:
        age = int(values["age"]) if values.get("age", "").isdigit() else None
        self.repos.victims.create(
            self.case_id, values["name"], age=age, gender=values.get("gender", "unknown"),
            phone=values.get("phone") or None, address=values.get("address") or None,
            injury_level=values.get("injury", "none"), statement=values.get("statement") or None,
        )


class WitnessDialog(_PersonDialog):
    def __init__(self, master, repos, case_id: int) -> None:
        self.repos = repos
        self.case_id = case_id
        super().__init__(master, "Add a witness", size=(660, 540))

    def build(self, form: FormPanel) -> None:
        form.add_entry("name", "Full name", placeholder="Name of the witness", required=True)
        form.add_entry("phone", "Phone")
        form.add_entry("address", "Address")
        form.add_choice("reliable", "Statement reliable", ["Yes", "No"])
        form.add_text("statement", "Statement", height=120)

    def on_save(self, values: dict[str, Any]) -> None:
        self.repos.witnesses.create(
            self.case_id, values["name"], phone=values.get("phone") or None,
            address=values.get("address") or None, statement=values.get("statement") or None,
            is_reliable=values.get("reliable", "Yes") == "Yes",
        )


class _PeopleView(BaseView):
    """Shared list behaviour for the three people registers."""

    title_text = ""
    empty_text = ""

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(self, fg_color=PALETTE.SURFACE, corner_radius=RADIUS)
        bar.grid(row=0, column=0, sticky="ew", padx=PAD_LG, pady=(PAD_LG, PAD))
        bar.grid_columnconfigure(1, weight=1)

        self.search = ctk.CTkEntry(
            bar, height=36, placeholder_text="Search by name or case number",
            font=fonts().body, fg_color=PALETTE.SURFACE_ALT,
            border_color=PALETTE.BORDER, border_width=1,
        )
        self.search.grid(row=0, column=0, sticky="ew", padx=(PAD, PAD_SM), pady=PAD)
        self.search.bind("<Return>", lambda _e: self.refresh())

        if self.can_write():
            ctk.CTkButton(
                bar, text="Open a case to add", width=200, height=36, font=fonts().body,
                fg_color=PALETTE.SURFACE_ALT, hover_color=PALETTE.SURFACE_HOVER,
                text_color=PALETTE.TEXT_MUTED, state="disabled",
            ).grid(row=0, column=1, sticky="e", padx=(0, PAD), pady=PAD)

        self.table = DataTable(
            self, self.columns(), title=self.title_text, empty_text=self.empty_text,
            on_row_double=lambda row: self.app.navigate("cases", case_id=row["case_id"]),
        )
        self.table.grid(row=1, column=0, sticky="nsew", padx=PAD_LG, pady=(0, PAD_LG))

    def columns(self) -> list[Column]:
        raise NotImplementedError

    def load(self) -> list[dict]:
        raise NotImplementedError

    def refresh(self) -> None:
        self.table.set_rows(self.guard(self.load) or [])


class SuspectsView(_PeopleView):
    title_text = "Suspect register"
    empty_text = "No suspects recorded yet. Open a case to add one."

    def columns(self) -> list[Column]:
        return [
            Column("name", "Name", 180),
            Column("alias", "Alias", 130),
            Column("gender", "Gender", 100),
            Column("status", "Status", 140),
            Column("case_no", "Case", 120),
            Column("case_category", "Category", 130),
            Column("arrest_count", "Arrests", 90, anchor="center"),
            Column("total_sentence_years", "Sentence (yrs)", 120, anchor="e"),
        ]

    def load(self) -> list[dict]:
        return self.repos.suspects.list_all(search=self.search.get().strip() or None)


class VictimsView(_PeopleView):
    title_text = "Victim register"
    empty_text = "No victims recorded yet. Open a case to add one."

    def columns(self) -> list[Column]:
        return [
            Column("name", "Name", 180),
            Column("age", "Age", 80, anchor="center"),
            Column("gender", "Gender", 100),
            Column("injury_level", "Injury", 130),
            Column("phone", "Phone", 140),
            Column("case_no", "Case", 120),
        ]

    def load(self) -> list[dict]:
        return self.repos.victims.list_all(search=self.search.get().strip() or None)


class WitnessesView(_PeopleView):
    title_text = "Witness register"
    empty_text = "No witnesses recorded yet. Open a case to add one."

    def columns(self) -> list[Column]:
        return [
            Column("name", "Name", 180),
            Column("phone", "Phone", 140),
            Column("is_reliable", "Reliable", 100, anchor="center",
                   render=lambda row: "Yes" if row.get("is_reliable") else "No"),
            Column("case_no", "Case", 120),
            Column("statement", "Statement", 420),
        ]

    def load(self) -> list[dict]:
        return self.repos.witnesses.list_all(search=self.search.get().strip() or None)
