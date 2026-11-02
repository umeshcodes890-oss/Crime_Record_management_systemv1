"""Matplotlib charts embedded in the dashboard.

Each helper returns a Figure already styled for the current palette, so
the views only have to hand it to a canvas.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("TkAgg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from app.ui.widgets import PALETTE  # noqa: E402

FIGURE_BG = None  # resolved lazily from the palette


def _style(fig: Figure, ax) -> None:
    c = PALETTE.colors
    fig.patch.set_facecolor(c.SURFACE)
    ax.set_facecolor(c.SURFACE)
    ax.title.set_color(c.TEXT)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=c.TEXT_MUTED, labelsize=9)
    ax.grid(axis="y", color=c.BORDER, alpha=0.45, linewidth=0.8)
    ax.set_axisbelow(True)


def bar_chart(labels, values, title: str, colors=None, *, horizontal: bool = False,
              size: tuple[float, float] = (5.2, 2.9)):
    c = PALETTE.colors
    fig = plt.figure(figsize=size, dpi=100)
    ax = fig.add_subplot(111)
    _style(fig, ax)

    palette = colors or [c.ACCENT] * len(labels)
    if horizontal:
        positions = range(len(labels))
        ax.barh(list(positions), values, color=palette, height=0.62)
        ax.set_yticks(list(positions))
        ax.set_yticklabels(labels)
        ax.invert_yaxis()
        ax.grid(axis="x", color=c.BORDER, alpha=0.45, linewidth=0.8)
        ax.grid(axis="y", visible=False)
    else:
        ax.bar(list(range(len(labels))), values, color=palette, width=0.62)
        ax.set_xticks(list(range(len(labels))))
        ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.grid(axis="x", visible=False)

    ax.set_title(title, fontsize=11, pad=12, loc="left")
    for index, value in enumerate(values):
        if value:
            if horizontal:
                ax.text(value, index, f" {value}", va="center", fontsize=9,
                        color=c.TEXT_MUTED)
            else:
                ax.text(index, value, f" {value}", ha="center", va="bottom",
                        fontsize=9, color=c.TEXT_MUTED)
    fig.tight_layout()
    return fig


def donut_chart(labels, values, title: str, colors=None,
                size: tuple[float, float] = (5.2, 2.9)):
    c = PALETTE.colors
    fig = plt.figure(figsize=size, dpi=100)
    ax = fig.add_subplot(111)
    fig.patch.set_facecolor(c.SURFACE)
    ax.set_facecolor(c.SURFACE)
    ax.title.set_color(c.TEXT)

    palette = colors or [c.ACCENT] * len(labels)
    wedges, _ = ax.pie(
        values, colors=palette, startangle=90, counterclock=False,
        wedgeprops={"width": 0.42, "edgecolor": c.SURFACE, "linewidth": 2},
    )
    ax.text(0, 0.08, str(sum(values)), ha="center", va="center",
            fontsize=18, color=c.TEXT, fontweight="bold")
    ax.text(0, -0.16, "cases", ha="center", va="center", fontsize=9,
            color=c.TEXT_MUTED)

    legend_labels = [f"{label}  {value}" for label, value in zip(labels, values)]
    ax.legend(wedges, legend_labels, loc="center left", bbox_to_anchor=(1.0, 0.5),
              frameon=False, fontsize=9, labelcolor=c.TEXT_MUTED)
    ax.set_title(title, fontsize=11, pad=12, loc="left")
    fig.tight_layout()
    return fig


def line_chart(labels, series: dict[str, list], title: str,
               size: tuple[float, float] = (5.2, 2.9)):
    c = PALETTE.colors
    fig = plt.figure(figsize=size, dpi=100)
    ax = fig.add_subplot(111)
    _style(fig, ax)

    x = range(len(labels))
    for name, values in series.items():
        ax.plot(list(x), values, marker="o", markersize=4, linewidth=2, label=name)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_title(title, fontsize=11, pad=12, loc="left")
    if series:
        ax.legend(frameon=False, fontsize=9, labelcolor=c.TEXT_MUTED)
    fig.tight_layout()
    return fig


def horizontal_bar_chart(labels, values, title: str, colors=None,
                          size: tuple[float, float] = (5.2, 2.9)):
    return bar_chart(labels, values, title, colors, horizontal=True, size=size)
