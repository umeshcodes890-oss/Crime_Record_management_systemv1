"""The main application window: sidebar navigation, header and content area."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import customtkinter as ctk

from app.db.auth import ROLE_ADMIN
from app.db.connection import Database, DatabaseError
from app.ui.theme import PAD, PAD_LG, PAD_SM, RADIUS, RADIUS_SM, fonts
from app.ui.widgets import PALETTE, set_mode, toast


@dataclass
class NavItem:
    key: str
    label: str
    title: str
    subtitle: str
    roles: tuple[str, ...]
    factory: Callable[["AppWindow", "AppWindow"], ctk.CTkFrame]
    group: str = "Operations"


class AppWindow(ctk.CTkFrame):
    """Shell that hosts the sidebar, the header and the active view."""

    def __init__(self, master, db: Database, user: dict, on_logout) -> None:
        super().__init__(master, fg_color=PALETTE.BG)
        self.db = db
        self.user = user
        self.on_logout = on_logout
        self._view: ctk.CTkFrame | None = None
        self._view_key: str | None = None
        self._nav_buttons: dict[str, ctk.CTkButton] = {}

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._build_sidebar()
        self._build_header()
        self._build_content()

        self.navigate(self._first_allowed_key())

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_sidebar(self) -> None:
        self.sidebar = ctk.CTkFrame(self, fg_color=PALETTE.SURFACE, corner_radius=0, width=236)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(2, weight=1)
        self.sidebar.grid_columnconfigure(0, weight=1)

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=PAD_LG, pady=(PAD_LG, PAD))
        ctk.CTkLabel(
            brand, text="CRIME RECORD", font=fonts().label, text_color=PALETTE.ACCENT,
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand, text="Management System", font=fonts().subtitle, text_color=PALETTE.TEXT,
        ).pack(anchor="w")

        self.nav = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.nav.grid(row=1, column=0, sticky="new", padx=PAD_SM)

        self.user_panel = ctk.CTkFrame(self.sidebar, fg_color=PALETTE.SURFACE_ALT,
                                       corner_radius=RADIUS)
        self.user_panel.grid(row=3, column=0, sticky="ew", padx=PAD, pady=PAD)
        self.user_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.user_panel, text=self.user.get("full_name") or self.user["username"],
            font=fonts().body_bold, text_color=PALETTE.TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=PAD, pady=(PAD, 0))
        ctk.CTkLabel(
            self.user_panel, text=self.user["role"].replace("_", " ").title(),
            font=fonts().small, text_color=PALETTE.ACCENT, anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=PAD)

        ctk.CTkButton(
            self.user_panel, text="Sign out", height=32, font=fonts().small,
            fg_color="transparent", border_width=1, border_color=PALETTE.BORDER,
            text_color=PALETTE.TEXT_MUTED, hover_color=PALETTE.SURFACE_HOVER,
            command=self.on_logout,
        ).grid(row=2, column=0, sticky="ew", padx=PAD, pady=(PAD_SM, PAD))

    def _build_header(self) -> None:
        self.header = ctk.CTkFrame(self, fg_color=PALETTE.BG, corner_radius=0)
        self.header.grid(row=0, column=1, sticky="ew")
        self.header.grid_columnconfigure(0, weight=1)

        titles = ctk.CTkFrame(self.header, fg_color="transparent")
        titles.grid(row=0, column=0, sticky="w", padx=PAD_LG, pady=(PAD_LG, PAD_SM))

        self.page_title = ctk.CTkLabel(
            titles, text="", font=fonts().display, text_color=PALETTE.TEXT, anchor="w",
        )
        self.page_title.pack(anchor="w")
        self.page_subtitle = ctk.CTkLabel(
            titles, text="", font=fonts().small, text_color=PALETTE.TEXT_MUTED, anchor="w",
        )
        self.page_subtitle.pack(anchor="w")

        actions = ctk.CTkFrame(self.header, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e", padx=PAD_LG)

        self.theme_button = ctk.CTkButton(
            actions, text="Light mode", width=110, height=36, font=fonts().small,
            fg_color=PALETTE.SURFACE, hover_color=PALETTE.SURFACE_HOVER,
            text_color=PALETTE.TEXT, command=self._toggle_theme,
        )
        self.theme_button.pack(side="left", padx=(0, PAD_SM))

        ctk.CTkButton(
            actions, text="Refresh", width=100, height=36, font=fonts().small,
            fg_color=PALETTE.ACCENT, hover_color=PALETTE.ACCENT_HOVER,
            text_color=PALETTE.ACCENT_TEXT, command=self._refresh,
        ).pack(side="left")

    def _build_content(self) -> None:
        self.content = ctk.CTkFrame(self, fg_color=PALETTE.BG, corner_radius=0)
        self.content.grid(row=1, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # navigation
    # ------------------------------------------------------------------
    def nav_items(self) -> list[NavItem]:
        from app.ui.views import dashboard, cases, court, evidence, masters, persons, users

        return [
            NavItem("dashboard", "Dashboard", "Dashboard",
                    "Caseload, trends and clearance at a glance",
                    ("admin", "officer", "viewer"), dashboard.DashboardView),
            NavItem("cases", "Cases", "Crime Cases",
                    "Every registered case and its investigation trail",
                    ("admin", "officer", "viewer"), cases.CasesView),
            NavItem("suspects", "Suspects", "Suspects",
                    "People named in cases and where they stand",
                    ("admin", "officer", "viewer"), persons.SuspectsView),
            NavItem("victims", "Victims", "Victims",
                    "Victim register across all cases",
                    ("admin", "officer", "viewer"), persons.VictimsView),
            NavItem("witnesses", "Witnesses", "Witnesses",
                    "Witness statements and reliability",
                    ("admin", "officer", "viewer"), persons.WitnessesView),
            NavItem("evidence", "Evidence", "Evidence",
                    "Evidence register and chain of custody",
                    ("admin", "officer", "viewer"), evidence.EvidenceView),
            NavItem("court", "Court", "Court & Custody",
                    "Hearings, arrests and convictions",
                    ("admin", "officer", "viewer"), court.CourtView),
            NavItem("stations", "Stations", "Police Stations",
                    "Stations, their districts and their caseload",
                    (ROLE_ADMIN,), masters.StationsView, group="Administration"),
            NavItem("officers", "Officers", "Officers",
                    "Officer strength and workload",
                    (ROLE_ADMIN,), masters.OfficersView, group="Administration"),
            NavItem("offences", "Law Library", "Offence Sections",
                    "The BNS and IPC sections your cases can be charged under",
                    (ROLE_ADMIN,), masters.OffencesView, group="Administration"),
            NavItem("users", "Users", "User Accounts",
                    "Logins, roles and password resets",
                    (ROLE_ADMIN,), users.UsersView, group="Administration"),
        ]

    def _allowed_items(self) -> list[NavItem]:
        role = self.user.get("role")
        return [item for item in self.nav_items() if role in item.roles]

    def _first_allowed_key(self) -> str:
        return self._allowed_items()[0].key

    def _populate_nav(self) -> None:
        for child in self.nav.winfo_children():
            child.destroy()

        group = None
        for item in self._allowed_items():
            if item.group != group:
                group = item.group
                ctk.CTkLabel(
                    self.nav, text=group.upper(), font=fonts().small,
                    text_color=PALETTE.TEXT_DIM, anchor="w",
                ).grid(row=self.nav.grid_size()[1], column=0, sticky="w",
                       padx=PAD, pady=(PAD, PAD_SM))

            button = ctk.CTkButton(
                self.nav, text=item.label, height=38, font=fonts().body,
                fg_color="transparent", hover_color=PALETTE.SURFACE_HOVER,
                text_color=PALETTE.TEXT_MUTED, anchor="w", corner_radius=RADIUS_SM,
                command=lambda key=item.key: self.navigate(key),
            )
            button.grid(row=self.nav.grid_size()[1], column=0, sticky="ew",
                        padx=PAD_SM, pady=1)
            self._nav_buttons[item.key] = button

        # The sidebar needs its own stretch so the nav sits at the top.
        self.nav.grid_rowconfigure(0, weight=0)

    def navigate(self, key: str, **kwargs) -> None:
        items = {item.key: item for item in self._allowed_items()}
        item = items.get(key)
        if item is None:
            return

        if not self._nav_buttons:
            self._populate_nav()

        for nav_key, button in self._nav_buttons.items():
            active = nav_key == key
            button.configure(
                fg_color=PALETTE.ACCENT_SOFT if active else "transparent",
                text_color=PALETTE.ACCENT if active else PALETTE.TEXT_MUTED,
            )

        if self._view is not None:
            self._view.destroy()
            self._view = None

        self.page_title.configure(text=item.title)
        self.page_subtitle.configure(text=item.subtitle)

        view = item.factory(self.content, self)
        if kwargs:
            setter = getattr(view, "open_detail", None)
            if setter:
                setter(**kwargs)
        view.grid(row=0, column=0, sticky="nsew")
        self._view = view
        self._view_key = key

    def _refresh(self) -> None:
        if self._view is not None and hasattr(self._view, "refresh"):
            try:
                self._view.refresh()
                toast(self, "Refreshed", "success", 1600)
            except DatabaseError as exc:
                toast(self, str(exc), "error", 5000)

    def _toggle_theme(self) -> None:
        mode = "light" if PALETTE.mode == "dark" else "dark"
        ctk.set_appearance_mode(mode)
        set_mode(mode)
        toast(self, f"Switched to {mode} mode", "info", 1600)
        self._rebuild(mode)

    def _rebuild(self, mode: str) -> None:
        """Rebuild the shell so every widget picks up the new palette."""
        current = self._view_key or self._first_allowed_key()
        for child in self.winfo_children():
            child.destroy()
        self._nav_buttons.clear()
        self._view = None
        self._view_key = None
        self.theme_button = None

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self._build_sidebar()
        self._build_header()
        self._build_content()
        self.theme_button.configure(
            text="Light mode" if mode == "dark" else "Dark mode"
        )
        self.navigate(current)

    # ------------------------------------------------------------------
    # helpers for views
    # ------------------------------------------------------------------
    def can(self, *roles: str) -> bool:
        return self.user.get("role") in roles

    def toast(self, message: str, kind: str = "info", duration: int = 3600) -> None:
        toast(self, message, kind, duration)
