"""Evidence register screen.

The register is where an item is found; the profile behind each row is
where its collection detail, filed copies, chain of custody and forensic
requests live. An item is recorded from the case it belongs to, so this
screen reads and removes but never invents a case link.
"""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from app.db.connection import DatabaseError
from app.ui.dialogs import FormDialog, officer_choices, officer_id_for
from app.ui.options import (
    EVIDENCE_CATEGORIES, EVIDENCE_CONDITIONS, EVIDENCE_STATUSES, EVIDENCE_TYPES,
    FORENSIC_STATUSES, pretty,
)
from app.ui.theme import PAD, PAD_LG, PAD_SM, RADIUS, fonts
from app.ui.views.base import BaseView
from app.ui.views.evidence_profile import EvidenceProfileView
from app.ui.widgets import PALETTE, Column, DataTable, FormPanel, filter_menu


class EvidenceDialog(FormDialog):
    """The first record of an item, made when it is seized."""

    def __init__(self, master, repos, case_id: int) -> None:
        self.repos = repos
        self.case_id = case_id
        super().__init__(master, "Record evidence", size=(760, 640))

    def build(self, form: FormPanel) -> None:
        self._officers = self.repos.officers.options()
        form.add_entry("item_name", "Item name", required=True,
                       placeholder="e.g. Black laptop, Dell Inspiron")
        form.add_choice("type", "Evidence type", EVIDENCE_TYPES, required=True)
        form.add_choice("evidence_category", "Category", EVIDENCE_CATEGORIES)
        form.add_choice("officer", "Collected by",
                        officer_choices(self._officers), required=True)
        form.add_datetime("collected", "Collected on", required=True)
        form.add_entry("collection_location", "Collected at")
        form.add_choice("condition", "Condition", EVIDENCE_CONDITIONS)
        form.add_entry("packaging_type", "Packaging",
                       placeholder="e.g. Sealed plastic bag")
        form.add_entry("seal_number", "Seal number")
        form.add_entry("seized", "Seized under", placeholder="Section and warrant")
        form.add_entry("storage", "Storage location", placeholder="e.g. Almirah 4, Rack B")
        form.add_datetime("custody", "Chain opened on")
        form.add_text("description", "Short description", height=70, required=True)
        form.add_text("detailed_description", "Full description", height=100)

    def on_save(self, values: dict[str, Any]) -> None:
        if not values.get("item_name") or not values.get("description"):
            raise DatabaseError("Name the item and say what it is.")
        officer_id = officer_id_for(self._officers, values.get("officer"))
        if officer_id is None:
            raise DatabaseError("Say which officer collected the item.")
        self.repos.evidence.create(
            self.case_id, values["type"], values["description"], officer_id,
            values["collected"], values.get("seized") or None,
            values.get("storage") or None, values.get("custody") or None,
            item_name=values["item_name"],
            evidence_category=values.get("evidence_category") or None,
            condition=values.get("condition") or None,
            packaging_type=values.get("packaging_type") or None,
            seal_number=values.get("seal_number") or None,
            collection_location=values.get("collection_location") or None,
            detailed_description=values.get("detailed_description") or None,
        )


