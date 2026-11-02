"""Entry point for the Crime Record Management System."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import customtkinter as ctk

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.connection import ConfigError, ConnectionLost, Database, DatabaseError  # noqa: E402
from app.ui.app_window import AppWindow  # noqa: E402
from app.ui.login import LoginScreen  # noqa: E402
from app.ui.theme import PAD, PAD_LG, PAD_SM, PAD_XL, fonts  # noqa: E402
from app.ui.widgets import PALETTE, apply_ttk_styles  # noqa: E402

LOG_DIR = PROJECT_ROOT / "logs"


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8")],
    )


class Application:
    """Owns the root window and swaps between the login and the shell."""

    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk()
        self.root.title("Crime Record Management System")
        self.root.geometry("1380x880")
        self.root.minsize(1200, 760)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        apply_ttk_styles()

        self.db: Database | None = None
        self.window: AppWindow | None = None
        self.show_login()

    def quit(self) -> None:
        """Close the window without leaving Tcl noise in the console.

        CustomTkinter keeps a repeating 'after' callback alive for DPI
        scaling; if it is still pending when the root is destroyed, Tk
        complains about an invalid command name on the way out.
        """
        try:
            for callback in self.root.tk.call("after", "info"):
                self.root.after_cancel(callback)
        except Exception:
            pass
        self.root.destroy()

    def clear(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()

    def show_login(self) -> None:
        self.clear()
        try:
            self.db = Database()
            # Fail early with a clear message if the schema is missing.
            self.db.query_one("SELECT user_id FROM users LIMIT 1")
        except ConfigError as exc:
            self.show_startup_error(str(exc), "Setup needed")
            return
        except ConnectionLost as exc:
            self.show_startup_error(str(exc), "Cannot reach MySQL")
            return
        except DatabaseError:
            self.show_startup_error(
                "The database exists but the tables do not.\n"
                "Create the schema first:\n\n    py scripts\\setup_db.py",
                "Schema missing",
            )
            return

        login = LoginScreen(self.root, self.db, self.on_login)
        login.pack(fill="both", expand=True)

    def on_login(self, user: dict) -> None:
        self.clear()
        self.window = AppWindow(self.root, self.db, user, self.show_login)
        self.window.pack(fill="both", expand=True)

    def show_startup_error(self, message: str, heading: str) -> None:
        self.clear()
        frame = ctk.CTkFrame(self.root, fg_color=PALETTE.BG)
        frame.pack(fill="both", expand=True)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        card = ctk.CTkFrame(frame, fg_color=PALETTE.SURFACE, corner_radius=14, width=620)
        card.grid(row=0, column=0)
        card.grid_columnconfigure(0, weight=1)
        card.grid_propagate(False)

        ctk.CTkLabel(
            card, text=heading, font=fonts().title, text_color=PALETTE.DANGER,
        ).grid(row=0, column=0, padx=PAD_XL, pady=(PAD_XL, PAD_SM))
        ctk.CTkLabel(
            card, text=message, font=fonts().body, text_color=PALETTE.TEXT_MUTED,
            anchor="w", justify="left", wraplength=540,
        ).grid(row=1, column=0, sticky="w", padx=PAD_XL)

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="e", padx=PAD_XL, pady=PAD_LG)
        ctk.CTkButton(
            buttons, text="Quit", width=110, height=36, font=fonts().body,
            fg_color="transparent", border_width=1, border_color=PALETTE.BORDER,
            text_color=PALETTE.TEXT, command=self.quit,
        ).pack(side="left", padx=(0, PAD))
        ctk.CTkButton(
            buttons, text="Retry", width=110, height=36, font=fonts().body_bold,
            fg_color=PALETTE.ACCENT, hover_color=PALETTE.ACCENT_HOVER,
            text_color=PALETTE.ACCENT_TEXT, command=self.show_login,
        ).pack(side="left")


def main() -> int:
    setup_logging()
    app = Application()
    app.root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
