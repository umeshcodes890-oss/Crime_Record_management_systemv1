"""Administration screens: stations, officers and the law library."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from app.ui.dialogs import FormDialog
from app.ui.theme import PAD, PAD_LG, RADIUS, fonts
from app.ui.views.base import BaseView
from app.ui.widgets import PALETTE, Column, DataTable, FormPanel, confirm

RANKS = ["Constable", "Sub-Inspector", "Inspector", "Deputy Superintendent of Police",
         "Superintendent of Police", "Additional Superintendent of Police"]
SEVERITIES = ["low", "medium", "high", "grave"]
LAW_CODES = ["BNS", "IPC"]
CATEGORIES = ["cognizable", "non_cognizable"]


class StationDialog(FormDialog):
    def __init__(self, master, repos, station: dict | None = None) -> None:
        self.repos = repos
        self.station = station
        super().__init__(master, "Edit police station" if station else "Add police station",
                         size=(620, 480))

    def build(self, form: FormPanel) -> None:
        form.add_entry("name", "Station name", required=True)
        form.add_entry("district", "District", required=True)
        form.add_entry("address", "Address")
        form.add_entry("phone", "Phone")
        officers = self.repos.officers.options()
        form.add_choice("incharge", "In-charge officer",
                        ["None"] + [f"{row['name']} - {row['rank']}" for row in officers])
        if self.station:
            form.set("name", self.station.get("name"))
            form.set("district", self.station.get("district"))
            form.set("address", self.station.get("address"))
            form.set("phone", self.station.get("phone"))

    def on_save(self, values: dict[str, Any]) -> None:
        officers = self.repos.officers.options()
        incharge_id = None
        label = values.get("incharge", "None")
        if label != "None":
            incharge = next((row for row in officers if label.startswith(row["name"])), None)
            incharge_id = incharge["officer_id"] if incharge else None

        if self.station:
            self.repos.stations.update(
                self.station["station_id"], values["name"], values["district"],
                values.get("address") or None, values.get("phone") or None, incharge_id,
            )
        else:
            self.repos.stations.create(
                values["name"], values["district"], values.get("address") or None,
                values.get("phone") or None, incharge_id,
            )


class OfficerDialog(FormDialog):
    def __init__(self, master, repos, officer: dict | None = None) -> None:
        self.repos = repos
        self.officer = officer
        super().__init__(master, "Edit officer" if officer else "Add officer",
                         size=(620, 520))

    def build(self, form: FormPanel) -> None:
        stations = self.repos.stations.options()
        form.add_entry("badge", "Badge number", required=True)
        form.add_entry("name", "Full name", required=True)
        form.add_choice("rank", "Rank", RANKS, required=True)
        form.add_choice("station", "Station",
                        [row["name"] for row in stations], required=True)
        form.add_entry("phone", "Phone")
        form.add_date("joined", "Date of joining")
        if self.officer:
            form.set("badge", self.officer.get("badge_no"))
            form.set("name", self.officer.get("name"))
            form.set("rank", self.officer.get("rank"))
            form.set("phone", self.officer.get("phone"))

    def on_save(self, values: dict[str, Any]) -> None:
        stations = self.repos.stations.options()
        station = next((row for row in stations if row["name"] == values["station"]), None)
        if station is None:
            raise ValueError("Choose the station this officer is posted at.")

        if self.officer:
            self.repos.officers.update(
                self.officer["officer_id"], values["badge"], values["name"], values["rank"],
                station["station_id"], values.get("phone") or None,
                values.get("joined") or None, True,
            )
        else:
            self.repos.officers.create(
                values["badge"], values["name"], values["rank"], station["station_id"],
                values.get("phone") or None, values.get("joined") or None,
            )


class OffenceDialog(FormDialog):
    def __init__(self, master, repos, section: dict | None = None) -> None:
        self.repos = repos
        self.section = section
        super().__init__(master, "Edit offence section" if section else "Add offence section",
                         size=(660, 620))

    def build(self, form: FormPanel) -> None:
        form.add_choice("law", "Law", LAW_CODES, required=True)
        form.add_entry("number", "Section number", placeholder="e.g. 420", required=True)
        form.add_entry("name", "Offence name", required=True)
        form.add_choice("category", "Category", CATEGORIES, required=True)
        form.add_choice("severity", "Severity", SEVERITIES, required=True)
        form.add_entry("min", "Minimum imprisonment (years)")
        form.add_entry("max", "Maximum imprisonment (years)")
        form.add_entry("fine", "Fine cap")
        form.add_text("description", "Description", height=90)
        if self.section:
            form.set("law", self.section.get("law_code"))
            form.set("number", self.section.get("section_no"))
            form.set("name", self.section.get("offence_name"))
            form.set("category", self.section.get("category"))
            form.set("severity", self.section.get("severity"))
            form.set("min", self.section.get("min_imprisonment_yrs"))
            form.set("max", self.section.get("max_imprisonment_yrs"))
            form.set("fine", self.section.get("fine_cap"))

    def on_save(self, values: dict[str, Any]) -> None:
        def number(key: str) -> float | None:
            raw = (values.get(key) or "").strip()
            return float(raw) if raw.replace(".", "", 1).isdigit() else None

        if self.section:
            self.repos.offences.update(
                self.section["section_id"], values["law"], values["number"], values["name"],
                values["category"], values["severity"], number("min"), number("max"),
                number("fine"), values.get("description") or None,
            )
        else:
            self.repos.offences.create(
                values["law"], values["number"], values["name"], values["category"],
                values["severity"], number("min"), number("max"), number("fine"),
                values.get("description") or None,
            )


class _MasterView(BaseView):
    """Shared CRUD list for the administration screens."""

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(self, fg_color=PALETTE.SURFACE, corner_radius=RADIUS)
        bar.grid(row=0, column=0, sticky="ew", padx=PAD_LG, pady=(PAD_LG, PAD))
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            bar, text=self.heading, font=fonts().subtitle, text_color=PALETTE.TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(PAD, PAD_SM))

        ctk.CTkButton(
            bar, text=self.add_text, width=150, height=36, font=fonts().body_bold,
            fg_color=PALETTE.ACCENT, hover_color=PALETTE.ACCENT_HOVER,
            text_color=PALETTE.ACCENT_TEXT, command=self._add,
        ).grid(row=0, column=1, sticky="e", padx=(0, PAD), pady=PAD)

        self.table = DataTable(
            self, self.columns(), title=self.table_title,
            empty_text=self.empty_text, on_row_double=self._edit,
        )
        self.table.grid(row=1, column=0, sticky="nsew", padx=PAD_LG, pady=(0, PAD_LG))

    def columns(self) -> list[Column]:
        raise NotImplementedError

    def load(self) -> list[dict]:
        raise NotImplementedError

    def refresh(self) -> None:
        self.table.set_rows(self.guard(self.load) or [])

    def _add(self) -> None:
        raise NotImplementedError

    def _edit(self, row: dict) -> None:
        raise NotImplementedError


class StationsView(_MasterView):
    heading = "Police stations"
    table_title = "Stations"
    add_text = "Add station"
    empty_text = "No police stations yet."

    def columns(self) -> list[Column]:
        return [
            Column("name", "Station", 220),
            Column("district", "District", 140),
            Column("address", "Address", 260),
            Column("phone", "Phone", 140),
            Column("incharge_name", "In-charge", 180),
            Column("case_count", "Cases", 90, anchor="center"),
        ]

    def load(self) -> list[dict]:
        return self.repos.stations.list_all()

    def _add(self) -> None:
        dialog = StationDialog(self.app, self.repos)
        if dialog.show():
            self.app.toast("Station added", "success")
            self.refresh()

    def _edit(self, row: dict) -> None:
        dialog = StationDialog(self.app, self.repos, row)
        if dialog.show():
            self.app.toast("Station updated", "success")
            self.refresh()


class OfficersView(_MasterView):
    heading = "Officers"
    table_title = "Officer strength and workload"
    add_text = "Add officer"
    empty_text = "No officers yet."

    def columns(self) -> list[Column]:
        return [
            Column("badge_no", "Badge", 110),
            Column("name", "Name", 200),
            Column("rank", "Rank", 200),
            Column("station_name", "Station", 180),
            Column("total_cases", "Cases", 90, anchor="center"),
            Column("open_cases", "Open", 90, anchor="center"),
            Column("avg_days_to_close", "Avg days", 110, anchor="center"),
        ]

    def load(self) -> list[dict]:
        return self.repos.officers.list_all()

    def _add(self) -> None:
        dialog = OfficerDialog(self.app, self.repos)
        if dialog.show():
            self.app.toast("Officer added", "success")
            self.refresh()

    def _edit(self, row: dict) -> None:
        officer = self.repos.officers.get(row["officer_id"])
        dialog = OfficerDialog(self.app, self.repos, officer)
        if dialog.show():
            self.app.toast("Officer updated", "success")
            self.refresh()


class OffencesView(_MasterView):
    heading = "Law library"
    table_title = "Offence sections"
    add_text = "Add section"
    empty_text = "No offence sections yet."

    def columns(self) -> list[Column]:
        return [
            Column("law_code", "Law", 70, anchor="center"),
            Column("section_no", "Section", 90, anchor="center"),
            Column("offence_name", "Offence", 340),
            Column("category", "Type", 150),
            Column("severity", "Severity", 110),
            Column("max_imprisonment_yrs", "Max yrs", 90, anchor="center"),
        ]

    def load(self) -> list[dict]:
        return self.repos.offences.list_all()

    def _add(self) -> None:
        dialog = OffenceDialog(self.app, self.repos)
        if dialog.show():
            self.app.toast("Offence section added", "success")
            self.refresh()

    def _edit(self, row: dict) -> None:
        section = self.repos.offences.get(row["section_id"])
        dialog = OffenceDialog(self.app, self.repos, section)
        if dialog.show():
            self.app.toast("Offence section updated", "success")
            self.refresh()
