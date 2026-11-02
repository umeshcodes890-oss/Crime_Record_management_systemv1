"""Sign-in screen."""

from __future__ import annotations

import customtkinter as ctk

from app.db.auth import UserRepository
from app.db.connection import Database, DatabaseError
from app.ui.theme import PAD, PAD_LG, PAD_SM, PAD_XL, fonts
from app.ui.widgets import PALETTE


class LoginScreen(ctk.CTkFrame):
    """Username and password entry, shown before the main window."""

    def __init__(self, master, db: Database, on_success) -> None:
        super().__init__(master, fg_color=PALETTE.BG)
        self.db = db
        self.on_success = on_success
        self.users = UserRepository(db)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.card = ctk.CTkFrame(self, fg_color=PALETTE.SURFACE, corner_radius=16)
        self.card.grid(row=0, column=0)
        self.card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.card, text="Crime Record", font=fonts().display,
            text_color=PALETTE.TEXT,
        ).grid(row=0, column=0, padx=PAD_XL, pady=(PAD_XL, 0))
        ctk.CTkLabel(
            self.card, text="Management System", font=fonts().title,
            text_color=PALETTE.ACCENT,
        ).grid(row=1, column=0, padx=PAD_XL, pady=(0, PAD))
        ctk.CTkLabel(
            self.card, text="Sign in with your department account",
            font=fonts().small, text_color=PALETTE.TEXT_MUTED,
        ).grid(row=2, column=0, padx=PAD_XL, pady=(0, PAD_LG))

        self.username = ctk.CTkEntry(
            self.card, height=40, width=356, placeholder_text="Username",
            font=fonts().body, fg_color=PALETTE.SURFACE_ALT,
            border_color=PALETTE.BORDER, border_width=1,
        )
        self.username.grid(row=3, column=0, padx=PAD_XL, sticky="ew", pady=(0, PAD))

        self.password = ctk.CTkEntry(
            self.card, height=40, width=356, placeholder_text="Password", show="*",
            font=fonts().body, fg_color=PALETTE.SURFACE_ALT,
            border_color=PALETTE.BORDER, border_width=1,
        )
        self.password.grid(row=4, column=0, padx=PAD_XL, sticky="ew", pady=(0, PAD))

        self.error = ctk.CTkLabel(
            self.card, text="", font=fonts().small, text_color=PALETTE.DANGER,
            wraplength=356, justify="left",
        )
        self.error.grid(row=5, column=0, padx=PAD_XL, sticky="ew")

        self.button = ctk.CTkButton(
            self.card, text="Sign in", height=42, font=fonts().body_bold,
            fg_color=PALETTE.ACCENT, hover_color=PALETTE.ACCENT_HOVER,
            text_color=PALETTE.ACCENT_TEXT, command=self._sign_in,
        )
        self.button.grid(row=6, column=0, padx=PAD_XL, sticky="ew", pady=(PAD, PAD_SM))

        ctk.CTkLabel(
            self.card, text="Default account: admin / admin123",
            font=fonts().small, text_color=PALETTE.TEXT_DIM,
        ).grid(row=7, column=0, padx=PAD_XL, pady=(0, PAD_XL))

        self.username.bind("<Return>", lambda _e: self._sign_in())
        self.password.bind("<Return>", lambda _e: self._sign_in())
        self.after(100, self.username.focus_set)

    def _sign_in(self) -> None:
        username = self.username.get().strip()
        password = self.password.get()
        if not username or not password:
            self._show_error("Enter both a username and a password.")
            return

        self.button.configure(state="disabled", text="Signing in...")
        self.update_idletasks()

        try:
            user = self.users.authenticate(username, password)
        except DatabaseError as exc:
            self._show_error(str(exc))
            return
        finally:
            self.button.configure(state="normal", text="Sign in")

        if user is None:
            self._show_error("Incorrect username or password.")
            self.password.delete(0, "end")
            self.password.focus_set()
            return

        self.on_success(user)

    def _show_error(self, message: str) -> None:
        self.error.configure(text=message)
