"""Dashboard: headline numbers, charts and what needs attention today."""

from __future__ import annotations

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from app.ui.charts import bar_chart, donut_chart, horizontal_bar_chart, line_chart
from app.ui.theme import PAD, PAD_LG, PAD_SM, RADIUS, fonts
from app.ui.views.base import BaseView
from app.ui.widgets import PALETTE, Column, DataTable, StatCard


class DashboardView(BaseView):
    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.canvas = ctk.CTkScrollableFrame(self, fg_color=PALETTE.BG)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.grid_columnconfigure(0, weight=1)

        self._build_stats()
        self._build_charts()
        self._build_tables()
        self.refresh()

    # ------------------------------------------------------------------
    def _build_stats(self) -> None:
        row = ctk.CTkFrame(self.canvas, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew", padx=PAD_LG, pady=(PAD_LG, PAD))
        for index in range(5):
            row.grid_columnconfigure(index, weight=1)

        self.cards: dict[str, StatCard] = {}
        specs = [
            ("total", "Total cases", PALETTE.ACCENT),
            ("open", "Open cases", PALETTE.WARNING),
            ("convicted", "Convicted", PALETTE.SUCCESS),
            ("clearance", "Clearance rate", PALETTE.INFO),
            ("disposal", "Avg days to close", PALETTE.VIOLET),
        ]
        for index, (key, title, accent) in enumerate(specs):
            card = StatCard(row, title, "-", accent=accent)
            card.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else PAD_SM, 0))
            self.cards[key] = card

    def _build_charts(self) -> None:
        row = ctk.CTkFrame(self.canvas, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=PAD_LG, pady=(0, PAD))
        row.grid_columnconfigure(0, weight=1)
        row.grid_columnconfigure(1, weight=1)

        self.chart_monthly = self._chart_holder(row, 0, 0, "Monthly caseload")
        self.chart_status = self._chart_holder(row, 0, 1, "Cases by status")

        row2 = ctk.CTkFrame(self.canvas, fg_color="transparent")
        row2.grid(row=2, column=0, sticky="ew", padx=PAD_LG, pady=(0, PAD))
        row2.grid_columnconfigure(0, weight=1)
        row2.grid_columnconfigure(1, weight=1)

        self.chart_offences = self._chart_holder(row2, 0, 0, "Most charged sections")
        self.chart_stations = self._chart_holder(row2, 0, 1, "Caseload by station")

    def _chart_holder(self, parent, row: int, column: int, title: str) -> ctk.CTkFrame:
        holder = ctk.CTkFrame(parent, fg_color=PALETTE.SURFACE, corner_radius=RADIUS)
        holder.grid(row=row, column=column, sticky="nsew", padx=(0, PAD_SM))
        holder.grid_columnconfigure(0, weight=1)
        holder.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            holder, text=title, font=fonts().heading, text_color=PALETTE.TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=PAD_LG, pady=(PAD_LG, 0))

        area = ctk.CTkFrame(holder, fg_color="transparent")
        area.grid(row=1, column=0, sticky="nsew", padx=PAD_SM, pady=(0, PAD_SM))
        return area

    def _build_tables(self) -> None:
        row = ctk.CTkFrame(self.canvas, fg_color="transparent")
        row.grid(row=3, column=0, sticky="ew", padx=PAD_LG, pady=(0, PAD_LG))
        row.grid_columnconfigure(0, weight=3)
        row.grid_columnconfigure(1, weight=2)

        recent = ctk.CTkFrame(row, fg_color=PALETTE.SURFACE, corner_radius=RADIUS)
        recent.grid(row=0, column=0, sticky="nsew", padx=(0, PAD_SM))
        recent.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            recent, text="Recently registered cases", font=fonts().heading,
            text_color=PALETTE.TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=PAD_LG, pady=(PAD_LG, PAD))
        self.recent_table = DataTable(
            recent,
            [
                Column("case_no", "Case No", 110),
                Column("category", "Category", 120),
                Column("station_name", "Station", 140),
                Column("status", "Status", 150),
            ],
            title="", searchable=False, height=200,
            on_row_double=lambda row: self.app.navigate("cases", case_id=row["case_id"]),
        )
        self.recent_table.grid(row=1, column=0, sticky="nsew", padx=(PAD_SM, PAD_SM), pady=(0, PAD))

        hearings = ctk.CTkFrame(row, fg_color=PALETTE.SURFACE, corner_radius=RADIUS)
        hearings.grid(row=0, column=1, sticky="nsew")
        hearings.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            hearings, text="Next hearings", font=fonts().heading,
            text_color=PALETTE.TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=PAD_LG, pady=(PAD_LG, PAD))
        self.hearings_table = DataTable(
            hearings,
            [
                Column("case_no", "Case", 110),
                Column("court_name", "Court", 160),
                Column("next_hearing_datetime", "Next hearing", 150),
            ],
            title="", searchable=False, height=200,
        )
        self.hearings_table.grid(row=1, column=0, sticky="nsew", padx=(PAD_SM, PAD_SM), pady=(0, PAD))

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        summary = self.guard(self.repos.reports.summary)
        if summary is None:
            return

        self.cards["total"].set_value(summary.get("total_cases", 0),
                                      f"{summary.get('cases_last_30_days', 0)} in the last 30 days")
        self.cards["open"].set_value(summary.get("open_cases", 0),
                                     "Still under investigation")
        self.cards["convicted"].set_value(summary.get("convicted_cases", 0),
                                          f"{summary.get('custody_suspects', 0)} suspects in custody")
        clearance = summary.get("clearance_rate")
        self.cards["clearance"].set_value(
            f"{clearance}%" if clearance is not None else "-",
            "Convicted share of closed cases",
        )
        disposal = summary.get("avg_days_to_close")
        self.cards["disposal"].set_value(
            disposal if disposal is not None else "-", "Average time to close a case"
        )

        self._draw_charts()
        self.recent_table.set_rows(self.guard(self.repos.cases.recent) or [])
        self.hearings_table.set_rows(self.guard(self.repos.reports.upcoming_hearings) or [])

    def _draw_charts(self) -> None:
        monthly = list(reversed(self.guard(self.repos.reports.monthly) or []))
        labels = [row["month"] for row in monthly]
        series = {
            "Registered": [row["cases_registered"] for row in monthly],
            "Closed": [row["cases_closed"] for row in monthly],
        }
        self._embed(self.chart_monthly,
                    line_chart(labels, series, "Monthly caseload") if labels
                    else bar_chart([], [], "Monthly caseload"))

        status_rows = self.guard(self.repos.reports.by_status) or []
        status_labels = [row["status"].replace("_", " ").title() for row in status_rows]
        status_values = [row["total"] for row in status_rows]
        status_colors = [PALETTE.case_status.get(row["status"], PALETTE.ACCENT)
                         for row in status_rows]
        self._embed(self.chart_status,
                    donut_chart(status_labels, status_values, "Cases by status", status_colors))

        offences = self.guard(self.repos.reports.top_offences) or []
        offence_labels = [f"{row['law_code']} {row['section_no']}" for row in offences]
        offence_values = [row["case_count"] for row in offences]
        offence_colors = [PALETTE.severity.get(row["severity"], PALETTE.ACCENT)
                          for row in offences]
        self._embed(self.chart_offences,
                    horizontal_bar_chart(offence_labels, offence_values,
                                         "Most charged sections", offence_colors))

        stations = self.guard(self.repos.reports.by_station) or []
        station_labels = [row["station_name"] for row in stations][:8]
        station_values = [row["total_cases"] for row in stations][:8]
        self._embed(self.chart_stations,
                    horizontal_bar_chart(station_labels, station_values,
                                         "Caseload by station"))

    def _embed(self, holder: ctk.CTkFrame, figure) -> None:
        for child in holder.winfo_children():
            child.destroy()
        canvas = FigureCanvasTkAgg(figure, master=holder)
        canvas.draw()
        widget = canvas.get_tk_widget()
        widget.configure(highlightthickness=0, bd=0)
        widget.pack(fill="both", expand=True)
