"""Court proceedings, arrests and convictions."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from app.ui.dialogs import FormDialog
from app.ui.theme import PAD, PAD_LG
from app.ui.views.base import BaseView
from app.ui.widgets import Column, DataTable, FormPanel

STAGES = ["first_hearing", "charge_frame", "evidence", "arguments", "verdict"]
VERDICTS = ["guilty", "acquitted", "case_dismissed"]
SENTENCE_TYPES = ["none", "fine", "imprisonment", "community_service", "life_imprisonment"]
REMAND_STATUSES = ["not_remanded", "police_remand", "judicial_remand", "bail"]


class ProceedingDialog(FormDialog):
    def __init__(self, master, repos, case_id: int) -> None:
        self.repos = repos
        self.case_id = case_id
        super().__init__(master, "Add a court proceeding", size=(680, 520))

    def build(self, form: FormPanel) -> None:
        form.add_entry("court", "Court name", placeholder="e.g. Sessions Court, Hyderabad",
                       required=True)
        form.add_choice("stage", "Stage", STAGES, required=True)
        form.add_datetime("hearing", "Hearing date and time", required=True)
        form.add_entry("judge", "Presiding judge")
        form.add_datetime("next", "Next hearing")
        form.add_text("remarks", "Remarks", height=100)

    def on_save(self, values: dict[str, Any]) -> None:
        self.repos.proceedings.create(
            self.case_id, values["court"], values["hearing"], values["stage"],
            values.get("judge") or None, values.get("next") or None,
            values.get("remarks") or None,
        )


class ConvictionDialog(FormDialog):
    def __init__(self, master, repos, case_id: int, user) -> None:
        self.repos = repos
        self.case_id = case_id
        self.user = user
        super().__init__(master, "Record a conviction", size=(700, 600))

    def build(self, form: FormPanel) -> None:
        suspects = self.repos.suspects.for_case(self.case_id)
        form.add_choice("suspect", "Suspect",
                        [row["name"] for row in suspects] or ["No suspects on this case"],
                        required=True)
        form.add_entry("court", "Court name", placeholder="Court that delivered the verdict",
                       required=True)
        form.add_choice("verdict", "Verdict", VERDICTS, required=True)
        form.add_choice("sentence", "Sentence type", SENTENCE_TYPES, required=True)
        form.add_entry("years", "Imprisonment in years")
        form.add_entry("fine", "Fine amount")
        form.add_date("start", "Sentence start date")
        form.add_date("release", "Release expected")

    def on_save(self, values: dict[str, Any]) -> None:
        suspects = self.repos.suspects.for_case(self.case_id)
        suspect = next((row for row in suspects if row["name"] == values["suspect"]), None)
        if suspect is None:
            raise ValueError("Choose a suspect for this conviction.")

        years = float(values["years"]) if values.get("years", "").replace(".", "", 1).isdigit() else None
        fine = float(values["fine"]) if values.get("fine", "").replace(".", "", 1).isdigit() else None

        self.repos.convictions.record(
            self.case_id, suspect["suspect_id"], self.user["user_id"], values["court"],
            values["verdict"], values["sentence"], years, fine,
            values.get("start") or None, values.get("release") or None,
        )


class CourtView(BaseView):
    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)
        body.grid_columnconfigure(0, weight=1)

        self.proceedings_table = DataTable(
            body,
            [
                Column("case_no", "Case", 120),
                Column("court_name", "Court", 220),
                Column("hearing_datetime", "Hearing", 160),
                Column("stage", "Stage", 140),
                Column("judge_name", "Judge", 160),
                Column("next_hearing_datetime", "Next hearing", 160),
                Column("station_name", "Station", 150),
            ],
            title="Court proceedings",
            empty_text="No court proceedings recorded yet.",
            on_row_double=lambda row: self.app.navigate("cases", case_id=row["case_id"]),
            on_delete=self._delete_proceeding if self.can_write() else None,
        )
        self.proceedings_table.grid(row=0, column=0, sticky="nsew", padx=PAD_LG, pady=(PAD_LG, PAD))

        self.convictions_table = DataTable(
            body,
            [
                Column("case_no", "Case", 120),
                Column("suspect_name", "Suspect", 180),
                Column("court_name", "Court", 220),
                Column("verdict", "Verdict", 130),
                Column("sentence_type", "Sentence", 160),
                Column("imprisonment_years", "Years", 90, anchor="center"),
                Column("fine_amount", "Fine", 110, anchor="e"),
                Column("release_expected", "Release expected", 150),
            ],
            title="Convictions",
            empty_text="No convictions recorded yet.",
            on_row_double=lambda row: self.app.navigate("cases", case_id=row["case_id"]),
            on_delete=self._delete_conviction if self.can_write() else None,
        )
        self.convictions_table.grid(row=1, column=0, sticky="nsew", padx=PAD_LG, pady=(0, PAD_LG))
        self.refresh()

    def refresh(self) -> None:
        self.proceedings_table.set_rows(self.guard(self.repos.proceedings.list_all) or [])
        self.convictions_table.set_rows(self.guard(self.repos.convictions.list_all) or [])

    def _delete_proceeding(self, row: dict) -> None:
        if self.delete_record(
            f"Proceeding on {row['hearing_datetime']} at {row['court_name']}",
            lambda: self.repos.proceedings.delete(row["proceeding_id"]),
        ):
            self.refresh()

    def _delete_conviction(self, row: dict) -> None:
        if self.delete_record(
            f"Conviction of {row['suspect_name']} ({row['verdict']})",
            lambda: self.repos.convictions.delete(row["conviction_id"]),
        ):
            self.refresh()
