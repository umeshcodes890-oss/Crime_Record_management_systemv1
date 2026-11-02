"""Colours, fonts and spacing for the whole application.

Light and dark palettes are defined side by side so the theme toggle in
the header can swap between them without any screen knowing about it.
"""

from __future__ import annotations

import customtkinter as ctk

DARK = "dark"
LIGHT = "light"


class Palette:
    """Colours for the dark theme (the default)."""

    BG = "#0f1319"
    SURFACE = "#171d26"
    SURFACE_ALT = "#1e2632"
    SURFACE_HOVER = "#26313f"
    BORDER = "#2b3646"
    TEXT = "#e8ecf4"
    TEXT_MUTED = "#8b97a9"
    TEXT_DIM = "#5f6b80"

    ACCENT = "#3fb6a8"
    ACCENT_HOVER = "#33a094"
    ACCENT_SOFT = "#1c3b39"
    ACCENT_TEXT = "#0f1319"

    DANGER = "#e05263"
    DANGER_HOVER = "#c94454"
    WARNING = "#e8a33d"
    SUCCESS = "#4caf7d"
    INFO = "#5b8dd9"
    VIOLET = "#9b6ede"


class LightPalette:
    """Colours for the light theme."""

    BG = "#f4f6fa"
    SURFACE = "#ffffff"
    SURFACE_ALT = "#ffffff"
    SURFACE_HOVER = "#e8ecf3"
    BORDER = "#d6dce8"
    TEXT = "#16202e"
    TEXT_MUTED = "#5b6779"
    TEXT_DIM = "#8592a6"

    ACCENT = "#1f8c80"
    ACCENT_HOVER = "#19756b"
    ACCENT_SOFT = "#d6ece9"
    ACCENT_TEXT = "#ffffff"

    DANGER = "#c83a4b"
    DANGER_HOVER = "#ad2f3e"
    WARNING = "#b8791a"
    SUCCESS = "#2f855a"
    INFO = "#3767b5"
    VIOLET = "#6f4bb5"


class PaletteSet:
    """Holds the palette for the current appearance mode."""

    def __init__(self, mode: str = DARK) -> None:
        self.mode = mode

    @property
    def colors(self) -> type[Palette] | type[LightPalette]:
        return LightPalette if self.mode == LIGHT else Palette

    def __getattr__(self, item: str):
        return getattr(self.colors, item)

    @property
    def case_status(self) -> dict[str, str]:
        c = self.colors
        return {
            "registered": c.INFO,
            "under_investigation": c.WARNING,
            "charges_filed": c.VIOLET,
            "trial": "#d07a3c",
            "closed_convicted": c.SUCCESS,
            "closed_acquitted": c.TEXT_MUTED,
            "closed_untraceable": c.DANGER,
        }

    @property
    def severity(self) -> dict[str, str]:
        c = self.colors
        return {
            "low": c.SUCCESS,
            "medium": c.WARNING,
            "high": "#d07a3c",
            "grave": c.DANGER,
        }


class Fonts:
    """Application fonts. Created once, after the Tk root exists."""

    def __init__(self) -> None:
        self.display = ctk.CTkFont(size=26, weight="bold")
        self.title = ctk.CTkFont(size=20, weight="bold")
        self.subtitle = ctk.CTkFont(size=15, weight="bold")
        self.heading = ctk.CTkFont(size=14, weight="bold")
        self.body = ctk.CTkFont(size=13)
        self.body_bold = ctk.CTkFont(size=13, weight="bold")
        self.small = ctk.CTkFont(size=11)
        self.label = ctk.CTkFont(size=11, weight="bold")
        self.mono = ctk.CTkFont(family="Consolas", size=12)
        self.pill = ctk.CTkFont(size=11, weight="bold")


_fonts: Fonts | None = None


def fonts() -> Fonts:
    global _fonts
    if _fonts is None:
        _fonts = Fonts()
    return _fonts


# Spacing scale
PAD_XS = 4
PAD_SM = 8
PAD = 14
PAD_LG = 22
PAD_XL = 32

RADIUS = 12
RADIUS_SM = 8


def status_label(status: str) -> str:
    """Turn a machine status into a readable label."""
    return status.replace("_", " ").title()


def format_datetime(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    return value.strftime("%d %b %Y, %I:%M %p")


def format_date(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    return value.strftime("%d %b %Y")
