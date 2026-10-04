"""The trading loop: transcript -> counts -> Jev -> orders."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from dataclasses import dataclass, field

from .config import Settings
from .dashboard import Dashboard, Row, build_status, build_table
from .jev import JevClient, JevState
from .jsonl_log import JsonlLogger
from .kalshi.book import OrderBook
from .kalshi.rest import KalshiClient, KalshiError
from .kalshi.ws import KalshiWebSocket
from .mentions import TermCounter
from .portfolio import Portfolio
from .safety import EntryGate, KillSwitch, LossGuard, evaluate_entry_gate
from .strategy import Action, Quote, evaluate, flatten_action
from .terms import TermMarket
from .transcribe import Segment, Transcriber, TranscriptWindow

log = logging.getLogger(__name__)

RECONCILE_INTERVAL_S = 30.0
CYCLE_INTERVAL_S = 0.5


@dataclass
class PendingOrder:
    order_id: str
    ticker: str
    kind: str  # "enter" | "exit"
    side: str
    action: str
    count: int
    limit_cents: int
    placed_at: float
    client_order_id: str


@dataclass
class MarketRuntime:
    """Per-market live state."""

    market: TermMarket
    counter: TermCounter
    jev_p: int | None = None
    quote: Quote = field(default_factory=Quote)
    note: str = ""


class Engine:
    """Owns every moving part for one event."""

    def __init__(
        self,
        *,
        settings: Settings,
        client: KalshiClient,
        markets: list[TermMarket],
        flagged: list[TermMarket],
        event_ticker: str,
        event_description: str,
        duration_minutes: float,
        jev: JevClient,
        transcriber: Transcriber,
        ws: KalshiWebSocket,
        kill: KillSwitch,
        logger: JsonlLogger,
        audio_connected: object,
        dashboard: Dashboard | None = None,
    ):
        self.settings = settings
        self.client = client
        self.event_ticker = event_ticker
        self.event_description = event_description
        self.duration_minutes = duration_minutes
        self.jev = jev
        self.transcriber = transcriber
        self.ws = ws
        self.kill = kill
        self.log = logger
        self.dashboard = dashboard
        self._audio = audio_connected

        self.runtimes: dict[str, MarketRuntime] = {
            m.ticker: MarketRuntime(
                market=m,
                counter=TermCounter(
                    variants=m.variants,
                    threshold=m.threshold,
                    min_confidence=settings.min_word_confidence,
                ),
            )
            for m in markets
        }
        self.flagged = flagged
        self.portfolio = Portfolio()
        self.window = TranscriptWindow(window_s=settings.transcript_window_s)
        self.loss_guard = LossGuard(max_loss_cents=settings.max_loss_cents)
        self.pending: dict[str, PendingOrder] = {}  # ticker -> order
        self.gate = EntryGate(False, ["starting up"])

        self.started_at = time.monotonic()
        self._last_jev = 0.0
        self._last_reconcile = 0.0
        self._flattened = False
        self._cancelled_for_kill = False
        self._stopping = False

    # -- clocks ----------------------------------------------------------
    @property
    def elapsed_minutes(self) -> float:
        return (time.monotonic() - self.started_at) / 60.0

    @property
    def remaining_minutes(self) -> float:
        return max(0.0, self.duration_minutes - self.elapsed_minutes)

    def book(self, ticker: str) -> OrderBook:
        return self.ws.book(ticker)

    @property
    def books(self) -> dict[str, OrderBook]:
        return {t: self.ws.book(t) for t in self.runtimes}

    # -- transcript ------------------------------------------------------
    def on_segment(self, segment: Segment) -> None:
        """Called from the transcriber for every finalized turn."""
        self.window.add(segment)
        self.log.write(
            "transcript",
            {
                "turn": segment.turn_order,
                "text": segment.text,
                "words": [
                    {"t": w.text, "c": round(w.confidence, 3), "s": w.start_ms, "e": w.end_ms}
                    for w in segment.words
                ],
            },
        )
        for rt in self.runtimes.values():
            if rt.counter.resolved_yes:
                continue
            hits = rt.counter.add_segment(segment.words)
            for hit in hits:
                log.info(
                    "MENTION %s: '%s' (%d/%d)",
                    rt.market.label,
                    hit.matched_text,
                    rt.counter.count,
                    rt.counter.threshold,
                )
                self.log.write(
                    "decisions",
                    {
                        "kind": "mention",
                        "ticker": rt.market.ticker,
                        "term": rt.market.label,
                        "variant": hit.variant,
                        "matched": hit.matched_text,
                        "count": rt.counter.count,
                        "threshold": rt.counter.threshold,
                        "confidence": round(hit.min_confidence, 3),
                        "resolved_yes": rt.counter.resolved_yes,
                    },
                )

    # -- fills -----------------------------------------------------------
    async def on_fill(self, msg: dict) -> None:
        ticker = msg.get("market_ticker") or msg.get("ticker")
        if not ticker:
            return
        side = (msg.get("side") or "").lower()
        action = (msg.get("action") or "").lower()
        count = int(msg.get("count") or 0)
        price = msg.get("price")
        if price is None:
            price = msg.get("yes_price") if side == "yes" else msg.get("no_price")
        if not (ticker and side and action and count and price is not None):
            return

        applied = self.portfolio.apply_fill(
            ticker=ticker,
            side=side,
            action=action,
            count=count,
            price_cents=int(price),
            fill_id=msg.get("fill_id") or msg.get("trade_id"),
        )
        if applied:
            self.log.write("fills", {"source": "ws", **msg})
            log.info("FILL %s %s %s x%d @ %sc", ticker, action, side, count, price)
        # A fill may complete the pending order for this ticker.
        pend = self.pending.get(ticker)
        if pend and count >= pend.count:
            self.pending.pop(ticker, None)

    # -- Jev -------------------------------------------------------------
    async def refresh_jev(self) -> None:
        pairs = [
            (rt.market, rt.counter.count)
            for rt in self.runtimes.values()
            if not rt.counter.resolved_yes and rt.market.tradable
        ]
        if not pairs:
            return
        state = JevState(
            event_description=self.event_description,
            elapsed_minutes=self.elapsed_minutes,
            remaining_minutes=self.remaining_minutes,
            transcript_window=self.window.text(),
            terms=[
                {
                    "term": m.label,
                    "variants": m.variants,
                    "threshold": m.threshold,
                    "said_so_far": count,
                    "opening_price_cents": m.opening_price,
                }
                for m, count in pairs
            ],
        )
        request_id = uuid.uuid4().hex[:12]
        self.log.write(
            "jev",
            {
                "dir": "request",
                "id": request_id,
                "model": self.jev.model,
                "state": state.to_payload(),
                "tickers": [m.ticker for m, _ in pairs],
            },
        )
        result = await self.jev.estimate(state, pairs)
        if result is None:
            self.log.write(
                "jev",
                {"dir": "error", "id": request_id, "error": self.jev.last_error},
            )
            return
        self.log.write(
            "jev",
            {
                "dir": "response",
                "id": request_id,
                "model": result.model,
                "latency_s": round(result.latency_s, 3),
                "probabilities": result.probabilities,
                "usage": result.raw.get("usage"),
            },
        )
        for ticker, prob in result.probabilities.items():
            rt = self.runtimes.get(ticker)
            if rt is not None:
                rt.jev_p = prob

    # -- orders ----------------------------------------------------------
    async def place(self, action: Action) -> None:
        ticker = action.ticker
        if ticker in self.pending:
            return  # never stack orders on one market
        client_order_id = f"mb-{uuid.uuid4().hex[:20]}"
        self.log.write(
            "decisions",
            {
                "kind": action.kind,
                "ticker": ticker,
                "side": action.side,
                "action": action.action,
                "count": action.count,
                "limit_cents": action.limit_cents,
                "edge_cents": action.edge_cents,
                "reason": action.reason,
            },
        )
        try:
            order = await self.client.create_order(
                ticker=ticker,
                side=action.side,
                action=action.action,
                count=action.count,
                price_cents=action.limit_cents,
                client_order_id=client_order_id,
            )
        except (KalshiError, ValueError) as exc:
            log.error("order rejected for %s: %s", ticker, exc)
            self.log.write(
                "orders",
                {"status": "rejected", "ticker": ticker, "error": str(exc)},
            )
            return

        order_id = order.get("order_id", "")
        self.log.write("orders", {"status": "placed", "ticker": ticker, **order})
        log.info(
            "ORDER %s %s %s x%d @ %sc (%s)",
            ticker, action.action, action.side, action.count,
            action.limit_cents, action.reason,
        )
        if order_id:
            self.pending[ticker] = PendingOrder(
                order_id=order_id,
                ticker=ticker,
                kind=action.kind,
                side=action.side,
                action=action.action,
                count=action.count,
                limit_cents=action.limit_cents,
                placed_at=time.monotonic(),
                client_order_id=client_order_id,
            )

    async def expire_stale_orders(self) -> None:
        """Cancel orders that have rested past ``order_timeout_s``.

        Entry orders are dropped outright. Exit orders are also cancelled so
        the next cycle can re-price them against the current bid rather than
        leaving a stale order resting where the market has moved away.
        """
        now = time.monotonic()
        for ticker, pend in list(self.pending.items()):
            if now - pend.placed_at < self.settings.order_timeout_s:
                continue
            self.pending.pop(ticker, None)
            try:
                await self.client.cancel_order(pend.order_id)
                self.log.write(
                    "orders",
                    {"status": "cancelled", "ticker": ticker, "order_id": pend.order_id,
                     "reason": "order_timeout_s"},
                )
                log.info("cancelled stale %s order on %s", pend.kind, ticker)
            except KalshiError as exc:
                # Most likely it filled between our check and the cancel.
                log.info("cancel of %s returned %s", pend.order_id, exc)

    async def cancel_everything(self) -> None:
        self.pending.clear()
        try:
            cancelled = await self.client.cancel_all(set(self.runtimes))
            self.log.write("orders", {"status": "cancel_all", "order_ids": cancelled})
            log.warning("cancelled %d resting order(s)", len(cancelled))
        except KalshiError as exc:
            log.error("cancel-all failed: %s", exc)

    async def flatten_all(self) -> None:
        for ticker in self.runtimes:
            pos = self.portfolio.position(ticker)
            if pos.is_flat:
                continue
            action = flatten_action(ticker, pos, self.book(ticker))
            if action is not None:
                await self.place(action)
        self._flattened = True

    # -- reconciliation ---------------------------------------------------
    async def reconcile(self) -> None:
        try:
            positions = await self.client.get_positions(event_ticker=self.event_ticker)
        except KalshiError as exc:
            log.error("position reconcile failed: %s", exc)
            return
        drifted = self.portfolio.reconcile_positions(positions)
        if drifted:
            log.warning("position drift corrected from API: %s", ", ".join(drifted))
            self.log.write("decisions", {"kind": "reconcile", "drifted": drifted})

        try:
            fills = await self.client.get_fills(limit=200)
        except KalshiError as exc:
            log.error("fill reconcile failed: %s", exc)
            return
        for fill in fills:
            ticker = fill.get("ticker") or fill.get("market_ticker")
            if ticker not in self.runtimes:
                continue
            side = (fill.get("side") or "").lower()
            price = fill.get("price")
            if price is None:
                price = fill.get("yes_price") if side == "yes" else fill.get("no_price")
            if price is None:
                continue
            # apply_fill de-duplicates on fill_id, so replaying is safe.
            if self.portfolio.apply_fill(
                ticker=ticker,
                side=side,
                action=(fill.get("action") or "").lower(),
                count=int(fill.get("count") or 0),
                price_cents=int(price),
                fill_id=fill.get("fill_id"),
            ):
                self.log.write("fills", {"source": "rest", **fill})

    # -- the cycle ---------------------------------------------------------
    def compute_gate(self) -> EntryGate:
        books_stale = all(
            self.book(t).is_stale(self.settings.stale_data_s) for t in self.runtimes
        ) if self.runtimes else True
        return evaluate_entry_gate(
            kill_engaged=self.kill.engaged,
            loss_halted=self.loss_guard.halted,
            jev_healthy=self.jev.healthy,
            book_stale=books_stale,
            transcript_stale=self.transcriber.is_stale(self.settings.stale_data_s),
            audio_connected=bool(getattr(self._audio, "connected", False)),
            market_data_connected=self.ws.connected,
        )

    async def cycle(self) -> None:
        now = time.monotonic()

        if now - self._last_reconcile >= RECONCILE_INTERVAL_S:
            self._last_reconcile = now
            await self.reconcile()

        if now - self._last_jev >= self.settings.jev_interval_s:
            self._last_jev = now
            await self.refresh_jev()

        await self.expire_stale_orders()

        # Kill switch: cancel once at level 1, flatten once at level 2.
        if self.kill.engaged and not self._cancelled_for_kill:
            self._cancelled_for_kill = True
            await self.cancel_everything()
        if self.kill.flatten and not self._flattened:
            await self.flatten_all()

        total_pnl = self.portfolio.total_pnl_cents(self.books)
        self.loss_guard.update(total_pnl)
        self.gate = self.compute_gate()

        event_over = self.remaining_minutes <= 0
        for ticker, rt in self.runtimes.items():
            if ticker in self.pending:
                rt.note = "order resting"
                continue
            action, quote = evaluate(
                market=rt.market,
                book=self.book(ticker),
                position=self.portfolio.position(ticker),
                settings=self.settings,
                jev_p=rt.jev_p,
                resolved_yes=rt.counter.resolved_yes,
                mention_detected=rt.counter.count > 0,
                spend_cents=self.portfolio.gross_spend_cents,
                entries_allowed=self.gate.allowed and not event_over,
            )
            rt.quote = quote
            rt.note = self._note_for(rt, action)
            if action is not None:
                await self.place(action)

        self.render()

    def _note_for(self, rt: MarketRuntime, action: Action | None) -> str:
        if rt.market.flagged_reason:
            return f"EXCLUDED: {rt.market.flagged_reason}"
        if rt.counter.resolved_yes:
            return "said: holding to settlement"
        if action is not None:
            return action.reason
        if not self.gate.allowed:
            return self.gate.summary
        return ""

    # -- display ------------------------------------------------------------
    def render(self) -> None:
        if self.dashboard is None:
            return
        rows: list[Row] = []
        for ticker, rt in self.runtimes.items():
            pos = self.portfolio.position(ticker)
            book = self.book(ticker)
            q = rt.quote
            gap = q.entry_edge_yes if pos.is_flat else q.exit_edge
            rows.append(
                Row(
                    term=rt.market.label,
                    count=rt.counter.count,
                    threshold=rt.counter.threshold,
                    jev_p=q.fair_cents if q.fair_cents is not None else rt.jev_p,
                    yes_bid=q.yes_bid,
                    yes_ask=q.yes_ask,
                    gap=gap,
                    position=(
                        "-" if pos.is_flat else f"{(pos.side or '').upper()} {pos.count}"
                    ),
                    pnl_cents=pos.realized_cents + pos.unrealized_cents(book),
                    note=rt.note,
                )
            )
        for m in self.flagged:
            rows.append(
                Row(m.label, 0, m.threshold, None, None, None, None, "-", 0,
                    f"EXCLUDED: {m.flagged_reason}")
            )
        status = build_status(
            event_ticker=self.event_ticker,
            elapsed_min=self.elapsed_minutes,
            remaining_min=self.remaining_minutes,
            realized_cents=self.portfolio.realized_cents(),
            unrealized_cents=self.portfolio.unrealized_cents(self.books),
            spend_cents=self.portfolio.gross_spend_cents,
            cap_cents=self.settings.max_cents_per_event,
            gate_summary=self.gate.summary,
            kill_level=self.kill.level,
            connections={
                "kalshi": self.ws.connected,
                "audio": bool(getattr(self._audio, "connected", False)),
                "stt": self.transcriber.connected,
                "jev": self.jev.healthy,
            },
        )
        self.dashboard.update(
            status, build_table(rows), "keys: [k] stop entries + cancel  [f] flatten at bid"
        )

    # -- main loop ----------------------------------------------------------
    async def run(self) -> None:
        log.info(
            "trading %d market(s) on %s for %.0f minutes",
            len(self.runtimes), self.event_ticker, self.duration_minutes,
        )
        try:
            while not self._stopping:
                await self.cycle()
                # Once the event is over and nothing is open, there is no work left.
                if self.remaining_minutes <= 0 and not self.pending:
                    log.info("scheduled duration reached; stopping entries")
                    break
                if self.kill.flatten and self._flattened and not self.pending:
                    log.info("kill switch flatten complete; stopping")
                    break
                await asyncio.sleep(CYCLE_INTERVAL_S)
        except asyncio.CancelledError:
            raise
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        self._stopping = True
        with contextlib.suppress(Exception):
            await self.cancel_everything()
        with contextlib.suppress(Exception):
            await self.reconcile()
        self.log.write(
            "decisions",
            {
                "kind": "shutdown",
                "realized_cents": self.portfolio.realized_cents(),
                "unrealized_cents": self.portfolio.unrealized_cents(self.books),
                "spend_cents": self.portfolio.gross_spend_cents,
                "positions": {
                    t: {"side": p.side, "count": p.count, "cost_cents": p.cost_cents}
                    for t, p in self.portfolio.positions.items()
                    if not p.is_flat
                },
            },
        )
