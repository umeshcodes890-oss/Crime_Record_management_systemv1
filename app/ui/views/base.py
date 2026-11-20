"""Shared behaviour for every screen."""

from __future__ import annotations

from typing import Any, Callable, Iterable, NamedTuple

import customtkinter as ctk

from app.db.connection import DatabaseError
from app.db.privacy import RESTRICTED
from app.db.repositories import Repositories
from app.ui.theme import PAD, PAD_LG, PAD_SM, RADIUS, fonts
from app.ui.widgets import (
    PALETTE, Column, DataTable, FormPanel, StatusPill, as_form_values, confirm,
)


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


class Button(NamedTuple):
    """A button shown above a table on a profile tab."""

    label: str
    command: Callable[[], None]
    write: bool = True


class ProfileView(BaseView):
    """One victim, witness or evidence item, opened tab by tab.

    A screen builds its tabs in its constructor and hands this class the
    loader for each one; :meth:`reload` then refills the heading, every
    form and every table without the screen having to remember them.
    """

    def __init__(self, master, app, *, on_back: Callable[[], None]) -> None:
        super().__init__(master, app)
        self.on_back = on_back
        self._record: dict = {}
        self._tables: dict[str, DataTable] = {}
        self._loads: list[Callable[[], None]] = []

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_header()

        self.tabs = ctk.CTkTabview(
            self, fg_color=PALETTE.SURFACE,
            segmented_button_fg_color=PALETTE.SURFACE_ALT,
            segmented_button_selected_color=PALETTE.ACCENT,
            segmented_button_selected_hover_color=PALETTE.ACCENT_HOVER,
            segmented_button_unselected_color=PALETTE.SURFACE_ALT,
            segmented_button_unselected_hover_color=PALETTE.SURFACE_HOVER,
            text_color=PALETTE.TEXT, corner_radius=RADIUS,
        )
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=PAD_LG, pady=(0, PAD_LG))

    # ------------------------------------------------------------------
    # heading
    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=PALETTE.SURFACE, corner_radius=RADIUS)
        header.grid(row=0, column=0, sticky="ew", padx=PAD_LG, pady=(PAD_LG, PAD))
        header.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=(PAD_LG, PAD), pady=PAD)
        left.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            left, text="Back", width=80, height=32, font=fonts().small,
            fg_color="transparent", border_width=1, border_color=PALETTE.BORDER,
            text_color=PALETTE.TEXT_MUTED, hover_color=PALETTE.SURFACE_HOVER,
            command=self.on_back,
        ).grid(row=0, column=0, sticky="w", padx=(0, PAD), rowspan=2)

        self.title_label = ctk.CTkLabel(
            left, text="", font=fonts().title, text_color=PALETTE.TEXT, anchor="w",
        )
        self.title_label.grid(row=0, column=1, sticky="w")

        self.subtitle_label = ctk.CTkLabel(
            left, text="", font=fonts().small, text_color=PALETTE.TEXT_MUTED, anchor="w",
        )
        self.subtitle_label.grid(row=1, column=1, sticky="w", pady=(2, 0))

        self.pills = ctk.CTkFrame(header, fg_color="transparent")
        self.pills.grid(row=0, column=1, sticky="e", padx=(0, PAD))

        self.actions = ctk.CTkFrame(header, fg_color="transparent")
        self.actions.grid(row=0, column=2, sticky="e", padx=(0, PAD_LG))

    def set_heading(self, title: str, subtitle: str = "",
                    pills: Iterable[tuple[str, str]] = ()) -> None:
        self.title_label.configure(text=title)
        self.subtitle_label.configure(text=subtitle)
        for child in self.pills.winfo_children():
            child.destroy()
        for text, colour in pills:
            StatusPill(self.pills, text, colour).pack(side="left", padx=(PAD_SM, 0))

    def add_action(self, text: str, command: Callable[[], None], *,
                   write: bool = True, danger: bool = False) -> None:
        """Put a button in the header. Writers-only buttons stay hidden."""
        if write and not self.can_write():
            return
        ctk.CTkButton(
            self.actions, text=text, width=140, height=36, font=fonts().body,
            fg_color="transparent" if danger else PALETTE.SURFACE_ALT,
            hover_color=PALETTE.SURFACE_HOVER,
            border_width=1 if danger else 0,
            border_color=PALETTE.DANGER if danger else PALETTE.BORDER,
            text_color=PALETTE.DANGER if danger else PALETTE.TEXT,
            command=command,
        ).pack(side="left", padx=(PAD_SM, 0))

    # ------------------------------------------------------------------
    # tabs
    # ------------------------------------------------------------------
    def open_tab(self, name: str, *, blocks: int = 2) -> ctk.CTkFrame:
        """Add a tab and hand its rows to the blocks placed inside it.

        A block is a bar plus the widget under it, so a tab with two
        blocks shows, say, a short form above the table it belongs to.
        Only the last block grows when the window does.
        """
        page = self.tabs.add(name)
        page.grid_columnconfigure(0, weight=1)
        for row in range(blocks):
            page.grid_rowconfigure(row, weight=1 if row == blocks - 1 else 0)
        return page

    def form_tab(self, name: str, *, build: Callable[[FormPanel], None],
                 save: Callable[[dict], None], title: str = "",
                 note: str = "", save_text: str = "Save changes",
                 present: Callable[[dict], dict] = as_form_values,
                 accept: Callable[[dict], dict] = lambda values: values,
                 columns: int = 2, page: ctk.CTkFrame | None = None, row: int = 0,
                 scroll: bool = True) -> FormPanel:
        """An editable form of the record's own fields.

        ``present`` turns the record into field values and ``accept``
        turns field values back into columns, so a screen only describes
        the two or three fields that are not plain text.
        """
        page = page if page is not None else self.open_tab(name)

        bar = ctk.CTkFrame(page, fg_color="transparent")
        bar.grid(row=row, column=0, sticky="ew", padx=PAD, pady=(PAD, PAD_SM))
        bar.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            bar, text=title or name, font=fonts().heading, text_color=PALETTE.TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        if note:
            ctk.CTkLabel(
                bar, text=note, font=fonts().small, text_color=PALETTE.TEXT_MUTED, anchor="e",
            ).grid(row=0, column=1, sticky="e", padx=PAD)
        if self.can_write():
            ctk.CTkButton(
                bar, text=save_text, width=140, height=32, font=fonts().small,
                fg_color=PALETTE.ACCENT, hover_color=PALETTE.ACCENT_HOVER,
                text_color=PALETTE.ACCENT_TEXT,
                command=lambda: self._save_form(form, accept, save),
            ).grid(row=0, column=2, sticky="e")

        if scroll:
            host = ctk.CTkScrollableFrame(page, fg_color="transparent")
            host.grid(row=row + 1, column=0, sticky="nsew",
                      padx=(PAD, PAD - 6), pady=(0, PAD))
            host.grid_columnconfigure(0, weight=1)
            place = {"row": 0, "column": 0, "sticky": "ew",
                     "padx": (0, PAD), "pady": PAD_SM}
        else:
            host = page
            place = {"row": row + 1, "column": 0, "sticky": "ew",
                     "padx": PAD, "pady": (0, PAD_SM)}

        form = FormPanel(host, columns=columns)
        build(form)
        form.grid(**place)

        self._loads.append(lambda: self._fill_form(form, present))
        return form

    def table_tab(self, name: str, columns: list[Column], *, load: Callable[[], list[dict]],
                  title: str = "", note: str = "", buttons: Iterable[Button] = (),
                  add: Callable[[], None] | None = None, add_text: str = "Add",
                  delete: Callable[[dict], None] | None = None,
                  on_row_double: Callable[[dict], None] | None = None,
                  privileged_only: bool = False, empty_text: str = "Nothing recorded yet.",
                  searchable: bool = True, height: int = 320,
                  page: ctk.CTkFrame | None = None, row: int = 0) -> DataTable | None:
        """A table of the child rows belonging to the record.

        ``privileged_only`` leaves the block as a notice for a role the
        repository would refuse anyway; the refusal itself stays in the
        repository, so hiding this changes nothing but the noise.
        """
        page = page if page is not None else self.open_tab(name)

        if privileged_only and not self.can_write():
            ctk.CTkLabel(
                page,
                text="This detail belongs to the case staff working the record.\n"
                     "It is not shown to a viewer.",
                font=fonts().body, text_color=PALETTE.TEXT_MUTED, justify="left",
            ).grid(row=row + 1, column=0, sticky="w", padx=PAD_LG, pady=PAD_LG)
            return None

        table = DataTable(
            page, columns, title="", searchable=searchable, height=height,
            empty_text=empty_text, on_row_double=on_row_double,
            on_delete=(lambda row: self._run(lambda: delete(row)))
            if (delete is not None and self.can_write()) else None,
        )
        table.grid(row=row + 1, column=0, sticky="nsew", padx=PAD, pady=(0, PAD))

        bar = ctk.CTkFrame(page, fg_color="transparent")
        bar.grid(row=row, column=0, sticky="ew", padx=PAD, pady=(PAD, PAD_SM))
        bar.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            bar, text=title or name, font=fonts().heading, text_color=PALETTE.TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        if note:
            ctk.CTkLabel(
                bar, text=note, font=fonts().small, text_color=PALETTE.TEXT_MUTED, anchor="e",
            ).grid(row=0, column=1, sticky="e", padx=PAD)

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e")
        for button in buttons:
            if button.write and not self.can_write():
                continue
            ctk.CTkButton(
                right, text=button.label, width=140, height=32, font=fonts().small,
                fg_color=PALETTE.SURFACE_ALT, hover_color=PALETTE.SURFACE_HOVER,
                text_color=PALETTE.TEXT, command=button.command,
            ).pack(side="left", padx=(PAD_SM, 0))
        if add is not None and self.can_write():
            ctk.CTkButton(
                right, text=add_text, width=120, height=32, font=fonts().small,
                fg_color=PALETTE.ACCENT, hover_color=PALETTE.ACCENT_HOVER,
                text_color=PALETTE.ACCENT_TEXT,
                command=lambda: self._run(add),
            ).pack(side="left", padx=(PAD_SM, 0))

        self._tables[name] = table
        self._loads.append(lambda: self._fill_table(table, load))
        return table

    # ------------------------------------------------------------------
    # interaction
    # ------------------------------------------------------------------
    def selected(self, name: str) -> dict | None:
        table = self._tables.get(name)
        return table.selected_row if table is not None else None

    def require_selection(self, name: str, what: str,
                          action: Callable[[dict], None]) -> None:
        """Act on the highlighted row, or say why nothing happened."""
        row = self.selected(name)
        if row is None:
            self.app.toast(f"Select {what} first.", "error")
            return
        self._run(action, row, success=None)

    def _run(self, action: Callable, *args, success: str | None = None) -> Any:
        """Do something that the repository may refuse, and say so."""
        try:
            result = action(*args)
        except DatabaseError as exc:
            self.app.toast(str(exc), "error", 6500)
            return None
        self.reload()
        if success:
            self.app.toast(success, "success")
        return result

    def _save_form(self, form: FormPanel, accept: Callable[[dict], dict],
                   save: Callable[[dict], None]) -> None:
        values = accept(form.values())
        # A field this user was not allowed to read holds the placeholder.
        # Saving it would write the mask over somebody else's real answer.
        values = {key: value for key, value in values.items() if value != RESTRICTED}
        if not values:
            self.app.toast("There is nothing here for you to change.", "info")
            return
        self._run(save, values, success="Saved")

    # -- reloading ----------------------------------------------------
    @property
    def record(self) -> dict:
        return self._record

    def load_record(self) -> dict | None:
        """The row this page is about. Overridden by every screen."""
        raise NotImplementedError

    def paint_heading(self, record: dict) -> None:
        """Say who or what the page is about. Overridden by each screen."""
        raise NotImplementedError

    def reload(self) -> None:
        try:
            record = self.load_record()
        except DatabaseError as exc:
            self.app.toast(str(exc), "error", 6500)
            return
        if record is None:
            self.app.toast("That record is no longer here.", "error")
            self.on_back()
            return
        self._record = record
        self.guard(self.paint_heading, record)
        for reload_tab in self._loads:
            reload_tab()

    def _fill_form(self, form: FormPanel, present: Callable[[dict], dict]) -> None:
        for key, value in present(self._record).items():
            form.set(key, value)

    def _fill_table(self, table: DataTable, load: Callable[[], list[dict]]) -> None:
        rows = self.guard(load)
        if rows is not None:
            table.set_rows(rows)


PAD_GAP = 12
