"""Suspects, victims and witnesses registers.

The victim and witness registers open a profile page, so a person's own
detail - statements, contacts, medical records, interviews, protection -
is one double-click away instead of a column in a table.
"""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from app.ui.dialogs import FormDialog
from app.ui.options import (
    AVAILABILITY, CONFIDENTIALITY_LEVELS, GENDERS, INJURY_LEVELS,
    MEDICAL_ASSISTANCE, WITNESS_TYPES, YES_NO, pretty,
)
from app.ui.theme import PAD, PAD_LG, PAD_SM, RADIUS, fonts
from app.ui.views.base import BaseView
from app.ui.views.victim_profile import VictimProfileView
from app.ui.views.witness_profile import WitnessProfileView
from app.ui.widgets import PALETTE, Column, DataTable, FormPanel, clip, filter_menu

SUSPECT_STATUSES = [
    "wanted", "arrested", "in_custody", "bailed", "released",
    "convicted", "acquitted", "untraceable",
]


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
    """The few fields that make a victim findable; the profile holds the rest."""

    def __init__(self, master, repos, case_id: int) -> None:
        self.repos = repos
        self.case_id = case_id
        super().__init__(master, "Add a victim", size=(720, 600))

    def build(self, form: FormPanel) -> None:
        form.add_entry("name", "Full name", placeholder="Name of the victim", required=True)
        form.add_entry("age", "Age")
        form.add_choice("gender", "Gender", GENDERS)
        form.add_date("date_of_birth", "Date of birth")
        form.add_entry("phone", "Phone")
        form.add_entry("address", "Address")
        form.add_choice("injury_level", "Injury level", INJURY_LEVELS)
        form.add_choice("medical_assistance_status", "Medical assistance",
                        MEDICAL_ASSISTANCE)
        form.add_entry("hospital_name", "Hospital")
        form.add_choice("confidentiality_level", "Confidentiality", CONFIDENTIALITY_LEVELS)
        form.add_text("statement", "Statement", height=120)
        # A dropdown starts on its first value, so the ones that carry
        # meaning are set to the answer a new record should not assume.
        form.set("gender", "unknown")
        form.set("injury_level", "none")
        form.set("medical_assistance_status", "none")
        form.set("confidentiality_level", "internal")

    def on_save(self, values: dict[str, Any]) -> None:
        age = values.get("age") or ""
        self.repos.victims.create(
            self.case_id, values["name"],
            age=int(age) if age.isdigit() else None,
            gender=values.get("gender") or "unknown",
            date_of_birth=values.get("date_of_birth") or None,
            phone=values.get("phone") or None,
            address=values.get("address") or None,
            injury_level=values.get("injury_level") or "none",
            medical_assistance_status=values.get("medical_assistance_status") or "none",
            hospital_name=values.get("hospital_name") or None,
            confidentiality_level=values.get("confidentiality_level") or "internal",
            statement=values.get("statement") or None,
        )


class WitnessDialog(_PersonDialog):
    """Record a witness.

    Whether their account is believed is deliberately not asked here: that
    is a decision somebody signs for on the witness profile, with a reason.
    """

    def __init__(self, master, repos, case_id: int) -> None:
        self.repos = repos
        self.case_id = case_id
        super().__init__(master, "Add a witness", size=(720, 600))

    def build(self, form: FormPanel) -> None:
        form.add_entry("name", "Full name", placeholder="Name of the witness", required=True)
        form.add_choice("witness_type", "Witness type", WITNESS_TYPES)
        form.add_choice("gender", "Gender", GENDERS)
        form.add_date("date_of_birth", "Date of birth")
        form.add_entry("phone", "Phone")
        form.add_entry("email", "Email")
        form.add_entry("address", "Address")
        form.add_entry("occupation", "Occupation")
        form.add_choice("availability_status", "Availability", AVAILABILITY)
        form.add_choice("protection_required", "Protection needed", YES_NO)
        form.add_choice("confidentiality_level", "Confidentiality", CONFIDENTIALITY_LEVELS)
        form.add_entry("statement_language", "Speaks")
        form.add_text("statement", "Statement", height=120)
        form.set("gender", "unknown")
        form.set("availability_status", "unknown")
        form.set("protection_required", "No")
        form.set("confidentiality_level", "internal")

    def on_save(self, values: dict[str, Any]) -> None:
        self.repos.witnesses.create(
            self.case_id, values["name"],
            statement=values.get("statement") or None,
            gender=values.get("gender") or "unknown",
            date_of_birth=values.get("date_of_birth") or None,
            phone=values.get("phone") or None,
            email=values.get("email") or None,
            address=values.get("address") or None,
            occupation=values.get("occupation") or None,
            witness_type=values.get("witness_type") or "eyewitness",
            availability_status=values.get("availability_status") or "available",
            protection_required=values.get("protection_required") == "Yes",
            confidentiality_level=values.get("confidentiality_level") or "internal",
            statement_language=values.get("statement_language") or None,
        )


