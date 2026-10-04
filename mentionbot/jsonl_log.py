"""Append-only JSONL logs for transcript, Jev calls, decisions, orders, fills."""

from __future__ import annotations

import contextlib
import json
import threading
import time
from pathlib import Path
from typing import Any

STREAMS = ("transcript", "jev", "decisions", "orders", "fills", "errors")


class JsonlLogger:
    """One directory of append-only JSONL streams, safe across threads."""

    def __init__(self, run_dir: str | Path):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._handles: dict[str, Any] = {}
        self._lock = threading.Lock()

    def write(self, stream: str, record: dict[str, Any]) -> None:
        payload = {"ts": time.time(), **record}
        line = json.dumps(payload, default=str, ensure_ascii=False)
        with self._lock:
            handle = self._handles.get(stream)
            if handle is None:
                handle = open(self.run_dir / f"{stream}.jsonl", "a", encoding="utf-8")  # noqa: SIM115
                self._handles[stream] = handle
            handle.write(line + "\n")
            handle.flush()

    def close(self) -> None:
        with self._lock:
            for handle in self._handles.values():
                with contextlib.suppress(OSError):
                    handle.close()
            self._handles.clear()

    def __enter__(self) -> JsonlLogger:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def new_run_dir(root: str | Path = "logs") -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    path = Path(root) / stamp
    path.mkdir(parents=True, exist_ok=True)
    return path
