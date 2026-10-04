"""Terminal dashboard."""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


@dataclass
class Row:
    """One market's line on the dashboard."""

    term: str
    count: int
    threshold: int
    jev_p: int | None
    yes_bid: int | None
    yes_ask: int | None
    gap: int | None
    position: str
    pnl_cents: int
    note: str = ""


def _cents(value: int | None) -> str:
    return "-" if value is None else str(value)


def _money(cents: int) -> Text:
    style = "green" if cents > 0 else ("red" if cents < 0 else "dim")
    return Text(f"{cents / 100:+.2f}", style=style)


def build_table(rows: list[Row]) -> Table:
    table = Table(expand=True, header_style="bold", pad_edge=False)
    table.add_column("Term", ratio=3, no_wrap=True)
    table.add_column("Said", justify="right", width=7)
    table.add_column("Jev", justify="right", width=5)
    table.add_column("Yes bid/ask", justify="right", width=12)
    table.add_column("Gap", justify="right", width=6)
    table.add_column("Position", width=12)
    table.add_column("P&L $", justify="right", width=8)
    table.add_column("Note", ratio=2)

    for r in rows:
        resolved = r.count >= r.threshold
        said = Text(f"{r.count}/{r.threshold}", style="bold green" if resolved else "")
        gap_text = Text("-")
        if r.gap is not None:
            gap_style = "green" if r.gap > 0 else "dim"
            gap_text = Text(f"{r.gap:+d}", style=gap_style)
        table.add_row(
            Text(r.term, style="bold" if resolved else ""),
            said,
            _cents(r.jev_p),
            f"{_cents(r.yes_bid)}/{_cents(r.yes_ask)}",
            gap_text,
            Text(r.position, style="cyan" if r.position != "-" else "dim"),
            _money(r.pnl_cents),
            Text(r.note, style="yellow" if r.note else "dim"),
        )
    return table


def build_status(
    *,
    event_ticker: str,
    elapsed_min: float,
    remaining_min: float,
    realized_cents: int,
    unrealized_cents: int,
    spend_cents: int,
    cap_cents: int,
    gate_summary: str,
    kill_level: int,
    connections: dict[str, bool],
) -> Panel:
    conn = "  ".join(
        f"[{'green' if ok else 'red'}]{'o' if ok else 'x'} {name}[/]"
        for name, ok in connections.items()
    )
    total = realized_cents + unrealized_cents
    gate_style = "green" if gate_summary == "OK" else "yellow"
    kill_line = (
        f"[bold red]KILL SWITCH LEVEL {kill_level}[/]\n" if kill_level else ""
    )
    body = (
        f"{kill_line}"
        f"[bold]{event_ticker}[/]   "
        f"elapsed [bold]{elapsed_min:.1f}m[/]  remaining [bold]{remaining_min:.1f}m[/]\n"
        f"P&L realized [bold]{realized_cents / 100:+.2f}[/]  "
        f"unrealized [bold]{unrealized_cents / 100:+.2f}[/]  "
        f"total [bold]{total / 100:+.2f}[/]\n"
        f"spent [bold]${spend_cents / 100:.2f}[/] of [bold]${cap_cents / 100:.2f}[/]   "
        f"entries [{gate_style}]{gate_summary}[/]\n"
        f"{conn}"
    )
    return Panel(body, title="mention-bot (LIVE)", border_style="red")


class Dashboard:
    """Wraps a `rich` Live display; a no-op when output is not a terminal."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._live: Live | None = None

    def __enter__(self) -> Dashboard:
        if self.enabled:
            self._live = Live(auto_refresh=False, screen=False)
            self._live.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        if self._live is not None:
            self._live.__exit__(*exc)
            self._live = None

    def update(self, status: Panel, table: Table, footer: str = "") -> None:
        if self._live is None:
            return
        parts = [status, table]
        if footer:
            parts.append(Text(footer, style="dim"))
        self._live.update(Group(*parts), refresh=True)
