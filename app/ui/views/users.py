"""User account administration."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from app.db.auth import ALL_ROLES
from app.ui.dialogs import FormDialog
from app.ui.theme import PAD, PAD_LG, RADIUS, fonts
from app.ui.views.base import BaseView
from app.ui.widgets import PALETTE, Column, DataTable, FormPanel, confirm


class UserDialog(FormDialog):
    def __init__(self, master, repos, account: dict | None = None) -> None:
        self.repos = repos
        self.account = account
        super().__init__(master, "Edit user" if account else "Add user", size=(600, 480))

    def build(self, form: FormPanel) -> None:
        officers = self.repos.officers.options()
        form.add_entry("username", "Username", required=True)
        form.add_entry("full_name", "Full name")
        form.add_choice("role", "Role", list(ALL_ROLES), required=True)
        form.add_choice("officer", "Linked officer",
                        ["None"] + [f"{row['name']} - {row['rank']}" for row in officers])
        if not self.account:
            form.add_entry("password", "Password", placeholder="At least 6 characters",
                           required=True)
        if self.account:
            form.set("username", self.account.get("username"))
            form.set("full_name", self.account.get("full_name"))
            form.set("role", self.account.get("role"))

    def validate(self, values: dict[str, Any]) -> bool:
        if not self.account:
            if len(values.get("password", "")) < 6:
                self.error.configure(text="Use a password of at least 6 characters.")
                return False
        return True

    def on_save(self, values: dict[str, Any]) -> None:
        officers = self.repos.officers.options()
        label = values.get("officer", "None")
        officer_id = None
        if label != "None":
            officer = next((row for row in officers if label.startswith(row["name"])), None)
            officer_id = officer["officer_id"] if officer else None

        if self.account:
            self.repos.users.update(
                self.account["user_id"], username=values["username"], role=values["role"],
                full_name=values.get("full_name") or None, officer_id=officer_id,
            )
        else:
            self.repos.users.create(
                values["username"], values["password"], values["role"],
                full_name=values.get("full_name") or None, officer_id=officer_id,
            )


class PasswordDialog(FormDialog):
    def __init__(self, master, repos, account: dict) -> None:
        self.repos = repos
        self.account = account
        super().__init__(master, f"Reset password - {account['username']}",
                         size=(460, 320), save_text="Reset")

    def build(self, form: FormPanel) -> None:
        form.add_entry("password", "New password", placeholder="At least 6 characters",
                       required=True)
        form.add_entry("confirm", "Confirm password", required=True)

    def validate(self, values: dict[str, Any]) -> bool:
        if len(values.get("password", "")) < 6:
            self.error.configure(text="Use a password of at least 6 characters.")
            return False
        if values.get("password") != values.get("confirm"):
            self.error.configure(text="The two passwords do not match.")
            return False
        return True

    def on_save(self, values: dict[str, Any]) -> None:
        self.repos.users.set_password(self.account["user_id"], values["password"])


class UsersView(BaseView):
    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(self, fg_color=PALETTE.SURFACE, corner_radius=RADIUS)
        bar.grid(row=0, column=0, sticky="ew", padx=PAD_LG, pady=(PAD_LG, PAD))
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            bar, text="User accounts", font=fonts().subtitle, text_color=PALETTE.TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(PAD, PAD_SM))

        ctk.CTkButton(
            bar, text="Add user", width=140, height=36, font=fonts().body_bold,
            fg_color=PALETTE.ACCENT, hover_color=PALETTE.ACCENT_HOVER,
            text_color=PALETTE.ACCENT_TEXT, command=self._add,
        ).grid(row=0, column=1, sticky="e", padx=(0, PAD), pady=PAD)

        self.table = DataTable(
            self,
            [
                Column("username", "Username", 160),
                Column("full_name", "Full name", 200),
                Column("role", "Role", 120),
                Column("officer_name", "Linked officer", 200),
                Column("is_active", "Active", 100, anchor="center",
                       render=lambda row: "Yes" if row.get("is_active") else "No"),
                Column("last_login_at", "Last sign-in", 170),
            ],
            title="Accounts",
            empty_text="No user accounts.",
            on_row_double=self._edit,
        )
        self.table.grid(row=1, column=0, sticky="nsew", padx=PAD_LG, pady=(0, PAD_LG))

    def refresh(self) -> None:
        self.table.set_rows(self.guard(self.repos.users.list_all) or [])

    def _add(self) -> None:
        dialog = UserDialog(self.app, self.repos)
        if dialog.show():
            self.app.toast("User created", "success")
            self.refresh()

    def _edit(self, row: dict) -> None:
        dialog = UserDialog(self.app, self.repos, row)
        if dialog.show():
            self.app.toast("User updated", "success")
            self.refresh()
        else:
            self._offer_reset(row)

    def _offer_reset(self, row: dict) -> None:
        if confirm(self.app, "Reset password",
                   f"Change the password for '{row['username']}'?", "Reset"):
            dialog = PasswordDialog(self.app, self.repos, row)
            if dialog.show():
                self.app.toast("Password reset", "success")
