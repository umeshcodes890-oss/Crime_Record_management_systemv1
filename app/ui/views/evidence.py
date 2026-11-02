"""Evidence register screen."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from app.ui.dialogs import FormDialog
from app.ui.theme import PAD, PAD_LG, PAD_SM, RADIUS, fonts
from app.ui.views.base import BaseView
from app.ui.widgets import PALETTE, Column, DataTable, FormPanel

EVIDENCE_TYPES = ["physical", "documentary", "digital", "forensic", "testimonial"]


class EvidenceDialog(FormDialog):
    def __init__(self, master, repos, case_id: int) -> None:
        self.repos = repos
        self.case_id = case_id
        super().__init__(master, "Record evidence", size=(700, 600))

    def build(self, form: FormPanel) -> None:
        officers = self.repos.officers.options()
        form.add_choice("type", "Evidence type", EVIDENCE_TYPES, required=True)
        form.add_choice("officer", "Collected by",
                        [f"{row['name']} - {row['rank']}" for row in officers], required=True)
        form.add_entry("description", "Description", placeholder="What was seized",
                       required=True)
        form.add_datetime("collected", "Collected on", required=True)
        form.add_entry("seized", "Seized under", placeholder="Section and warrant")
        form.add_entry("storage", "Storage location", placeholder="e.g. Almirah 4, Rack B")
        form.add_datetime("custody", "Chain of custody")

    def on_save(self, values: dict[str, Any]) -> None:
        officers = self.repos.officers.options()
        label = values["officer"]
        officer = next((row for row in officers
                        if label.startswith(row["name"])), officers[0])
        self.repos.evidence.create(
            self.case_id, values["type"], values["description"], officer["officer_id"],
            values["collected"], values.get("seized") or None,
            values.get("storage") or None, values.get("custody") or None,
        )


class EvidenceView(BaseView):
    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(self, fg_color=PALETTE.SURFACE, corner_radius=RADIUS)
        bar.grid(row=0, column=0, sticky="ew", padx=PAD_LG, pady=(PAD_LG, PAD))
        bar.grid_columnconfigure(1, weight=1)

        self.search = ctk.CTkEntry(
            bar, height=36, placeholder_text="Search description, case or storage",
            font=fonts().body, fg_color=PALETTE.SURFACE_ALT,
            border_color=PALETTE.BORDER, border_width=1,
        )
        self.search.grid(row=0, column=0, sticky="ew", padx=(PAD, PAD_SM), pady=PAD)
        self.search.bind("<Return>", lambda _e: self.refresh())

        self.type_filter = ctk.CTkOptionMenu(
            bar, values=["All types"] + EVIDENCE_TYPES, height=36, font=fonts().body,
            fg_color=PALETTE.SURFACE_ALT, button_color=PALETTE.SURFACE_HOVER,
            button_hover_color=PALETTE.BORDER, text_color=PALETTE.TEXT,
            dropdown_fg_color=PALETTE.SURFACE, dropdown_text_color=PALETTE.TEXT,
            dropdown_hover_color=PALETTE.SURFACE_HOVER,
            command=lambda _value: self.refresh(),
        )
        self.type_filter.grid(row=0, column=1, sticky="e", padx=(0, PAD), pady=PAD)

        self.table = DataTable(
            self,
            [
                Column("case_no", "Case", 120),
                Column("type", "Type", 120),
                Column("description", "Description", 320),
                Column("collected_by_name", "Collected by", 160),
                Column("collected_datetime", "Collected", 150),
                Column("chain_of_custody_datetime", "Chain of custody", 150),
                Column("storage_location", "Storage", 150),
            ],
            title="Evidence register",
            empty_text="No evidence has been recorded yet.",
            on_row_double=lambda row: self.app.navigate("cases", case_id=row["case_id"]),
            on_delete=self._delete if self.can_write() else None,
        )
        self.table.grid(row=1, column=0, sticky="nsew", padx=PAD_LG, pady=(0, PAD_LG))
        self.refresh()

    def refresh(self) -> None:
        evidence_type = self.type_filter.get()
        if evidence_type == "All types":
            evidence_type = None
        rows = self.guard(
            self.repos.evidence.list_all,
            evidence_type=evidence_type,
            search=self.search.get().strip() or None,
        )
        self.table.set_rows(rows or [])

    def _delete(self, row: dict) -> None:
        if self.delete_record(
            f"Evidence '{row['description']}'",
            lambda: self.repos.evidence.delete(row["evidence_id"]),
        ):
            self.refresh()
