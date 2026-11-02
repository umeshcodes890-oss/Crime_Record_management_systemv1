"""Modal dialogs used by the screens."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from app.ui.theme import PAD, PAD_LG, PAD_SM, RADIUS, fonts
from app.ui.widgets import PALETTE, FormPanel


class FormDialog(ctk.CTkToplevel):
    """A modal form.

    Subclasses fill the form in ``build`` and handle the result in
    ``on_save``; ``show`` returns the saved values or None if cancelled.
    """

    def __init__(self, master, title: str, *, size: tuple[int, int] = (660, 560),
                 save_text: str = "Save") -> None:
        super().__init__(master)
        self.title(title)
        self.geometry(f"{size[0]}x{size[1]}")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.saved: dict[str, Any] | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=PAD_LG, pady=(PAD_LG, PAD))
        ctk.CTkLabel(
            header, text=title, font=fonts().subtitle, text_color=PALETTE.TEXT, anchor="w",
        ).pack(anchor="w")

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=(PAD_LG, PAD_LG - 6))
        body.grid_columnconfigure(0, weight=1)

        self.form = FormPanel(body, columns=2)
        self.form.grid(row=0, column=0, sticky="ew")

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=PAD_LG, pady=PAD)
        footer.grid_columnconfigure(0, weight=1)

        self.error = ctk.CTkLabel(
            footer, text="", font=fonts().small, text_color=PALETTE.DANGER, anchor="w",
        )
        self.error.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            footer, text="Cancel", width=110, height=36, font=fonts().body,
            fg_color="transparent", border_width=1, border_color=PALETTE.BORDER,
            text_color=PALETTE.TEXT, command=self.destroy,
        ).grid(row=0, column=1, padx=(0, PAD_SM))
        ctk.CTkButton(
            footer, text=save_text, width=110, height=36, font=fonts().body,
            fg_color=PALETTE.ACCENT, hover_color=PALETTE.ACCENT_HOVER,
            text_color=PALETTE.ACCENT_TEXT, command=self._save,
        ).grid(row=0, column=2)

        self.after(50, self._centre)

    def _centre(self) -> None:
        self.update_idletasks()
        master = self.master
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def build(self, form: FormPanel) -> None:
        """Add the fields. Overridden by subclasses."""

    def collect(self) -> dict[str, Any]:
        return self.form.values()

    def validate(self, values: dict[str, Any]) -> bool:
        return True

    def on_save(self, values: dict[str, Any]) -> None:
        """Persist the values. Raise to keep the dialog open."""

    def _save(self) -> None:
        values = self.collect()
        if not self.validate(values):
            return
        try:
            self.on_save(values)
        except Exception as exc:  # shown in the dialog, dialog stays open
            self.error.configure(text=str(exc))
            return
        self.saved = values
        self.destroy()

    def show(self) -> dict[str, Any] | None:
        self.build(self.form)
        self.master.wait_window(self)
        return self.saved


class ChoiceDialog(ctk.CTkToplevel):
    """Pick one row from a list of options."""

    def __init__(self, master, title: str, options: list[tuple[int, str]],
                 subtitle: str = "") -> None:
        super().__init__(master)
        self.title(title)
        self.geometry("520x560")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.choice: int | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self, text=title, font=fonts().subtitle, text_color=PALETTE.TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=PAD_LG, pady=(PAD_LG, 0))
        if subtitle:
            ctk.CTkLabel(
                self, text=subtitle, font=fonts().small, text_color=PALETTE.TEXT_MUTED,
                anchor="w",
            ).grid(row=1, column=0, sticky="w", padx=PAD_LG, pady=(0, PAD))

        list_frame = ctk.CTkScrollableFrame(self, fg_color=PALETTE.SURFACE,
                                            corner_radius=RADIUS)
        list_frame.grid(row=2, column=0, sticky="nsew", padx=PAD_LG)
        list_frame.grid_columnconfigure(0, weight=1)

        for identifier, label in options:
            ctk.CTkButton(
                list_frame, text=label, height=38, font=fonts().body, anchor="w",
                fg_color="transparent", hover_color=PALETTE.SURFACE_HOVER,
                text_color=PALETTE.TEXT,
                command=lambda value=identifier: self._pick(value),
            ).grid(row=len(list_frame.grid_slaves()), column=0, sticky="ew",
                  padx=PAD_SM, pady=1)

        ctk.CTkButton(
            self, text="Cancel", width=110, height=36, font=fonts().body,
            fg_color="transparent", border_width=1, border_color=PALETTE.BORDER,
            text_color=PALETTE.TEXT, command=self.destroy,
        ).grid(row=3, column=0, sticky="e", padx=PAD_LG, pady=PAD)

        self.after(50, self._centre)

    def _centre(self) -> None:
        self.update_idletasks()
        master = self.master
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _pick(self, value: int) -> None:
        self.choice = value
        self.destroy()

    def show(self) -> int | None:
        self.master.wait_window(self)
        return self.choice