class _PeopleView(BaseView):
    """A register of people, with the profile page it opens into."""

    title_text = ""
    empty_text = ""
    detail_key = ""
    profile: type | None = None

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.detail: ctk.CTkFrame | None = None
        self._defaults: dict[ctk.CTkOptionMenu, str] = {}

        self.list_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.list_frame.grid(row=0, column=0, sticky="nsew")
        self.list_frame.grid_rowconfigure(1, weight=1)
        self.list_frame.grid_columnconfigure(0, weight=1)

        self._build_bar()

        self.table = DataTable(
            self.list_frame, self.columns(), title=self.title_text,
            empty_text=self.empty_text, on_row_double=self._open_row,
            on_delete=self._delete if self.can_write() else None,
        )
        self.table.grid(row=1, column=0, sticky="nsew",
                        padx=PAD_LG, pady=(0, PAD_LG))
        self.refresh()

    # -- the bar --------------------------------------------------------
    def _build_bar(self) -> None:
        bar = ctk.CTkFrame(self.list_frame, fg_color=PALETTE.SURFACE, corner_radius=RADIUS)
        bar.grid(row=0, column=0, sticky="ew", padx=PAD_LG, pady=(PAD_LG, PAD))
        bar.grid_columnconfigure(0, weight=1)

        self.search = ctk.CTkEntry(
            bar, height=36, placeholder_text="Search by name or case number",
            font=fonts().body, fg_color=PALETTE.SURFACE_ALT,
            border_color=PALETTE.BORDER, border_width=1,
        )
        self.search.grid(row=0, column=0, sticky="ew", padx=(PAD, PAD_SM), pady=PAD)
        self.search.bind("<Return>", lambda _e: self.refresh())

        self.filters = ctk.CTkFrame(bar, fg_color="transparent")
        self.build_filters()
        # An empty frame still asks for 250 pixels of height, which is the
        # whole gap a register without filters would otherwise not have.
        if self.filters.winfo_children():
            self.filters.grid(row=0, column=1, sticky="e", pady=PAD)
        else:
            self.filters.destroy()
            self.filters = None

        ctk.CTkButton(
            bar, text="Clear", width=90, height=36, font=fonts().body,
            fg_color="transparent", border_width=1, border_color=PALETTE.BORDER,
            text_color=PALETTE.TEXT_MUTED, hover_color=PALETTE.SURFACE_HOVER,
            command=self._clear_filters,
        ).grid(row=0, column=2, sticky="e", padx=(PAD_SM, PAD), pady=PAD)

    def build_filters(self) -> None:
        """Add this register's dropdowns. Overridden by each screen."""

    def _add_filter(self, values: list[str]) -> ctk.CTkOptionMenu:
        menu = filter_menu(self.filters, values, on_change=self.refresh)
        menu.pack(side="left", padx=(PAD_SM, 0))
        self._defaults[menu] = values[0]
        return menu

    def _filter_value(self, menu: ctk.CTkOptionMenu | None) -> str | None:
        """What a dropdown stands for, or None when it asks for everything."""
        if menu is None:
            return None
        label = menu.get()
        return None if label == self._defaults[menu] else label

    def _clear_filters(self) -> None:
        self.search.delete(0, "end")
        for menu, everything in self._defaults.items():
            menu.set(everything)
        self.refresh()

    # -- the list -------------------------------------------------------
    def columns(self) -> list[Column]:
        raise NotImplementedError

    def load(self) -> list[dict]:
        raise NotImplementedError

    def refresh(self) -> None:
        self.table.set_rows(self.guard(self.load) or [])

    def _delete(self, row: dict) -> None:
        raise NotImplementedError

    # -- the profile ----------------------------------------------------
    def _open_row(self, row: dict) -> None:
        if self.profile is None:
            self.app.navigate("cases", case_id=row["case_id"])
            return
        self.open_detail(**{self.detail_key: row[self.detail_key]})

    def open_detail(self, **key) -> None:
        self._show_profile(key[self.detail_key])

    def _show_profile(self, record_id: int) -> None:
        if self.detail is not None:
            self.detail.destroy()
        self.detail = self.profile(self, self.app, record_id, self._back_to_list)
        self.detail.grid(row=0, column=0, sticky="nsew")
        self.list_frame.grid_remove()

    def _back_to_list(self) -> None:
        if self.detail is not None:
            self.detail.destroy()
            self.detail = None
        self.list_frame.grid()
        self.refresh()


