from __future__ import annotations

from typing import Optional, Sequence, Tuple

from rich.console import Console
from rich.console import RenderableType
from rich.align import Align
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box


def header_panel(subtitle: str = "Smart Execution • AI Assisted") -> Panel:
    header = Table.grid(expand=True)
    header.add_column(justify="center")

    title = "[bold white]DARK[/] [bold white]BLACK[/] [bold bright_magenta]BOT[/]"
    header.add_row(Align.center(Text.from_markup(title)))
    header.add_row(Align.center(Text.from_markup(f"[bright_white]{subtitle}[/]")))

    return Panel(
        header,
        border_style="bright_cyan",
        box=box.HEAVY,
        style="on black",
        padding=(0, 1),
    )


def title_panel(
    title: str,
    subtitle: Optional[str] = None,
    *,
    border_style: str = "bright_cyan",
) -> Panel:
    grid = Table.grid(expand=True)
    grid.add_column(justify="center")
    grid.add_row(Text.from_markup(f"[bold white]{title}[/]", justify="center"))
    if subtitle:
        grid.add_row(Text.from_markup(f"[dim]{subtitle}[/]", justify="center"))

    return Panel(
        grid,
        border_style=border_style,
        box=box.HEAVY,
        style="on black",
        padding=(0, 1),
    )


def section(title: str, body: RenderableType, *, border_style: str = "bright_cyan") -> Panel:
    return Panel(
        body,
        title=f"[bold]{title}[/]",
        title_align="left",
        border_style=border_style,
        box=box.DOUBLE,
        padding=(1, 2),
        style="on black",
    )


def menu_table(
    title: str,
    items: Sequence[Tuple[str, str, str]],
    *,
    border_style: str = "bright_cyan",
    key_style: str = "bold bright_cyan",
    title_style: str = "bold white",
    desc_style: str = "dim",
) -> Panel:
    """Creates a dashboard-like menu panel.

    items: (key, label, description)
    """
    # Keep option numbers and text visually close.
    # Using ratios with expand=True pushes the label column far from the key.
    t = Table.grid(expand=True, padding=(0, 1))
    t.style = "on black"
    t.add_column(justify="left", width=4, no_wrap=True)
    t.add_column(justify="left", ratio=1)

    for key, label, desc in items:
        t.add_row(
            f"[{key_style}]{key}[/]",
            f"[{title_style}]{label}[/]\n[{desc_style}]{desc}[/]",
        )

    return section(title, t, border_style=border_style)


def info_kv(
    title: str,
    rows: Sequence[Tuple[str, str]],
    *,
    border_style: str = "bright_magenta",
) -> Panel:
    t = Table.grid(expand=True)
    t.style = "on black"
    t.add_column(ratio=1)
    t.add_column(justify="right")

    for k, v in rows:
        t.add_row(f"[dim]{k}[/]", v)

    return section(title, t, border_style=border_style)


def print_panel(console: Console, panel: Panel) -> None:
    console.print(panel, style="on black")
