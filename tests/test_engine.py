"""End-to-end engine behaviour against a mocked Kalshi API and stub feeds."""

import json

import httpx
import pytest

from mentionbot.config import Settings
from mentionbot.engine import Engine
from mentionbot.jsonl_log import JsonlLogger
from mentionbot.kalshi.auth import KalshiSigner
from mentionbot.kalshi.book import OrderBook
from mentionbot.kalshi.rest import KalshiClient
from mentionbot.mentions import Word
from mentionbot.safety import KillSwitch
from mentionbot.terms import TermMarket
from mentionbot.transcribe import Segment
from tests.test_kalshi_api import KEY, KEY_ID, MockKalshi

pytestmark = pytest.mark.asyncio

TICKER = "KXT-TARIFF"


class StubJev:
    def __init__(self, prob=None, healthy=True):
        self.model = "jev-1.13.0"
        self.healthy = healthy
        self.last_error = None
        self.prob = prob
        self.calls = 0

    async def estimate(self, state, markets):
        self.calls += 1
        return None


class StubTranscriber:
    def __init__(self, connected=True):
        self.connected = connected
        self.on_segment = None

    def is_stale(self, _s, now=None):
        return not self.connected


class StubWS:
    def __init__(self, books):
        self._books = books
        self.connected = True

    def book(self, ticker):
        return self._books.setdefault(ticker, OrderBook(ticker))


class StubAudio:
    connected = True


def make_engine(tmp_path, mock, *, jev=None, books=None, **settings_kw):
    settings = Settings()
    for k, v in settings_kw.items():
        setattr(settings, k, v)
    settings.validate()

    http = httpx.AsyncClient(transport=httpx.MockTransport(mock.handler))
    client = KalshiClient(KalshiSigner(KEY_ID, KEY), client=http)

    market = TermMarket(
        ticker=TICKER, title="Tariff", variants=["tariff"], threshold=1,
        rules_primary="Counts if said.",
    )
    books = books if books is not None else {}
    books.setdefault(TICKER, OrderBook(TICKER)).apply_snapshot([[40, 50]], [[55, 50]])

    engine = Engine(
        settings=settings,
        client=client,
        markets=[market],
        flagged=[],
        event_ticker="KXEVENT",
        event_description="test event",
        duration_minutes=60,
        jev=jev or StubJev(),
        transcriber=StubTranscriber(),
        ws=StubWS(books),
        kill=KillSwitch(tmp_path),
        logger=JsonlLogger(tmp_path / "logs"),
        audio_connected=StubAudio(),
    )
    return engine, client


def seg(text: str, confidence: float = 0.99) -> Segment:
    words = [Word(t, confidence, i * 300, i * 300 + 250) for i, t in enumerate(text.split())]
    return Segment(text=text, words=words, received_at=1000.0, turn_order=1)


def posted_orders(mock) -> list[dict]:
    return [
        json.loads(r.content)
        for r in mock.requests
        if r.method == "POST" and r.url.path.endswith("/portfolio/orders")
    ]


# -- transcript -> counting ------------------------------------------------
async def test_segment_updates_the_counter_and_logs(tmp_path):
    mock = MockKalshi()
    engine, client = make_engine(tmp_path, mock)
    try:
        engine.on_segment(seg("we will raise the tariff today"))
        rt = engine.runtimes[TICKER]
        assert rt.counter.count == 1 and rt.counter.resolved_yes
        body = (tmp_path / "logs" / "transcript.jsonl").read_text()
        assert "tariff" in body
    finally:
        await client.aclose()
        engine.log.close()


async def test_low_confidence_segment_does_not_resolve(tmp_path):
    mock = MockKalshi()
    engine, client = make_engine(tmp_path, mock)
    try:
        engine.on_segment(seg("we will raise the tariff today", confidence=0.4))
        assert engine.runtimes[TICKER].counter.count == 0
    finally:
        await client.aclose()
        engine.log.close()


