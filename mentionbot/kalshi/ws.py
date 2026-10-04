"""Kalshi market-data WebSocket: live order books and fills.

Subscribes to ``orderbook_delta`` (snapshot + incremental updates) and ``fill``
(our own executions). Reconnects with backoff; on every reconnect the server
resends snapshots, so book state re-syncs itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

import websockets

from .auth import KalshiSigner
from .book import OrderBook

log = logging.getLogger(__name__)

PROD_WS = "wss://api.elections.kalshi.com/trade-api/ws/v2"
WS_SIGNING_PATH = "/trade-api/ws/v2"


class KalshiWebSocket:
    """Maintains live `OrderBook`s for a set of tickers."""

    def __init__(
        self,
        signer: KalshiSigner,
        tickers: list[str],
        *,
        url: str = PROD_WS,
        on_fill: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        subscribe_fills: bool = True,
    ):
        self.signer = signer
        self.tickers = list(tickers)
        self.url = url
        self.books: dict[str, OrderBook] = {t: OrderBook(t) for t in self.tickers}
        self.connected = False
        self._on_fill = on_fill
        self._subscribe_fills = subscribe_fills
        self._cmd_id = 0
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    # -- lifecycle -------------------------------------------------------
    def start(self) -> None:
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self._run_forever(), name="kalshi-ws")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.connected = False

    async def _run_forever(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            try:
                await self._session()
                attempt = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Kalshi WS disconnected (%s); reconnecting", exc)
            finally:
                self.connected = False
            if self._stop.is_set():
                return
            delay = min(2.0**attempt * 0.5, 15.0) + random.uniform(0, 0.5)
            attempt += 1
            await asyncio.sleep(delay)

    async def _session(self) -> None:
        headers = self.signer.headers("GET", WS_SIGNING_PATH)
        async with websockets.connect(
            self.url,
            additional_headers=headers,
            ping_interval=10,
            ping_timeout=10,
            max_queue=1024,
        ) as ws:
            await self._subscribe(ws)
            self.connected = True
            log.info("Kalshi WS connected (%d markets)", len(self.tickers))
            async for raw in ws:
                await self._handle(raw)

    async def _subscribe(self, ws) -> None:
        self._cmd_id += 1
        await ws.send(
            json.dumps(
                {
                    "id": self._cmd_id,
                    "cmd": "subscribe",
                    "params": {
                        "channels": ["orderbook_delta"],
                        "market_tickers": self.tickers,
                    },
                }
            )
        )
        if self._subscribe_fills:
            self._cmd_id += 1
            await ws.send(
                json.dumps(
                    {
                        "id": self._cmd_id,
                        "cmd": "subscribe",
                        "params": {"channels": ["fill"]},
                    }
                )
            )

    # -- message handling ------------------------------------------------
    async def _handle(self, raw: str | bytes) -> None:
        try:
            event = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            log.warning("Kalshi WS: undecodable frame")
            return

        etype = event.get("type")
        msg = event.get("msg") or {}

        if etype == "orderbook_snapshot":
            book = self._book_for(msg)
            if book is not None:
                book.apply_snapshot(msg.get("yes"), msg.get("no"), seq=event.get("seq"))
        elif etype == "orderbook_delta":
            book = self._book_for(msg)
            if book is not None:
                book.apply_delta(
                    int(msg["price"]),
                    int(msg["delta"]),
                    str(msg["side"]),
                    seq=event.get("seq"),
                )
        elif etype == "fill":
            if self._on_fill is not None:
                await self._on_fill(msg)
        elif etype == "error":
            log.error("Kalshi WS error: %s", msg)

    def _book_for(self, msg: dict[str, Any]) -> OrderBook | None:
        ticker = msg.get("market_ticker") or msg.get("ticker")
        if ticker is None:
            return None
        if ticker not in self.books:
            self.books[ticker] = OrderBook(ticker)
        return self.books[ticker]

    # -- accessors -------------------------------------------------------
    def set_fill_handler(
        self, handler: Callable[[dict[str, Any]], Awaitable[None]] | None
    ) -> None:
        """Register (or clear) the coroutine called for each of our fills."""
        self._on_fill = handler

    def book(self, ticker: str) -> OrderBook:
        return self.books.setdefault(ticker, OrderBook(ticker))

    def all_stale(self, stale_after_s: float) -> bool:
        return all(b.is_stale(stale_after_s) for b in self.books.values())
