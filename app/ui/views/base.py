"""Shared behaviour for every screen."""

from __future__ import annotations

from typing import Any, Callable

import customtkinter as ctk

from app.db.connection import DatabaseError
from app.db.repositories import Repositories
from app.ui.theme import fonts
from app.ui.widgets import PALETTE, confirm


class BaseView(ctk.CTkFrame):
    """Base class for the screens shown in the content area."""

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=PALETTE.BG)
        self.app = app
        self.db = app.db
        self.user = app.user
        self._repos: Repositories | None = None

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

    @property
    def repos(self) -> Repositories:
        if self._repos is None:
            self._repos = Repositories(self.db, self.user)
        return self._repos

    # -- helpers ------------------------------------------------------
    def can_write(self) -> bool:
        return self.user.get("role") in ("admin", "officer")

    def is_admin(self) -> bool:
        return self.user.get("role") == "admin"

    def refresh(self) -> None:
        """Reload the data shown on screen."""

    def guard(self, func: Callable, *args, success: str | None = None, **kwargs) -> Any:
        """Run a repository call, turning database errors into a toast."""
        try:
            result = func(*args, **kwargs)
        except DatabaseError as exc:
            self.app.toast(str(exc), "error", 6500)
            return None
        if success:
            self.app.toast(success, "success")
        return result

    def delete_record(self, subject: str, action: Callable[[], None]) -> bool:
        """Ask for confirmation, then run a delete and report the outcome."""
        if not confirm(self.app, "Delete record",
                       f"{subject}\n\nThis cannot be undone.", "Delete", danger=True):
            return False
        try:
            action()
        except DatabaseError as exc:
            self.app.toast(str(exc), "error", 6500)
            return False
        self.app.toast("Record deleted", "success")
        return True

    def toolbar(self, parent, title: str = "", subtitle: str = "") -> ctk.CTkFrame:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        if title:
            ctk.CTkLabel(
                bar, text=title, font=fonts().subtitle, text_color=PALETTE.TEXT, anchor="w",
            ).pack(side="left")
        if subtitle:
            ctk.CTkLabel(
                bar, text=subtitle, font=fonts().small, text_color=PALETTE.TEXT_MUTED,
                anchor="w",
            ).pack(side="left", padx=(PAD_GAP, 0))
        return bar

    def section(self, parent, title: str = "") -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        if title:
            ctk.CTkLabel(
                frame, text=title, font=fonts().heading, text_color=PALETTE.TEXT, anchor="w",
            ).pack(anchor="w", pady=(0, 8))
        return frame


PAD_GAP = 12