# -- a detected mention drives a Yes buy -----------------------------------
async def test_mention_triggers_a_yes_buy_at_the_derived_ask(tmp_path):
    mock = MockKalshi()
    mock.queue(200, {"market_positions": []})   # reconcile
    mock.queue(200, {"fills": []})
    mock.queue(201, {"order": {"order_id": "o1"}})
    engine, client = make_engine(tmp_path, mock)
    try:
        engine.on_segment(seg("the tariff is going up"))
        await engine.cycle()
        orders = posted_orders(mock)
        assert len(orders) == 1
        assert orders[0]["side"] == "yes" and orders[0]["action"] == "buy"
        assert orders[0]["yes_price"] == 45  # 100 - best no bid 55
        assert engine.pending[TICKER].order_id == "o1"
    finally:
        await client.aclose()
        engine.log.close()


async def test_no_second_order_while_one_is_resting(tmp_path):
    mock = MockKalshi()
    mock.queue(200, {"market_positions": []})
    mock.queue(200, {"fills": []})
    mock.queue(201, {"order": {"order_id": "o1"}})
    engine, client = make_engine(tmp_path, mock)
    try:
        engine.on_segment(seg("the tariff is going up"))
        await engine.cycle()
        await engine.cycle()
        assert len(posted_orders(mock)) == 1
    finally:
        await client.aclose()
        engine.log.close()


async def test_no_entries_while_jev_is_down_and_nothing_is_said(tmp_path):
    mock = MockKalshi()
    mock.queue(200, {"market_positions": []})
    mock.queue(200, {"fills": []})
    engine, client = make_engine(tmp_path, mock, jev=StubJev(healthy=False))
    try:
        await engine.cycle()
        assert posted_orders(mock) == []
        assert not engine.gate.allowed
        assert "Jev unavailable" in engine.gate.summary
    finally:
        await client.aclose()
        engine.log.close()


# -- fills -----------------------------------------------------------------
async def test_ws_fill_updates_the_position_and_clears_pending(tmp_path):
    mock = MockKalshi()
    engine, client = make_engine(tmp_path, mock)
    try:
        engine.pending[TICKER] = type(
            "P", (), dict(order_id="o1", ticker=TICKER, kind="enter", side="yes",
                          action="buy", count=1, limit_cents=45, placed_at=0.0,
                          client_order_id="c"),
        )()
        await engine.on_fill({
            "market_ticker": TICKER, "side": "yes", "action": "buy",
            "count": 1, "price": 45, "fill_id": "f1",
        })
        pos = engine.portfolio.position(TICKER)
        assert pos.side == "yes" and pos.count == 1
        assert TICKER not in engine.pending
    finally:
        await client.aclose()
        engine.log.close()


async def test_duplicate_ws_fill_is_ignored(tmp_path):
    mock = MockKalshi()
    engine, client = make_engine(tmp_path, mock)
    try:
        fill = {"market_ticker": TICKER, "side": "yes", "action": "buy",
                "count": 1, "price": 45, "fill_id": "f1"}
        await engine.on_fill(fill)
        await engine.on_fill(dict(fill))
        assert engine.portfolio.position(TICKER).count == 1
    finally:
        await client.aclose()
        engine.log.close()


# -- order timeout ---------------------------------------------------------
async def test_unfilled_order_is_cancelled_after_the_timeout(tmp_path):
    mock = MockKalshi()
    mock.queue(200, {})  # the DELETE
    engine, client = make_engine(tmp_path, mock, order_timeout_s=0.0)
    try:
        engine.pending[TICKER] = type(
            "P", (), dict(order_id="o1", ticker=TICKER, kind="enter", side="yes",
                          action="buy", count=1, limit_cents=45, placed_at=0.0,
                          client_order_id="c"),
        )()
        await engine.expire_stale_orders()
        assert TICKER not in engine.pending
        assert any(r.method == "DELETE" for r in mock.requests)
    finally:
        await client.aclose()
        engine.log.close()


# -- kill switch -----------------------------------------------------------
async def test_kill_switch_level_one_cancels_and_blocks_entries(tmp_path):
    mock = MockKalshi()
    mock.queue(200, {"market_positions": []})
    mock.queue(200, {"fills": []})
    mock.queue(200, {"orders": []})  # cancel_all listing
    engine, client = make_engine(tmp_path, mock)
    try:
        engine.on_segment(seg("the tariff is going up"))
        engine.kill.trigger(1, "test")
        await engine.cycle()
        assert posted_orders(mock) == [], "no entries once the switch is engaged"
        assert "status=resting" in str(
            next(r for r in mock.requests if "orders" in str(r.url) and r.method == "GET").url
        )
    finally:
        await client.aclose()
        engine.log.close()


