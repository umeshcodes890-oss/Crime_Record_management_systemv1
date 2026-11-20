"""Modal dialogs used by the screens."""

from __future__ import annotations

from typing import Any, Sequence

import customtkinter as ctk

from app.ui.theme import PAD, PAD_LG, PAD_SM, RADIUS, fonts
from app.ui.widgets import FormPanel, PALETTE, as_form_values


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

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=(PAD_LG, PAD_LG - 6))
        self.body.grid_columnconfigure(0, weight=1)

        self.form = FormPanel(self.body, columns=2)
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
        self.after(120, self._sync_scrollbar)

    def _centre(self) -> None:
        self.update_idletasks()
        master = self.master
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _sync_scrollbar(self) -> None:
        """Hide the body scrollbar when the form already fits.

        CustomTkinter draws it whenever a scrollable frame exists, so a
        short form ends up showing a bar that cannot move.
        """
        scrollbar = getattr(self.body, "_scrollbar", None)
        canvas = getattr(self.body, "_parent_canvas", None)
        if scrollbar is None or canvas is None:
            return
        top, bottom = canvas.yview()
        if top <= 0.0 and bottom >= 1.0:
            scrollbar.grid_remove()
        else:
            scrollbar.grid()

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


class ChildFormDialog(FormDialog):
    """Add or edit one row that belongs to a victim, a witness or an item.

    The subclass names the fields in ``build`` and says where they go in
    ``save``. Handing the existing row over here is what makes every
    child form open filled in when it edits, and blank when it adds.
    """

    item_name = "record"
    size: tuple[int, int] = (680, 520)
    columns = 2

    def __init__(self, master, repos, parent_id: int,
                 record: dict | None = None) -> None:
        self.repos = repos
        self.parent_id = parent_id
        self.record = dict(record or {})
        verb = "Edit" if self.record else "Add"
        super().__init__(master, f"{verb} {self.item_name}", size=self.size)

    @property
    def is_new(self) -> bool:
        return not self.record

    def prefill(self, form: FormPanel, *, yes_no: Sequence[str] = ()) -> None:
        """Put the row being edited into the fields it owns."""
        for key, value in as_form_values(self.record, yes_no=yes_no).items():
            form.set(key, value)


def officer_choices(officers: Sequence[dict]) -> list[str]:
    """The names a screen offers for an officer."""
    return [f"{row['name']} - {row['rank']}" for row in officers]


def officer_id_for(officers: Sequence[dict], label: str | None) -> int | None:
    """The officer a choice on screen stands for, or None for no choice."""
    if not label:
        return None
    for row in officers:
        if label.startswith(row["name"]):
            return row["officer_id"]
    return None


class TextDialog(ctk.CTkToplevel):
    """A read-only look at a long piece of text: a statement, a report."""

    def __init__(self, master, title: str, body: str, *, subtitle: str = "",
                 size: tuple[int, int] = (720, 560)) -> None:
        super().__init__(master)
        self.title(title)
        self.geometry(f"{size[0]}x{size[1]}")
        self.resizable(True, True)
        self.transient(master)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self, text=title, font=fonts().subtitle, text_color=PALETTE.TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=PAD_LG, pady=(PAD_LG, 0))
        if subtitle:
            ctk.CTkLabel(
                self, text=subtitle, font=fonts().small, text_color=PALETTE.TEXT_MUTED,
                anchor="w", justify="left",
            ).grid(row=1, column=0, sticky="w", padx=PAD_LG, pady=(0, PAD))

        box = ctk.CTkTextbox(
            self, font=fonts().body, wrap="word", fg_color=PALETTE.SURFACE_ALT,
            border_color=PALETTE.BORDER, border_width=1, text_color=PALETTE.TEXT,
        )
        box.grid(row=2, column=0, sticky="nsew", padx=PAD_LG, pady=PAD)
        box.insert("1.0", body or "Nothing was recorded.")
        box.configure(state="disabled")

        ctk.CTkButton(
            self, text="Close", width=110, height=36, font=fonts().body,
            fg_color=PALETTE.ACCENT, hover_color=PALETTE.ACCENT_HOVER,
            text_color=PALETTE.ACCENT_TEXT, command=self.destroy,
        ).grid(row=3, column=0, sticky="e", padx=PAD_LG, pady=(0, PAD_LG))

    def show(self) -> None:
        self.master.wait_window(self)
