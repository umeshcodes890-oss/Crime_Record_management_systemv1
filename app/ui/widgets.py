"""Reusable UI components: cards, tables, forms, toasts and dialogs.

Every screen in the application is built from these, so the look stays
consistent and a change to the table or the form behaviour applies
everywhere at once.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from tkinter import ttk
from typing import Any, Callable, Sequence

import customtkinter as ctk

from app.ui.theme import (
    DARK,
    PAD,
    PAD_LG,
    PAD_SM,
    RADIUS,
    PaletteSet,
    fonts,
)

PALETTE = PaletteSet(DARK)


def set_mode(mode: str) -> None:
    """Switch the palette used by the shared widgets."""
    global PALETTE
    PALETTE = PaletteSet(mode)
    apply_ttk_styles()


def apply_ttk_styles() -> None:
    """Style the ttk widgets (the data table) to match the palette."""
    c = PALETTE.colors
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        "Crime.Treeview",
        background=c.SURFACE_ALT,
        fieldbackground=c.SURFACE_ALT,
        foreground=c.TEXT,
        rowheight=32,
        borderwidth=0,
        relief="flat",
        bordercolor=c.SURFACE_ALT,
        lightcolor=c.SURFACE_ALT,
        darkcolor=c.SURFACE_ALT,
        font=("Segoe UI", 12),
    )
    style.map(
        "Crime.Treeview",
        background=[("selected", c.ACCENT_SOFT)],
        foreground=[("selected", c.TEXT)],
    )
    style.configure(
        "Crime.Treeview.Heading",
        background=c.SURFACE,
        foreground=c.TEXT_MUTED,
        relief="flat",
        borderwidth=0,
        lightcolor=c.SURFACE,
        darkcolor=c.SURFACE,
        font=("Segoe UI", 11, "bold"),
        padding=(8, 9),
    )
    style.map(
        "Crime.Treeview.Heading",
        background=[("active", c.SURFACE_HOVER)],
        foreground=[("active", c.TEXT)],
    )
    style.configure(
        "Vertical.TScrollbar",
        background=c.SURFACE_HOVER,
        troughcolor=c.SURFACE,
        bordercolor=c.SURFACE,
        lightcolor=c.SURFACE,
        darkcolor=c.SURFACE,
        arrowcolor=c.TEXT_MUTED,
        borderwidth=0,
        arrowsize=12,
    )
    style.map(
        "Vertical.TScrollbar",
        background=[("active", c.ACCENT)],
        arrowcolor=[("active", c.ACCENT_TEXT)],
    )


# ----------------------------------------------------------------------
# Cards
# ----------------------------------------------------------------------
class Card(ctk.CTkFrame):
    """A raised surface with an optional heading."""

    def __init__(self, master, heading: str = "", subtitle: str = "",
                 **kwargs) -> None:
        kwargs.setdefault("fg_color", PALETTE.SURFACE)
        kwargs.setdefault("corner_radius", RADIUS)
        kwargs.setdefault("border_width", 0)
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(0, weight=1)

        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.grid(row=0, column=0, sticky="ew", padx=PAD_LG, pady=(PAD_LG, 0))

        self.heading_label = ctk.CTkLabel(
            self.header, text=heading, font=fonts().subtitle, text_color=PALETTE.TEXT,
            anchor="w", justify="left",
        )
        self.heading_label.pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(
                self.header, text=subtitle, font=fonts().small,
                text_color=PALETTE.TEXT_MUTED, anchor="w", justify="left",
            ).pack(anchor="w", pady=(2, 0))

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=PAD_LG, pady=(PAD, PAD_LG))
        self.grid_rowconfigure(1, weight=1)

    def hide_header(self) -> None:
        self.header.grid_remove()


class StatCard(ctk.CTkFrame):
    """A headline number with a caption, used across the dashboard."""

    def __init__(self, master, title: str, value: str = "0", caption: str = "",
                 accent: str | None = None, **kwargs) -> None:
        kwargs.setdefault("fg_color", PALETTE.SURFACE)
        kwargs.setdefault("corner_radius", RADIUS)
        super().__init__(master, **kwargs)
        accent = accent or PALETTE.ACCENT

        self.grid_columnconfigure(0, weight=1)

        self.bar = ctk.CTkFrame(self, fg_color=accent, corner_radius=2, height=4)
        self.bar.grid(row=0, column=0, sticky="ew", padx=PAD, pady=(PAD, 0))
        self.bar.grid_propagate(False)

        self.title_label = ctk.CTkLabel(
            self, text=title.upper(), font=fonts().label,
            text_color=PALETTE.TEXT_MUTED, anchor="w",
        )
        self.title_label.grid(row=1, column=0, sticky="ew", padx=PAD, pady=(PAD, 0))

        self.value_label = ctk.CTkLabel(
            self, text=value, font=fonts().display, text_color=PALETTE.TEXT, anchor="w",
        )
        self.value_label.grid(row=2, column=0, sticky="ew", padx=PAD)

        self.caption_label = ctk.CTkLabel(
            self, text=caption, font=fonts().small, text_color=PALETTE.TEXT_DIM, anchor="w",
        )
        self.caption_label.grid(row=3, column=0, sticky="ew", padx=PAD, pady=(0, PAD))

    def set_value(self, value: Any, caption: str | None = None) -> None:
        self.value_label.configure(text=str(value))
        if caption is not None:
            self.caption_label.configure(text=caption)


class StatusPill(ctk.CTkLabel):
    """A small rounded label used for statuses and severity."""

    def __init__(self, master, text: str, color: str | None = None, **kwargs) -> None:
        kwargs.setdefault("font", fonts().pill)
        kwargs.setdefault("corner_radius", 6)
        kwargs.setdefault("padx", 10)
        kwargs.setdefault("pady", 3)
        kwargs.setdefault("fg_color", color or PALETTE.TEXT_MUTED)
        kwargs.setdefault("text_color", "#ffffff")
        super().__init__(master, text=text, **kwargs)


# ----------------------------------------------------------------------
# Data table
# ----------------------------------------------------------------------
@dataclass
class Column:
    key: str
    title: str
    width: int = 140
    anchor: str = "w"
    render: Callable[[dict], str] | None = None


class DataTable(ctk.CTkFrame):
    """A sortable, searchable table.

    Rows are plain dicts; a column pulls its cell text from the row
    through an optional ``render`` callable.
    """

    def __init__(
        self,
        master,
        columns: Sequence[Column],
        *,
        title: str = "",
        searchable: bool = True,
        empty_text: str = "No records to show.",
        on_row_double: Callable[[dict], None] | None = None,
        on_selection: Callable[[dict | None], None] | None = None,
        on_delete: Callable[[dict], None] | None = None,
        height: int = 380,
    ) -> None:
        kwargs = {}
        super().__init__(master, fg_color=PALETTE.SURFACE_ALT, corner_radius=RADIUS, **kwargs)
        self.columns = list(columns)
        self._rows: list[dict] = []
        self._filtered: list[dict] = []
        self._sort_key: str | None = None
        self._sort_desc = False
        self._on_row_double = on_row_double
        self._on_selection = on_selection
        self._on_delete = on_delete

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # -- toolbar ---------------------------------------------------
        self.toolbar = ctk.CTkFrame(self, fg_color="transparent")
        self.toolbar.grid(row=0, column=0, sticky="ew", padx=PAD, pady=(PAD, PAD_SM))
        self.toolbar.grid_columnconfigure(1, weight=1)

        if title:
            ctk.CTkLabel(
                self.toolbar, text=title, font=fonts().heading,
                text_color=PALETTE.TEXT, anchor="w",
            ).grid(row=0, column=0, sticky="w")

        self.count_label = ctk.CTkLabel(
            self.toolbar, text="", font=fonts().small, text_color=PALETTE.TEXT_DIM, anchor="e",
        )
        self.count_label.grid(row=0, column=2, sticky="e", padx=(0, PAD_SM))

        self.delete_button = None
        if on_delete is not None:
            self.delete_button = ctk.CTkButton(
                self.toolbar, text="Delete", width=90, height=30, font=fonts().small,
                fg_color="transparent", border_width=1, border_color=PALETTE.DANGER,
                text_color=PALETTE.DANGER, hover_color=PALETTE.SURFACE_HOVER,
                state="disabled", command=self._on_delete_click,
            )
            self.delete_button.grid(row=0, column=3, sticky="e", padx=(0, PAD))

        self.search_entry = None
        if searchable:
            self.search_entry = ctk.CTkEntry(
                self.toolbar, width=220, height=32, placeholder_text="Search...",
                font=fonts().small, fg_color=PALETTE.SURFACE,
                border_color=PALETTE.BORDER, border_width=1,
            )
            self.search_entry.grid(row=0, column=1, sticky="e", padx=(PAD, PAD))
            self.search_entry.bind("<KeyRelease>", lambda _e: self._apply_filter())

        # -- tree ------------------------------------------------------
        self.tree_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.tree_frame.grid(row=1, column=0, sticky="nsew", padx=(PAD, PAD_SM), pady=(0, PAD))
        self.tree_frame.grid_columnconfigure(0, weight=1)
        self.tree_frame.grid_rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            self.tree_frame,
            columns=[c.key for c in self.columns],
            show="headings",
            selectmode="browse",
            style="Crime.Treeview",
            height=height,
        )
        for column in self.columns:
            self.tree.heading(column.key, text=column.title,
                              command=lambda k=column.key: self._sort_by(k))
            self.tree.column(column.key, width=column.width, anchor=column.anchor,
                             stretch=(column.width == 0))
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # -- empty state ------------------------------------------------
        self.empty_label = ctk.CTkLabel(
            self.tree_frame, text=empty_text, font=fonts().body,
            text_color=PALETTE.TEXT_DIM,
        )

    # -- data ---------------------------------------------------------
    def set_rows(self, rows: Sequence[dict]) -> None:
        self._rows = list(rows)
        self._apply_filter()

    def clear(self) -> None:
        self.set_rows([])

    def _apply_filter(self) -> None:
        term = ""
        if self.search_entry is not None:
            term = self.search_entry.get().strip().lower()
        if term:
            self._filtered = [
                row for row in self._rows
                if any(term in str(self._cell_text(column, row)).lower()
                       for column in self.columns)
            ]
        else:
            self._filtered = list(self._rows)
        self._sort_rows()
        self._redraw()

    def _cell_text(self, column: Column, row: dict) -> str:
        if column.render is not None:
            return str(column.render(row))
        value = row.get(column.key)
        if value is None:
            return "-"
        return str(value)

    def _sort_rows(self) -> None:
        if not self._sort_key:
            self._filtered.sort(key=lambda r: str(r.get("occurrence_datetime") or ""),
                                reverse=True)
            return
        column = next((c for c in self.columns if c.key == self._sort_key), None)
        if column is None:
            return
        self._filtered.sort(
            key=lambda r: str(self._cell_text(column, r)).lower(),
            reverse=self._sort_desc,
        )

    def _sort_by(self, key: str) -> None:
        if self._sort_key == key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key = key
            self._sort_desc = False
        self._sort_rows()
        self._redraw()

    def _redraw(self) -> None:
        self.tree.delete(*self.tree.get_children())
        if self.delete_button is not None:
            self.delete_button.configure(state="disabled")
        for index, row in enumerate(self._filtered):
            values = [self._cell_text(column, row) for column in self.columns]
            self.tree.insert("", "end", iid=str(index), values=values)

        total = len(self._rows)
        shown = len(self._filtered)
        if total == shown:
            self.count_label.configure(text=f"{total} record{'s' if total != 1 else ''}")
        else:
            self.count_label.configure(text=f"{shown} of {total} records")

        if shown:
            self.empty_label.place_forget()
        else:
            self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

    # -- selection ----------------------------------------------------
    def _on_double_click(self, _event=None) -> None:
        row = self.selected_row
        if row is not None and self._on_row_double:
            self._on_row_double(row)

    def _on_select(self, _event=None) -> None:
        if self.delete_button is not None:
            self.delete_button.configure(
                state="normal" if self.selected_row is not None else "disabled")
        if self._on_selection:
            self._on_selection(self.selected_row)

    def _on_delete_click(self) -> None:
        row = self.selected_row
        if row is not None and self._on_delete:
            self._on_delete(row)

    @property
    def selected_row(self) -> dict | None:
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            index = int(selection[0])
        except (ValueError, IndexError):
            return None
        if 0 <= index < len(self._filtered):
            return self._filtered[index]
        return None

    @property
    def selected_key(self) -> str | None:
        selection = self.tree.selection()
        return selection[0] if selection else None


# ----------------------------------------------------------------------
# Forms
# ----------------------------------------------------------------------
class FormPanel(ctk.CTkFrame):
    """A two-column form with labelled fields and inline validation.

    Fields are added with ``add_entry`` / ``add_text`` / ``add_choice``
    / ``add_date`` and read back with ``values()``.
    """

    def __init__(self, master, *, columns: int = 2, **kwargs) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._columns = columns
        self._fields: dict[str, Any] = {}
        self._row = 0
        for index in range(columns):
            self.grid_columnconfigure(index, weight=1)

    # -- building -----------------------------------------------------
    def _place(self, widget: tk.Widget, label: str, required: bool) -> None:
        row, column = divmod(self._row, self._columns)
        self._row += 1
        holder = ctk.CTkFrame(self, fg_color="transparent")
        holder.grid(row=row, column=column, sticky="ew",
                   padx=(0, PAD), pady=(0, PAD))
        holder.grid_columnconfigure(0, weight=1)

        text = f"{label} *" if required else label
        ctk.CTkLabel(
            holder, text=text, font=fonts().label, text_color=PALETTE.TEXT_MUTED, anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        widget.grid(row=1, column=0, sticky="ew")

    def add_entry(self, key: str, label: str, *, placeholder: str = "",
                  required: bool = False, width: int = 0) -> ctk.CTkEntry:
        entry = ctk.CTkEntry(
            self, width=width or 0, height=36, placeholder_text=placeholder,
            font=fonts().body, fg_color=PALETTE.SURFACE_ALT,
            border_color=PALETTE.BORDER, border_width=1,
        )
        self._place(entry, label, required)
        self._fields[key] = entry
        return entry

    def add_text(self, key: str, label: str, *, height: int = 90,
                 placeholder: str = "", required: bool = False) -> ctk.CTkTextbox:
        box = ctk.CTkTextbox(
            self, height=height, font=fonts().body, fg_color=PALETTE.SURFACE_ALT,
            border_color=PALETTE.BORDER, border_width=1, wrap="word",
        )
        if placeholder:
            box.insert("1.0", placeholder)
        self._place(box, label, required)
        self._fields[key] = box
        return box

    def add_choice(self, key: str, label: str, values: Sequence[str], *,
                   required: bool = False) -> ctk.CTkOptionMenu:
        menu = ctk.CTkOptionMenu(
            self, values=list(values), height=36, font=fonts().body,
            fg_color=PALETTE.SURFACE_ALT, button_color=PALETTE.SURFACE_HOVER,
            button_hover_color=PALETTE.BORDER, text_color=PALETTE.TEXT,
            dropdown_fg_color=PALETTE.SURFACE, dropdown_text_color=PALETTE.TEXT,
            dropdown_hover_color=PALETTE.SURFACE_HOVER, dropdown_font=fonts().body,
        )
        self._place(menu, label, required)
        self._fields[key] = menu
        return menu

    def add_date(self, key: str, label: str, *, required: bool = False) -> ctk.CTkEntry:
        entry = self.add_entry(key, label, placeholder="YYYY-MM-DD", required=required)
        return entry

    def add_datetime(self, key: str, label: str, *, required: bool = False) -> ctk.CTkEntry:
        entry = self.add_entry(key, label, placeholder="YYYY-MM-DD HH:MM", required=required)
        return entry

    # -- reading ------------------------------------------------------
    def value(self, key: str, default: Any = None) -> Any:
        widget = self._fields.get(key)
        if widget is None:
            return default
        if isinstance(widget, ctk.CTkTextbox):
            return widget.get("1.0", "end").strip()
        return widget.get().strip()

    def set(self, key: str, value: Any) -> None:
        widget = self._fields.get(key)
        if widget is None or value is None:
            return
        if isinstance(widget, ctk.CTkTextbox):
            widget.delete("1.0", "end")
            widget.insert("1.0", str(value))
        else:
            widget.delete(0, "end")
            widget.insert(0, str(value))

    def values(self) -> dict[str, Any]:
        return {key: self.value(key) for key in list(self._fields.keys())
                if isinstance(key, str)}

    def clear(self) -> None:
        for key, widget in self._fields.items():
            if isinstance(key, str) and isinstance(widget, (ctk.CTkEntry, ctk.CTkTextbox)):
                if isinstance(widget, ctk.CTkTextbox):
                    widget.delete("1.0", "end")
                else:
                    widget.delete(0, "end")

    # -- validation ---------------------------------------------------
    def validate(self, required: Sequence[str] = ()) -> bool:
        """Highlight and report the first empty required field."""
        for key in required:
            if not self.value(key):
                widget = self._fields.get(key)
                if isinstance(widget, (ctk.CTkEntry, ctk.CTkOptionMenu)):
                    widget.configure(border_color=PALETTE.DANGER)
                    widget.focus_set()
                return False
        for key, widget in self._fields.items():
            if isinstance(key, str) and isinstance(widget, (ctk.CTkEntry, ctk.CTkOptionMenu)):
                widget.configure(border_color=PALETTE.BORDER)
        return True


# ----------------------------------------------------------------------
# Feedback
# ----------------------------------------------------------------------
def toast(parent, message: str, kind: str = "info", duration: int = 3600) -> None:
    """Show a small notification in the bottom-right of the parent."""
    colors = {
        "info": PALETTE.INFO,
        "success": PALETTE.SUCCESS,
        "warning": PALETTE.WARNING,
        "error": PALETTE.DANGER,
    }
    accent = colors.get(kind, PALETTE.INFO)

    frame = ctk.CTkFrame(
        parent, fg_color=PALETTE.SURFACE, corner_radius=RADIUS,
        border_width=1, border_color=accent,
    )
    frame.place(relx=0.98, rely=0.96, anchor="se")
    frame.grid_columnconfigure(1, weight=1)

    ctk.CTkFrame(frame, fg_color=accent, corner_radius=2, width=4).grid(
        row=0, column=0, rowspan=2, sticky="ns", padx=(8, 0), pady=10)
    ctk.CTkLabel(
        frame, text=message, font=fonts().body, text_color=PALETTE.TEXT,
        anchor="w", justify="left", wraplength=340,
    ).grid(row=0, column=1, sticky="ew", padx=(10, 16), pady=(12, 2))
    frame.after(duration, frame.destroy)


def confirm(parent, title: str, message: str, confirm_text: str = "Confirm",
            danger: bool = False) -> bool:
    """Ask a yes/no question. Returns True when confirmed."""
    result = {"value": False}

    dialog = ctk.CTkToplevel(parent)
    dialog.title(title)
    dialog.geometry("440x230")
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()

    def centre() -> None:
        parent.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - dialog.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - dialog.winfo_height()) // 3
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def done(value: bool) -> None:
        result["value"] = value
        dialog.destroy()

    dialog.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(
        dialog, text=title, font=fonts().subtitle, text_color=PALETTE.TEXT, anchor="w",
    ).grid(row=0, column=0, sticky="w", padx=PAD_LG, pady=(PAD_LG, PAD_SM))
    ctk.CTkLabel(
        dialog, text=message, font=fonts().body, text_color=PALETTE.TEXT_MUTED,
        anchor="w", justify="left", wraplength=380,
    ).grid(row=1, column=0, sticky="w", padx=PAD_LG)

    buttons = ctk.CTkFrame(dialog, fg_color="transparent")
    buttons.grid(row=2, column=0, sticky="e", padx=PAD_LG, pady=PAD_LG)
    ctk.CTkButton(
        buttons, text="Cancel", width=110, height=36, font=fonts().body,
        fg_color="transparent", border_width=1, border_color=PALETTE.BORDER,
        text_color=PALETTE.TEXT, command=lambda: done(False),
    ).pack(side="left", padx=(0, PAD_SM))
    ctk.CTkButton(
        buttons, text=confirm_text, width=110, height=36, font=fonts().body,
        fg_color=PALETTE.DANGER if danger else PALETTE.ACCENT,
        hover_color=PALETTE.DANGER_HOVER if danger else PALETTE.ACCENT_HOVER,
        text_color=PALETTE.ACCENT_TEXT if not danger else "#ffffff",
        command=lambda: done(True),
    ).pack(side="left")

    dialog.after(50, centre)
    dialog.bind("<Escape>", lambda _e: done(False))
    parent.wait_window(dialog)
    return result["value"]


def parse_datetime(value: str) -> datetime | None:
    """Accept the date formats the forms allow."""
    if not value:
        return None
    value = value.strip()
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    return None