class SuspectsView(_PeopleView):
    title_text = "Suspect register"
    empty_text = "No suspects recorded yet. Open a case to add one."

    def build_filters(self) -> None:
        self.status_filter = self._add_filter(["Any status"] + SUSPECT_STATUSES)

    def columns(self) -> list[Column]:
        return [
            Column("is_prime", "Prime", 80, anchor="center",
                   render=lambda row: "Prime" if row.get("is_prime") else "-"),
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
        return self.repos.suspects.list_all(
            search=self.search.get().strip() or None,
            status=self._filter_value(self.status_filter),
        )

    def _delete(self, row: dict) -> None:
        if self.delete_record(
            f"Suspect '{row['name']}'",
            lambda: self.repos.suspects.delete(row["suspect_id"]),
        ):
            self.refresh()


class VictimsView(_PeopleView):
    title_text = "Victim register"
    empty_text = ("No victims match these filters. A victim is recorded from the "
                  "case they belong to.")
    detail_key = "victim_id"
    profile = VictimProfileView

    def build_filters(self) -> None:
        self.injury_filter = self._add_filter(["Any injury"] + INJURY_LEVELS)
        self.gender_filter = self._add_filter(["Any gender"] + GENDERS)
        self.assistance_filter = self._add_filter(["Any assistance"] + MEDICAL_ASSISTANCE)
        self.confidentiality_filter = self._add_filter(
            ["Any confidentiality"] + CONFIDENTIALITY_LEVELS)

    def columns(self) -> list[Column]:
        return [
            Column("is_prime", "Prime", 80, anchor="center",
                   render=lambda row: "Prime" if row.get("is_prime") else "-"),
            Column("name", "Name", 170),
            Column("age", "Age", 70, anchor="center"),
            Column("gender", "Gender", 90, render=lambda row: pretty(row.get("gender"))),
            Column("injury_level", "Injury", 110, render=lambda row: pretty(row.get("injury_level"))),
            Column("medical_assistance_status", "Medical help", 120,
                   render=lambda row: pretty(row.get("medical_assistance_status"))),
            Column("hospital_name", "Hospital", 160),
            Column("phone", "Phone", 130),
            Column("case_no", "Case", 120),
            Column("confidentiality_level", "Confidentiality", 130,
                   render=lambda row: pretty(row.get("confidentiality_level"))),
        ]

    def load(self) -> list[dict]:
        return self.repos.victims.list_all(
            self.search.get().strip() or None,
            injury_level=self._filter_value(self.injury_filter),
            gender=self._filter_value(self.gender_filter),
            medical_assistance_status=self._filter_value(self.assistance_filter),
            confidentiality_level=self._filter_value(self.confidentiality_filter),
        )

    def _delete(self, row: dict) -> None:
        if self.delete_record(
            f"Victim '{row['name']}'",
            lambda: self.repos.victims.delete(row["victim_id"]),
        ):
            self.refresh()


class WitnessesView(_PeopleView):
    title_text = "Witness register"
    empty_text = ("No witnesses match these filters. A witness is recorded from the "
                  "case they belong to.")
    detail_key = "witness_id"
    profile = WitnessProfileView

    def build_filters(self) -> None:
        self.type_filter = self._add_filter(["Any type"] + WITNESS_TYPES)
        self.availability_filter = self._add_filter(["Anyone"] + AVAILABILITY)
        self.protection_filter = self._add_filter(
            ["Protection: anyone", "Only protected", "No order"])
        self.confidentiality_filter = self._add_filter(
            ["Any confidentiality"] + CONFIDENTIALITY_LEVELS)

    def columns(self) -> list[Column]:
        return [
            Column("name", "Name", 170),
            Column("witness_type", "Type", 120,
                   render=lambda row: pretty(row.get("witness_type"))),
            Column("availability_status", "Available", 120,
                   render=lambda row: pretty(row.get("availability_status"))),
            Column("protection_required", "Protection", 100, anchor="center",
                   render=lambda row: "Ordered" if row.get("protection_required") else "-"),
            Column("phone", "Phone", 130),
            Column("case_no", "Case", 120),
            Column("confidentiality_level", "Confidentiality", 130,
                   render=lambda row: pretty(row.get("confidentiality_level"))),
            Column("statement", "Account", 320, render=lambda row: clip(row.get("statement"))),
        ]

    def load(self) -> list[dict]:
        protected = self.protection_filter.get()
        return self.repos.witnesses.list_all(
            self.search.get().strip() or None,
            witness_type=self._filter_value(self.type_filter),
            availability_status=self._filter_value(self.availability_filter),
            protection_required=None if protected == "Protection: anyone"
            else protected == "Only protected",
            confidentiality_level=self._filter_value(self.confidentiality_filter),
        )

    def _delete(self, row: dict) -> None:
        if self.delete_record(
            f"Witness '{row['name']}'",
            lambda: self.repos.witnesses.delete(row["witness_id"]),
        ):
            self.refresh()
