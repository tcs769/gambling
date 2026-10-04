"""Kill switch, loss halt, and the gate that decides if new entries are allowed.

The kill switch escalates in two stages, matching the operating rule "stop
first, flatten only if you mean it":

    level 1 - cancel every open order and stop opening new positions
    level 2 - additionally sell every open position at the bid

Either stage can be triggered by a keypress or by the ``STOP`` file in the
project folder. Creating ``STOP`` arms level 1; pressing a key again, or
writing ``FLATTEN`` into ``STOP``, escalates to level 2.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
import termios
import tty
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

STOP_FILE = "STOP"
FLATTEN_KEYS = {"f", "F"}
STOP_KEYS = {"k", "K", "s", "S", "\x03"}  # includes Ctrl-C


class KillSwitch:
    """Escalating stop control, fed by a STOP file and (optionally) the keyboard."""

    def __init__(self, project_dir: str | Path = ".", poll_s: float = 0.25):
        self.path = Path(project_dir) / STOP_FILE
        self.poll_s = poll_s
        self.level = 0
        self.reason: str | None = None
        self._tasks: list[asyncio.Task] = []
        self._saved_tty: tuple | None = None

    # -- triggers --------------------------------------------------------
    def trigger(self, level: int, reason: str) -> None:
        """Raise the switch to at least ``level``."""
        level = max(1, min(2, level))
        if level > self.level:
            self.level = level
            self.reason = reason
            log.warning("KILL SWITCH level %d: %s", level, reason)

    def escalate(self, reason: str) -> None:
        self.trigger(self.level + 1, reason)

    @property
    def engaged(self) -> bool:
        return self.level >= 1

    @property
    def flatten(self) -> bool:
        return self.level >= 2

    # -- watchers --------------------------------------------------------
    def start(self, *, keyboard: bool = True) -> None:
        self._tasks.append(asyncio.create_task(self._watch_file(), name="stopfile"))
        if keyboard and sys.stdin.isatty():
            self._tasks.append(asyncio.create_task(self._watch_keys(), name="keys"))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        self._restore_tty()

    async def _watch_file(self) -> None:
        seen = False
        while True:
            try:
                if self.path.exists():
                    body = ""
                    with contextlib.suppress(OSError):
                        body = self.path.read_text(errors="replace")
                    if "FLATTEN" in body.upper():
                        self.trigger(2, f"{STOP_FILE} file requests FLATTEN")
                    elif not seen:
                        seen = True
                        self.trigger(1, f"{STOP_FILE} file created")
                else:
                    seen = False
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # a watcher must never kill the engine
                log.error("STOP-file watcher error: %s", exc)
            await asyncio.sleep(self.poll_s)

    async def _watch_keys(self) -> None:
        loop = asyncio.get_running_loop()
        fd = sys.stdin.fileno()
        try:
            self._saved_tty = termios.tcgetattr(fd)
            tty.setcbreak(fd)
        except (termios.error, OSError):
            log.info("keyboard kill switch unavailable (not a tty)")
            return

        queue: asyncio.Queue[str] = asyncio.Queue()

        def _on_readable() -> None:
            try:
                ch = sys.stdin.read(1)
            except (OSError, ValueError):
                return
            if ch:
                queue.put_nowait(ch)

        loop.add_reader(fd, _on_readable)
        try:
            while True:
                ch = await queue.get()
                if ch in FLATTEN_KEYS:
                    self.trigger(2, "'f' pressed: flatten all positions")
                elif ch in STOP_KEYS:
                    self.escalate("kill key pressed")
        except asyncio.CancelledError:
            raise
        finally:
            with contextlib.suppress(Exception):
                loop.remove_reader(fd)
            self._restore_tty()

    def _restore_tty(self) -> None:
        if self._saved_tty is not None:
            with contextlib.suppress(Exception):
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._saved_tty)
            self._saved_tty = None


@dataclass
class EntryGate:
    """Why new entries are, or are not, currently allowed."""

    allowed: bool
    reasons: list[str]

    @property
    def summary(self) -> str:
        return "OK" if self.allowed else "; ".join(self.reasons)


def evaluate_entry_gate(
    *,
    kill_engaged: bool,
    loss_halted: bool,
    jev_healthy: bool,
    book_stale: bool,
    transcript_stale: bool,
    audio_connected: bool,
    market_data_connected: bool,
) -> EntryGate:
    """Collect every reason new entries should be blocked this cycle.

    Exits are never gated by this: a position we want out of must always be
    closable.
    """
    reasons: list[str] = []
    if kill_engaged:
        reasons.append("kill switch engaged")
    if loss_halted:
        reasons.append("loss limit reached")
    if not jev_healthy:
        reasons.append("Jev unavailable")
    if book_stale:
        reasons.append("orderbook data stale")
    if transcript_stale:
        reasons.append("transcript data stale")
    if not audio_connected:
        reasons.append("audio stream down")
    if not market_data_connected:
        reasons.append("Kalshi market data down")
    return EntryGate(allowed=not reasons, reasons=reasons)


@dataclass
class LossGuard:
    """Halts entries once the event's loss passes the configured limit."""

    max_loss_cents: int
    halted: bool = False
    worst_cents: int = 0

    def update(self, total_pnl_cents: int) -> bool:
        """Feed the latest realized+unrealized P&L. Returns ``halted``."""
        self.worst_cents = min(self.worst_cents, total_pnl_cents)
        if total_pnl_cents <= -self.max_loss_cents:
            if not self.halted:
                log.warning(
                    "LOSS HALT: P&L %dc breached limit of -%dc",
                    total_pnl_cents,
                    self.max_loss_cents,
                )
            self.halted = True
        return self.halted