async def test_kill_switch_level_two_flattens_at_the_bid(tmp_path):
    mock = MockKalshi()
    mock.queue(200, {"market_positions": []})
    mock.queue(200, {"fills": []})
    mock.queue(200, {"orders": []})       # cancel_all
    mock.queue(201, {"order": {"order_id": "flat"}})
    engine, client = make_engine(tmp_path, mock)
    try:
        await engine.on_fill({"market_ticker": TICKER, "side": "yes", "action": "buy",
                              "count": 2, "price": 45, "fill_id": "f1"})
        engine.kill.trigger(2, "flatten")
        await engine.cycle()
        orders = posted_orders(mock)
        assert len(orders) == 1
        assert orders[0]["action"] == "sell" and orders[0]["side"] == "yes"
        assert orders[0]["yes_price"] == 40  # the bid
        assert orders[0]["count"] == 2
    finally:
        await client.aclose()
        engine.log.close()


# -- loss halt --------------------------------------------------------------
async def test_loss_halt_blocks_new_entries(tmp_path):
    mock = MockKalshi()
    mock.queue(200, {"market_positions": []})
    mock.queue(200, {"fills": []})
    engine, client = make_engine(tmp_path, mock, max_loss_per_event=0.01)
    try:
        # Buy high, mark against a much lower bid: an immediate large loss.
        await engine.on_fill({"market_ticker": TICKER, "side": "yes", "action": "buy",
                              "count": 5, "price": 90, "fill_id": "f1"})
        engine.on_segment(seg("the tariff is going up"))
        await engine.cycle()
        assert engine.loss_guard.halted
        assert "loss limit reached" in engine.gate.summary
    finally:
        await client.aclose()
        engine.log.close()


# -- event cap ---------------------------------------------------------------
async def test_event_dollar_cap_stops_further_entries(tmp_path):
    mock = MockKalshi()
    mock.queue(200, {"market_positions": []})
    mock.queue(200, {"fills": []})
    engine, client = make_engine(tmp_path, mock, max_dollars_per_event=0.10)
    try:
        engine.portfolio.gross_spend_cents = 10
        engine.on_segment(seg("the tariff is going up"))
        await engine.cycle()
        assert posted_orders(mock) == []
    finally:
        await client.aclose()
        engine.log.close()


# -- reconciliation ----------------------------------------------------------
async def test_reconcile_adopts_api_positions_and_replays_fills(tmp_path):
    mock = MockKalshi()
    mock.queue(200, {"market_positions": [{"ticker": TICKER, "position": -3}]})
    mock.queue(200, {"fills": [{"ticker": TICKER, "side": "no", "action": "buy",
                                "count": 3, "price": 30, "fill_id": "rest-1"}]})
    engine, client = make_engine(tmp_path, mock)
    try:
        await engine.reconcile()
        pos = engine.portfolio.position(TICKER)
        assert pos.side == "no"
        assert (tmp_path / "logs" / "fills.jsonl").exists()
    finally:
        await client.aclose()
        engine.log.close()


# -- dashboard rendering ----------------------------------------------------
async def test_render_builds_rows_for_every_market(tmp_path):
    """Exercise the real render path; a dashboard-only bug must not hide here."""
    captured = {}

    class CapturingDashboard:
        def update(self, status, table, footer=""):
            captured["status"] = status
            captured["table"] = table

    mock = MockKalshi()
    mock.queue(200, {"market_positions": []})
    mock.queue(200, {"fills": []})
    engine, client = make_engine(tmp_path, mock)
    try:
        engine.dashboard = CapturingDashboard()
        engine.flagged = [
            TermMarket(ticker="FLAG", title="Border", variants=["border"], threshold=1,
                       flagged_reason="rules mention compound words")
        ]
        engine.on_segment(seg("the tariff is going up"))
        await engine.cycle()
        table = captured["table"]
        # One traded market plus one excluded market.
        assert table.row_count == 2
        from rich.console import Console

        out = Console(width=200, force_terminal=False, record=True)
        out.print(captured["status"])
        out.print(table)
        text = out.export_text()
        assert "tariff" in text.lower()
        assert "EXCLUDED" in text
    finally:
        await client.aclose()
        engine.log.close()