class EvidenceView(BaseView):
    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.detail: ctk.CTkFrame | None = None
        self._defaults: dict[ctk.CTkOptionMenu, str] = {}

        self.list_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.list_frame.grid(row=0, column=0, sticky="nsew")
        self.list_frame.grid_rowconfigure(1, weight=1)
        self.list_frame.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(self.list_frame, fg_color=PALETTE.SURFACE, corner_radius=RADIUS)
        bar.grid(row=0, column=0, sticky="ew", padx=PAD_LG, pady=(PAD_LG, PAD))
        bar.grid_columnconfigure(0, weight=1)

        self.search = ctk.CTkEntry(
            bar, height=36, placeholder_text="Search item, reference, seal, storage or case",
            font=fonts().body, fg_color=PALETTE.SURFACE_ALT,
            border_color=PALETTE.BORDER, border_width=1,
        )
        self.search.grid(row=0, column=0, sticky="ew", padx=(PAD, PAD), pady=PAD)
        self.search.bind("<Return>", lambda _e: self.refresh())

        self.filters = ctk.CTkFrame(bar, fg_color="transparent")
        self.filters.grid(row=0, column=1, sticky="e", pady=PAD)
        self.type_filter = self._add_filter(["All types"] + EVIDENCE_TYPES)
        self.category_filter = self._add_filter(["All categories"] + EVIDENCE_CATEGORIES)
        self.status_filter = self._add_filter(["Any state"] + EVIDENCE_STATUSES)
        self.forensic_filter = self._add_filter(["Any forensic state"] + FORENSIC_STATUSES)

        ctk.CTkButton(
            bar, text="Clear", width=90, height=36, font=fonts().body,
            fg_color="transparent", border_width=1, border_color=PALETTE.BORDER,
            text_color=PALETTE.TEXT_MUTED, hover_color=PALETTE.SURFACE_HOVER,
            command=self._clear_filters,
        ).grid(row=0, column=2, sticky="e", padx=(PAD, PAD), pady=PAD)

        self.table = DataTable(
            self.list_frame,
            [
                Column("is_prime", "Prime", 80, anchor="center",
                       render=lambda row: "Prime" if row.get("is_prime") else "-"),
                Column("evidence_ref", "Ref", 130),
                Column("item_name", "Item", 180),
                Column("type", "Type", 110),
                Column("evidence_category", "Category", 120,
                       render=lambda row: pretty(row.get("evidence_category"))),
                Column("evidence_status", "State", 130,
                       render=lambda row: pretty(row.get("evidence_status"))),
                Column("forensic_status", "Forensic", 140,
                       render=lambda row: pretty(row.get("forensic_status"))),
                Column("condition", "Condition", 110,
                       render=lambda row: pretty(row.get("condition"))),
                Column("collected_by_name", "Collected by", 160),
                Column("collected_datetime", "Collected", 150),
                Column("storage_location", "Storage", 140),
                Column("case_no", "Case", 110),
            ],
            title="Evidence register",
            empty_text="No evidence matches these filters. An item is recorded from "
                       "the case it belongs to.",
            on_row_double=lambda row: self.open_detail(evidence_id=row["evidence_id"]),
            on_delete=self._delete if self.can_write() else None,
        )
        self.table.grid(row=1, column=0, sticky="nsew", padx=PAD_LG, pady=(0, PAD_LG))
        self.refresh()

    # -- filters --------------------------------------------------------
    def _add_filter(self, values: list[str]) -> ctk.CTkOptionMenu:
        menu = filter_menu(self.filters, values, on_change=self.refresh)
        menu.pack(side="left", padx=(PAD_SM, 0))
        self._defaults[menu] = values[0]
        return menu

    def _filter_value(self, menu: ctk.CTkOptionMenu) -> str | None:
        label = menu.get()
        return None if label == self._defaults[menu] else label

    def _clear_filters(self) -> None:
        self.search.delete(0, "end")
        for menu, everything in self._defaults.items():
            menu.set(everything)
        self.refresh()

    # -- the list -------------------------------------------------------
    def refresh(self) -> None:
        rows = self.guard(
            self.repos.evidence.list_all,
            evidence_type=self._filter_value(self.type_filter),
            search=self.search.get().strip() or None,
            category=self._filter_value(self.category_filter),
            status=self._filter_value(self.status_filter),
            forensic_status=self._filter_value(self.forensic_filter),
        )
        self.table.set_rows(rows or [])

    def _delete(self, row: dict) -> None:
        if self.delete_record(
            f"Evidence '{row.get('item_name') or row['description']}'",
            lambda: self.repos.evidence.delete(row["evidence_id"]),
        ):
            self.refresh()

    # -- the profile ----------------------------------------------------
    def open_detail(self, evidence_id: int) -> None:
        if self.detail is not None:
            self.detail.destroy()
        self.detail = EvidenceProfileView(
            self, self.app, evidence_id, self._back_to_list)
        self.detail.grid(row=0, column=0, sticky="nsew")
        self.list_frame.grid_remove()

    def _back_to_list(self) -> None:
        if self.detail is not None:
            self.detail.destroy()
            self.detail = None
        self.list_frame.grid()
        self.refresh()
