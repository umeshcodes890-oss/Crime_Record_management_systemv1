"""Case list, filing form and the case detail screen."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from app.db.connection import DatabaseError
from app.ui.dialogs import FormDialog
from app.ui.theme import PAD, PAD_LG, PAD_SM, RADIUS, fonts, status_label
from app.ui.views.base import BaseView
from app.ui.widgets import (
    PALETTE,
    Column,
    DataTable,
    FormPanel,
    StatusPill,
    confirm,
    toast,
)

CATEGORIES = [
    "theft", "assault", "fraud", "homicide", "cyber",
    "missing_person", "arson", "drugs", "other",
]

STATUS_FLOW = {
    "registered": ["under_investigation", "closed_untraceable"],
    "under_investigation": ["charges_filed", "closed_untraceable"],
    "charges_filed": ["trial", "closed_untraceable"],
    "trial": ["closed_convicted", "closed_acquitted", "closed_untraceable"],
    "closed_convicted": [],
    "closed_acquitted": [],
    "closed_untraceable": [],
}


def next_statuses(current: str) -> list[str]:
    return STATUS_FLOW.get(current, [])


# ----------------------------------------------------------------------
class FileCaseDialog(FormDialog):
    """Register a new case and attach the offence sections."""

    def __init__(self, master, repos, user) -> None:
        self.repos = repos
        self.user = user
        self._sections: list[dict] = []
        self._checks: dict[int, ctk.CTkCheckBox] = {}
        super().__init__(master, "File a new case", size=(760, 720), save_text="File case")

    def build(self, form: FormPanel) -> None:
        stations = self.repos.stations.options()
        officers = self.repos.officers.options()
        self._sections = self.repos.offences.options()

        form.add_choice("station", "Police station",
                        [f"{row['name']} ({row['district']})" for row in stations], required=True)
        form.add_choice("officer", "Investigating officer",
                        [f"{row['name']} - {row['rank']}" for row in officers], required=True)
        form.add_choice("category", "Category", CATEGORIES, required=True)
        form.add_entry("offence_type", "Offence type",
                       placeholder="e.g. House burglary")
        form.add_datetime("occurrence", "Date and time of occurrence", required=True)
        form.add_datetime("reporting", "Date and time of reporting", required=True)
        form.add_entry("place", "Place of occurrence", placeholder="e.g. 14 Nehru Street")
        form.add_text("description", "Description of the incident", height=110)

        # offence sections with checkboxes
        holder = ctk.CTkFrame(form, fg_color="transparent")
        holder.grid(row=form._row, column=0, columnspan=2, sticky="ew", pady=(0, PAD))
        holder.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            holder, text="Offence sections charged", font=fonts().label,
            text_color=PALETTE.TEXT_MUTED, anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        scroller = ctk.CTkScrollableFrame(holder, fg_color=PALETTE.SURFACE_ALT,
                                           corner_radius=RADIUS, height=190)
        scroller.grid(row=1, column=0, sticky="ew")
        scroller.grid_columnconfigure(0, weight=1)

        for index, section in enumerate(self._sections):
            check = ctk.CTkCheckBox(
                scroller, text=f"{section['law_code']} {section['section_no']}  "
                               f"{section['offence_name']}",
                font=fonts().small, text_color=PALETTE.TEXT,
                fg_color=PALETTE.ACCENT, hover_color=PALETTE.ACCENT_HOVER,
                border_color=PALETTE.BORDER,
            )
            check.grid(row=index, column=0, sticky="w", padx=PAD, pady=3)
            self._checks[section["section_id"]] = check
        form._row += 1

    def collect(self) -> dict[str, Any]:
        values = super().collect()
        values["section_ids"] = [
            section_id for section_id, check in self._checks.items() if check.get()
        ]
        return values

    def validate(self, values: dict[str, Any]) -> bool:
        if not values.get("station") or not values.get("officer"):
            self.error.configure(text="Choose a station and an investigating officer.")
            return False
        if not values.get("occurrence") or not values.get("reporting"):
            self.error.configure(text="Enter when the incident happened and when it was reported.")
            return False
        if not values.get("section_ids"):
            self.error.configure(text="Select at least one offence section.")
            return False
        return True

    def on_save(self, values: dict[str, Any]) -> None:
        stations = self.repos.stations.options()
        officers = self.repos.officers.options()
        station_id = stations[self._index_for(stations, values["station"])] ["station_id"]
        officer_id = officers[self._index_for(officers, values["officer"])] ["officer_id"]

        result = self.repos.cases.file_case(
            station_id=station_id,
            officer_id=officer_id,
            user_id=self.user["user_id"],
            category=values["category"],
            offence_type=values.get("offence_type") or None,
            occurrence_datetime=values["occurrence"],
            reporting_datetime=values["reporting"],
            place_of_occurrence=values.get("place") or None,
            description=values.get("description") or None,
            section_ids=values["section_ids"],
        )
        self.saved = {**values, "case_id": result["case_id"], "case_no": result["case_no"]}

    @staticmethod
    def _index_for(options: list[dict], label: str) -> int:
        for index, option in enumerate(options):
            if label.startswith(option["name"]) or label.startswith(option["badge_no"]):
                return index
        return 0


# ----------------------------------------------------------------------
class ChangeStatusDialog(FormDialog):
    def __init__(self, master, repos, user, case: dict) -> None:
        self.repos = repos
        self.user = user
        self.case = case
        self._options = next_statuses(case["status"])
        super().__init__(master, f"Update status - {case['case_no']}",
                         size=(520, 380), save_text="Update")

    def build(self, form: FormPanel) -> None:
        form.add_choice("status", "New status",
                        [status_label(option) for option in self._options] or ["No further stage"])
        form.add_entry("remark", "Remark", placeholder="Optional note for the history trail")

    def validate(self, values: dict[str, Any]) -> bool:
        if not self._options:
            self.error.configure(text="This case is already closed.")
            return False
        return True

    def on_save(self, values: dict[str, Any]) -> None:
        label = values["status"]
        target = next(option for option in self._options
                      if status_label(option) == label)
        self.repos.cases.update_status(
            self.case["case_id"], target, self.user["user_id"], values.get("remark") or None
        )


# ----------------------------------------------------------------------
class CasesView(BaseView):
    """The case register: filters, the table and the detail screen."""

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.list_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.list_frame.grid(row=0, column=0, sticky="nsew")
        self.list_frame.grid_rowconfigure(1, weight=1)
        self.list_frame.grid_columnconfigure(0, weight=1)

        self._build_filters()
        self._build_table()

        self.detail: CaseDetailView | None = None
        self.refresh()

    # ------------------------------------------------------------------
    def _build_filters(self) -> None:
        bar = ctk.CTkFrame(self.list_frame, fg_color=PALETTE.SURFACE, corner_radius=RADIUS)
        bar.grid(row=0, column=0, sticky="ew", padx=PAD_LG, pady=(PAD_LG, PAD))
        for index in range(6):
            bar.grid_columnconfigure(index, weight=1)

        self.search = ctk.CTkEntry(
            bar, height=36, placeholder_text="Search case no, place, offence...",
            font=fonts().body, fg_color=PALETTE.SURFACE_ALT,
            border_color=PALETTE.BORDER, border_width=1,
        )
        self.search.grid(row=0, column=0, sticky="ew", padx=(PAD, PAD_SM), pady=PAD)
        self.search.bind("<Return>", lambda _e: self.refresh())

        stations = self.guard(self.repos.stations.options) or []
        self.station_filter = ctk.CTkOptionMenu(
            bar, values=["All stations"] + [row["name"] for row in stations],
            height=36, font=fonts().body, fg_color=PALETTE.SURFACE_ALT,
            button_color=PALETTE.SURFACE_HOVER, button_hover_color=PALETTE.BORDER,
            text_color=PALETTE.TEXT, dropdown_fg_color=PALETTE.SURFACE,
            dropdown_text_color=PALETTE.TEXT, dropdown_hover_color=PALETTE.SURFACE_HOVER,
            command=lambda _value: self.refresh(),
        )
        self.station_filter.grid(row=0, column=1, sticky="ew", padx=(0, PAD_SM), pady=PAD)

        self.status_filter = ctk.CTkOptionMenu(
            bar, values=["All statuses"] + [status_label(s) for s in self.repos.cases.statuses()],
            height=36, font=fonts().body, fg_color=PALETTE.SURFACE_ALT,
            button_color=PALETTE.SURFACE_HOVER, button_hover_color=PALETTE.BORDER,
            text_color=PALETTE.TEXT, dropdown_fg_color=PALETTE.SURFACE,
            dropdown_text_color=PALETTE.TEXT, dropdown_hover_color=PALETTE.SURFACE_HOVER,
            command=lambda _value: self.refresh(),
        )
        self.status_filter.grid(row=0, column=2, sticky="ew", padx=(0, PAD_SM), pady=PAD)

        self.category_filter = ctk.CTkOptionMenu(
            bar, values=["All categories"] + CATEGORIES, height=36, font=fonts().body,
            fg_color=PALETTE.SURFACE_ALT, button_color=PALETTE.SURFACE_HOVER,
            button_hover_color=PALETTE.BORDER, text_color=PALETTE.TEXT,
            dropdown_fg_color=PALETTE.SURFACE, dropdown_text_color=PALETTE.TEXT,
            dropdown_hover_color=PALETTE.SURFACE_HOVER,
            command=lambda _value: self.refresh(),
        )
        self.category_filter.grid(row=0, column=3, sticky="ew", padx=(0, PAD_SM), pady=PAD)

        ctk.CTkButton(
            bar, text="Clear", width=90, height=36, font=fonts().body,
            fg_color="transparent", border_width=1, border_color=PALETTE.BORDER,
            text_color=PALETTE.TEXT_MUTED, hover_color=PALETTE.SURFACE_HOVER,
            command=self._clear_filters,
        ).grid(row=0, column=4, sticky="ew", padx=(0, PAD_SM), pady=PAD)

        if self.can_write():
            ctk.CTkButton(
                bar, text="File a case", width=140, height=36, font=fonts().body_bold,
                fg_color=PALETTE.ACCENT, hover_color=PALETTE.ACCENT_HOVER,
                text_color=PALETTE.ACCENT_TEXT, command=self._file_case,
            ).grid(row=0, column=5, sticky="e", padx=(0, PAD), pady=PAD)

    def _build_table(self) -> None:
        self.table = DataTable(
            self.list_frame,
            [
                Column("case_no", "Case No", 120),
                Column("occurrence_datetime", "Occurred", 150,
                       render=lambda row: row["occurrence_datetime"].strftime("%d %b %Y")
                       if row.get("occurrence_datetime") else "-"),
                Column("category", "Category", 120,
                       render=lambda row: (row.get("category") or "-").replace("_", " ").title()),
                Column("offence_summary", "Offences", 320),
                Column("station_name", "Station", 150),
                Column("investigating_officer", "Investigator", 150),
                Column("status", "Status", 160,
                       render=lambda row: status_label(row.get("status", ""))),
                Column("suspect_count", "Persons", 80, anchor="center"),
            ],
            title="Case register",
            empty_text="No cases match the current filters.",
            on_row_double=self._open_case,
        )
        self.table.grid(row=1, column=0, sticky="nsew", padx=PAD_LG, pady=(0, PAD_LG))

    # ------------------------------------------------------------------
    def _clear_filters(self) -> None:
        self.search.delete(0, "end")
        self.station_filter.set("All stations")
        self.status_filter.set("All statuses")
        self.category_filter.set("All categories")
        self.refresh()

    def _file_case(self) -> None:
        dialog = FileCaseDialog(self, self.repos, self.user)
        result = dialog.show()
        if result:
            self.app.toast(f"Case {result['case_no']} registered", "success")
            self.refresh()
            self.open_detail(case_id=result["case_id"])

    def _open_case(self, row: dict) -> None:
        self.open_detail(case_id=row["case_id"])

    def open_detail(self, case_id: int) -> None:
        if self.detail is not None:
            self.detail.destroy()
        self.detail = CaseDetailView(self, self.app, case_id, self._back_to_list)
        self.detail.grid(row=0, column=0, sticky="nsew")
        self.list_frame.grid_remove()

    def _back_to_list(self) -> None:
        if self.detail is not None:
            self.detail.destroy()
            self.detail = None
        self.list_frame.grid()
        self.refresh()

    def refresh(self) -> None:
        stations = self.guard(self.repos.stations.options) or []
        station_label = self.station_filter.get()
        station_id = None
        if station_label != "All stations":
            station_id = next((row["station_id"] for row in stations
                               if row["name"] == station_label), None)

        status_label_value = self.status_filter.get()
        status = None
        if status_label_value != "All statuses":
            status = next((s for s in self.repos.cases.statuses()
                           if status_label(s) == status_label_value), None)

        category = self.category_filter.get()
        if category == "All categories":
            category = None

        rows = self.guard(
            self.repos.cases.search,
            case_no=None,
            station_id=station_id,
            officer_id=None,
            status=status,
            category=category,
            section_id=None,
            from_date=None,
            to_date=None,
            text=self.search.get().strip() or None,
            limit=500,
        )
        if rows is not None:
            self.table.set_rows(rows)


# ----------------------------------------------------------------------
class CaseDetailView(ctk.CTkFrame):
    """Everything known about one case, tab by tab."""

    def __init__(self, master, app, case_id: int, on_back) -> None:
        super().__init__(master, fg_color=PALETTE.BG)
        self.app = app
        self.db = app.db
        self.user = app.user
        self.case_id = case_id
        self.on_back = on_back

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.repos = RepositoriesProxy(app.db)

        self._build_header()
        self._build_tabs()
        self.reload()

    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=PALETTE.SURFACE, corner_radius=RADIUS)
        header.grid(row=0, column=0, sticky="ew", padx=PAD_LG, pady=(PAD_LG, PAD))
        header.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=(PAD_LG, PAD), pady=PAD)

        ctk.CTkButton(
            left, text="Back", width=80, height=32, font=fonts().small,
            fg_color="transparent", border_width=1, border_color=PALETTE.BORDER,
            text_color=PALETTE.TEXT_MUTED, hover_color=PALETTE.SURFACE_HOVER,
            command=self.on_back,
        ).grid(row=0, column=0, sticky="w", padx=(0, PAD))

        self.case_no_label = ctk.CTkLabel(
            left, text="", font=fonts().title, text_color=PALETTE.TEXT, anchor="w",
        )
        self.case_no_label.grid(row=0, column=1, sticky="w")

        self.subtitle_label = ctk.CTkLabel(
            left, text="", font=fonts().small, text_color=PALETTE.TEXT_MUTED, anchor="w",
        )
        self.subtitle_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e", padx=(0, PAD_LG))

        self.status_pill = StatusPill(right, "", PALETTE.ACCENT)
        self.status_pill.grid(row=0, column=0, padx=(0, PAD_SM))

        if self.user.get("role") in ("admin", "officer"):
            ctk.CTkButton(
                right, text="Update status", width=130, height=36, font=fonts().body,
                fg_color=PALETTE.ACCENT, hover_color=PALETTE.ACCENT_HOVER,
                text_color=PALETTE.ACCENT_TEXT, command=self._change_status,
            ).grid(row=0, column=1, padx=(0, PAD_SM))
            ctk.CTkButton(
                right, text="Assign officer", width=140, height=36, font=fonts().body,
                fg_color=PALETTE.SURFACE_ALT, hover_color=PALETTE.SURFACE_HOVER,
                text_color=PALETTE.TEXT, command=self._assign_officer,
            ).grid(row=0, column=2)

    def _build_tabs(self) -> None:
        self.tabs = ctk.CTkTabview(self, fg_color=PALETTE.SURFACE,
                                   segmented_button_fg_color=PALETTE.SURFACE_ALT,
                                   segmented_button_selected_color=PALETTE.ACCENT,
                                   segmented_button_selected_hover_color=PALETTE.ACCENT_HOVER,
                                   segmented_button_unselected_color=PALETTE.SURFACE_ALT,
                                   segmented_button_unselected_hover_color=PALETTE.SURFACE_HOVER,
                                   text_color=PALETTE.TEXT,
                                   corner_radius=RADIUS)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=PAD_LG, pady=(0, PAD_LG))

        self.overview_tab = self.tabs.add("Overview")
        self.offences_tab = self.tabs.add("Offences")
        self.suspects_tab = self.tabs.add("Suspects")
        self.victims_tab = self.tabs.add("Victims")
        self.witnesses_tab = self.tabs.add("Witnesses")
        self.evidence_tab = self.tabs.add("Evidence")
        self.custody_tab = self.tabs.add("Custody")
        self.court_tab = self.tabs.add("Court")
        self.conviction_tab = self.tabs.add("Conviction")
        self.history_tab = self.tabs.add("History")

        self.case: dict = {}

    # ------------------------------------------------------------------
    def reload(self) -> None:
        case = self.repos.cases.get(self.case_id)
        if case is None:
            toast(self.app, "That case no longer exists.", "error")
            self.on_back()
            return
        self.case = case

        self.case_no_label.configure(text=case["case_no"])
        self.subtitle_label.configure(
            text=f"{case['station_name']}  |  Investigator {case['investigating_officer']}"
                 f"  |  Filed by {case['filed_by_name'] or case['filed_by']}"
        )
        self.status_pill.configure(
            text=status_label(case["status"]),
            fg_color=PALETTE.case_status.get(case["status"], PALETTE.ACCENT),
        )

        self._fill_overview()
        self._fill_offences()
        self._fill_suspects()
        self._fill_victims()
        self._fill_witnesses()
        self._fill_evidence()
        self._fill_custody()
        self._fill_court()
        self._fill_convictions()
        self._fill_history()

    def _table_host(self, tab, title: str, columns: list[Column],
                    *, on_add=None, add_text: str = "Add", height: int = 340):
        for child in tab.winfo_children():
            child.destroy()
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=PAD, pady=(PAD, PAD_SM))
        bar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            bar, text=title, font=fonts().heading, text_color=PALETTE.TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        if on_add is not None:
            ctk.CTkButton(
                bar, text=add_text, width=120, height=32, font=fonts().small,
                fg_color=PALETTE.ACCENT, hover_color=PALETTE.ACCENT_HOVER,
                text_color=PALETTE.ACCENT_TEXT, command=on_add,
            ).grid(row=0, column=1, sticky="e")

        table = DataTable(tab, columns, title="", searchable=True, height=height)
        table.grid(row=1, column=0, sticky="nsew", padx=(PAD, PAD), pady=(0, PAD))
        return table

    def _fill_overview(self) -> None:
        tab = self.overview_tab
        for child in tab.winfo_children():
            child.destroy()
        tab.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(tab, fg_color=PALETTE.SURFACE_ALT, corner_radius=RADIUS)
        card.grid(row=0, column=0, sticky="ew", padx=PAD, pady=PAD)
        card.grid_columnconfigure(1, weight=1)

        case = self.case
        rows = [
            ("Category", (case.get("category") or "-").replace("_", " ").title()),
            ("Offence type", case.get("offence_type") or "-"),
            ("Date of occurrence", str(case.get("occurrence_datetime") or "-")),
            ("Date of reporting", str(case.get("reporting_datetime") or "-")),
            ("Place of occurrence", case.get("place_of_occurrence") or "-"),
            ("Police station", f"{case['station_name']} ({case['district']})"),
            ("Investigating officer", f"{case['investigating_officer']} ({case['badge_no']})"),
            ("Filed by", case.get("filed_by_name") or case.get("filed_by") or "-"),
            ("Date closed", str(case.get("closed_datetime") or "-")),
            ("Days to close", str(case.get("days_to_close") or "-")),
        ]
        for index, (label, value) in enumerate(rows):
            ctk.CTkLabel(
                card, text=label, font=fonts().small, text_color=PALETTE.TEXT_MUTED, anchor="w",
            ).grid(row=index, column=0, sticky="w", padx=(PAD, PAD_SM), pady=4)
            ctk.CTkLabel(
                card, text=value, font=fonts().body, text_color=PALETTE.TEXT, anchor="w",
                wraplength=520, justify="left",
            ).grid(row=index, column=1, sticky="w", padx=(0, PAD), pady=4)

        description = ctk.CTkFrame(tab, fg_color=PALETTE.SURFACE_ALT, corner_radius=RADIUS)
        description.grid(row=1, column=0, sticky="ew", padx=PAD, pady=(0, PAD))
        description.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            description, text="Description of the incident", font=fonts().small,
            text_color=PALETTE.TEXT_MUTED, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=PAD, pady=(PAD, 4))
        ctk.CTkLabel(
            description, text=case.get("description") or "No description recorded.",
            font=fonts().body, text_color=PALETTE.TEXT, anchor="w", justify="left",
            wraplength=900,
        ).grid(row=1, column=0, sticky="w", padx=PAD, pady=(0, PAD))

    def _fill_offences(self) -> None:
        table = self._table_host(
            self.offences_tab, "Offence sections charged",
            [
                Column("law_code", "Law", 70, anchor="center"),
                Column("section_no", "Section", 90, anchor="center"),
                Column("offence_name", "Offence", 300),
                Column("category", "Type", 140),
                Column("severity", "Severity", 100),
                Column("accused_role", "Role", 110),
            ],
        )
        table.set_rows(self.repos.cases.offences(self.case_id))

    def _fill_suspects(self) -> None:
        table = self._table_host(
            self.suspects_tab, "Suspects",
            [
                Column("name", "Name", 180),
                Column("alias", "Alias", 120),
                Column("gender", "Gender", 90),
                Column("status", "Status", 140),
                Column("arrest_count", "Arrests", 80, anchor="center"),
                Column("conviction_count", "Convictions", 100, anchor="center"),
            ],
        )
        table.set_rows(self.repos.suspects.for_case(self.case_id))

    def _fill_victims(self) -> None:
        table = self._table_host(
            self.victims_tab, "Victims",
            [
                Column("name", "Name", 180),
                Column("age", "Age", 70, anchor="center"),
                Column("gender", "Gender", 90),
                Column("injury_level", "Injury", 130),
                Column("phone", "Phone", 130),
            ],
        )
        table.set_rows(self.repos.victims.for_case(self.case_id))

    def _fill_witnesses(self) -> None:
        table = self._table_host(
            self.witnesses_tab, "Witnesses",
            [
                Column("name", "Name", 180),
                Column("phone", "Phone", 130),
                Column("is_reliable", "Reliable", 90, anchor="center",
                       render=lambda row: "Yes" if row.get("is_reliable") else "No"),
                Column("statement", "Statement", 420),
            ],
        )
        table.set_rows(self.repos.witnesses.for_case(self.case_id))

    def _fill_evidence(self) -> None:
        table = self._table_host(
            self.evidence_tab, "Evidence register",
            [
                Column("type", "Type", 120),
                Column("description", "Description", 300),
                Column("collected_by_name", "Collected by", 160),
                Column("collected_datetime", "Collected", 150),
                Column("chain_of_custody_datetime", "Chain of custody", 150),
                Column("storage_location", "Storage", 140),
            ],
        )
        table.set_rows(self.repos.evidence.for_case(self.case_id))

    def _fill_custody(self) -> None:
        table = self._table_host(
            self.custody_tab, "Arrests and custody",
            [
                Column("suspect_name", "Suspect", 180),
                Column("arrest_datetime", "Arrested on", 150),
                Column("place_of_arrest", "Place", 160),
                Column("remand_status", "Remand", 160),
                Column("bail_amount", "Bail", 110, anchor="e"),
                Column("arrested_by_name", "Arrested by", 160),
            ],
        )
        table.set_rows(self.repos.arrests.for_case(self.case_id))

    def _fill_court(self) -> None:
        table = self._table_host(
            self.court_tab, "Court proceedings",
            [
                Column("court_name", "Court", 200),
                Column("hearing_datetime", "Hearing", 150),
                Column("stage", "Stage", 140),
                Column("judge_name", "Judge", 150),
                Column("next_hearing_datetime", "Next hearing", 150),
            ],
        )
        table.set_rows(self.repos.proceedings.for_case(self.case_id))

    def _fill_convictions(self) -> None:
        table = self._table_host(
            self.conviction_tab, "Convictions",
            [
                Column("suspect_name", "Suspect", 180),
                Column("court_name", "Court", 200),
                Column("verdict", "Verdict", 130),
                Column("sentence_type", "Sentence", 150),
                Column("imprisonment_years", "Years", 80, anchor="center"),
                Column("fine_amount", "Fine", 110, anchor="e"),
                Column("release_expected", "Release expected", 140),
            ],
        )
        table.set_rows(self.repos.convictions.for_case(self.case_id))

    def _fill_history(self) -> None:
        table = self._table_host(
            self.history_tab, "Status history",
            [
                Column("changed_at", "When", 160),
                Column("old_status", "From", 150,
                       render=lambda row: status_label(row.get("old_status") or "Created")),
                Column("new_status", "To", 150,
                       render=lambda row: status_label(row.get("new_status") or "-")),
                Column("changed_by_name", "Changed by", 180,
                       render=lambda row: row.get("changed_by_name") or row.get("changed_by")),
                Column("remark", "Remark", 300),
            ],
        )
        table.set_rows(self.repos.cases.history(self.case_id))

    # ------------------------------------------------------------------
    def _change_status(self) -> None:
        dialog = ChangeStatusDialog(self.app, self.repos, self.user, self.case)
        result = dialog.show()
        if result:
            self.app.toast("Case status updated", "success")
            self.reload()

    def _assign_officer(self) -> None:
        officers = self.repos.officers.options(self.case["station_id"])
        if not officers:
            self.app.toast("No active officers at that station.", "warning")
            return
        from app.ui.dialogs import ChoiceDialog
        options = [(row["officer_id"],
                    f"{row['name']} - {row['rank']} ({row['badge_no']})") for row in officers]
        dialog = ChoiceDialog(self.app, "Assign investigating officer", options,
                              subtitle="Only officers posted at this station are listed.")
        choice = dialog.show()
        if choice is None:
            return
        try:
            self.repos.cases.assign_officer(self.case_id, choice, self.user["user_id"])
        except DatabaseError as exc:
            self.app.toast(str(exc), "error", 6000)
            return
        self.app.toast("Officer assigned", "success")
        self.reload()


class RepositoriesProxy:
    """Small helper so the detail view reaches the repositories."""

    def __init__(self, db) -> None:
        from app.db.repositories import Repositories
        self._repos = Repositories(db)

    def __getattr__(self, item):
        return getattr(self._repos, item)
