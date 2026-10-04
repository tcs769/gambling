"""Kalshi REST client against a mocked API."""

import base64
import json

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from mentionbot.kalshi.auth import KalshiSigner
from mentionbot.kalshi.rest import KalshiClient, KalshiError, TokenBucket

pytestmark = pytest.mark.asyncio

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KEY_ID = "test-key-id"


class MockKalshi:
    """Records requests and replays canned responses."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.responses: list[httpx.Response] = []
        self.orders: list[dict] = []

    def queue(self, status: int, payload: dict | None = None):
        self.responses.append(
            httpx.Response(status, json=payload if payload is not None else {})
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.responses:
            return self.responses.pop(0)
        return httpx.Response(200, json={})


def make_client(mock: MockKalshi, **kw) -> KalshiClient:
    transport = httpx.MockTransport(mock.handler)
    http = httpx.AsyncClient(transport=transport)
    signer = KalshiSigner(KEY_ID, KEY)
    return KalshiClient(signer, client=http, **kw)


def verify(request: httpx.Request) -> bool:
    """Check the auth headers on a captured request."""
    ts = request.headers["KALSHI-ACCESS-TIMESTAMP"]
    message = ts + request.method.upper() + request.url.path
    try:
        KEY.public_key().verify(
            base64.b64decode(request.headers["KALSHI-ACCESS-SIGNATURE"]),
            message.encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


# -- signing on the wire ---------------------------------------------------
async def test_every_request_is_signed_over_the_full_path():
    mock = MockKalshi()
    mock.queue(200, {"markets": []})
    async with make_client(mock) as c:
        await c.get_markets("KXEVENT")
    req = mock.requests[0]
    assert req.headers["KALSHI-ACCESS-KEY"] == KEY_ID
    assert req.url.path == "/trade-api/v2/markets"
    assert "event_ticker=KXEVENT" in str(req.url)
    assert verify(req), "signature must cover /trade-api/v2/markets without the query"


async def test_base_path_is_included_in_the_signature():
    mock = MockKalshi()
    mock.queue(200, {"orderbook": {}})
    async with make_client(mock) as c:
        await c.get_orderbook("T")
    assert mock.requests[0].url.path == "/trade-api/v2/markets/T/orderbook"
    assert verify(mock.requests[0])


# -- market data -----------------------------------------------------------
async def test_markets_pagination_is_followed():
    mock = MockKalshi()
    mock.queue(200, {"markets": [{"ticker": "A"}], "cursor": "next"})
    mock.queue(200, {"markets": [{"ticker": "B"}], "cursor": ""})
    async with make_client(mock) as c:
        markets = await c.get_markets("KXEVENT")
    assert [m["ticker"] for m in markets] == ["A", "B"]
    assert "cursor=next" in str(mock.requests[1].url)


async def test_none_params_are_dropped():
    mock = MockKalshi()
    mock.queue(200, {"markets": []})
    async with make_client(mock) as c:
        await c.get_markets("KXEVENT")
    assert "status=" not in str(mock.requests[0].url)


# -- order placement -------------------------------------------------------
async def test_buy_yes_sends_yes_price():
    mock = MockKalshi()
    mock.queue(201, {"order": {"order_id": "o1"}})
    async with make_client(mock) as c:
        order = await c.create_order(
            ticker="T", side="yes", action="buy", count=2,
            price_cents=45, client_order_id="cid-1",
        )
    body = json.loads(mock.requests[0].content)
    assert body["side"] == "yes" and body["action"] == "buy"
    assert body["yes_price"] == 45 and "no_price" not in body
    assert body["type"] == "limit" and body["count"] == 2
    assert body["client_order_id"] == "cid-1"
    assert order["order_id"] == "o1"


async def test_buy_no_sends_no_price():
    mock = MockKalshi()
    mock.queue(201, {"order": {"order_id": "o2"}})
    async with make_client(mock) as c:
        await c.create_order(
            ticker="T", side="no", action="buy", count=1,
            price_cents=60, client_order_id="cid-2",
        )
    body = json.loads(mock.requests[0].content)
    assert body["no_price"] == 60 and "yes_price" not in body


async def test_sell_yes_sends_yes_price():
    mock = MockKalshi()
    mock.queue(201, {"order": {"order_id": "o3"}})
    async with make_client(mock) as c:
        await c.create_order(
            ticker="T", side="yes", action="sell", count=3,
            price_cents=40, client_order_id="cid-3",
        )
    body = json.loads(mock.requests[0].content)
    assert body["action"] == "sell" and body["yes_price"] == 40


async def test_orders_are_always_limit_orders():
    mock = MockKalshi()
    mock.queue(201, {"order": {"order_id": "o"}})
    async with make_client(mock) as c:
        await c.create_order(ticker="T", side="yes", action="buy", count=1,
                             price_cents=10, client_order_id="c")
    assert json.loads(mock.requests[0].content)["type"] == "limit"


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(side="maybe", action="buy", count=1, price_cents=10),
        dict(side="yes", action="hold", count=1, price_cents=10),
        dict(side="yes", action="buy", count=0, price_cents=10),
        dict(side="yes", action="buy", count=1, price_cents=0),
        dict(side="yes", action="buy", count=1, price_cents=100),
    ],
)
async def test_invalid_orders_are_rejected_before_the_network(kwargs):
    mock = MockKalshi()
    async with make_client(mock) as c:
        with pytest.raises(ValueError):
            await c.create_order(ticker="T", client_order_id="c", **kwargs)
    assert mock.requests == [], "no request should reach the API"


# -- cancels ---------------------------------------------------------------
async def test_cancel_order_uses_delete():
    mock = MockKalshi()
    mock.queue(200, {})
    async with make_client(mock) as c:
        await c.cancel_order("abc")
    req = mock.requests[0]
    assert req.method == "DELETE"
    assert req.url.path == "/trade-api/v2/portfolio/orders/abc"
    assert verify(req)


async def test_cancel_all_cancels_every_resting_order_for_our_tickers():
    mock = MockKalshi()
    mock.queue(200, {"orders": [
        {"order_id": "o1", "ticker": "A"},
        {"order_id": "o2", "ticker": "B"},
        {"order_id": "o3", "ticker": "OTHER"},
    ]})
    mock.queue(200, {})
    mock.queue(200, {})
    async with make_client(mock) as c:
        cancelled = await c.cancel_all({"A", "B"})
    assert cancelled == ["o1", "o2"]
    deleted = [r.url.path for r in mock.requests if r.method == "DELETE"]
    assert deleted == [
        "/trade-api/v2/portfolio/orders/o1",
        "/trade-api/v2/portfolio/orders/o2",
    ]


async def test_cancel_all_survives_an_order_that_already_filled():
    mock = MockKalshi()
    mock.queue(200, {"orders": [{"order_id": "o1", "ticker": "A"},
                                {"order_id": "o2", "ticker": "A"}]})
    mock.queue(404, {"error": "order not found"})  # filled first
    mock.queue(200, {})
    async with make_client(mock) as c:
        cancelled = await c.cancel_all({"A"})
    assert cancelled == ["o2"]


async def test_cancel_all_asks_only_for_resting_orders():
    mock = MockKalshi()
    mock.queue(200, {"orders": []})
    async with make_client(mock) as c:
        await c.cancel_all()
    assert "status=resting" in str(mock.requests[0].url)


# -- errors and backoff ----------------------------------------------------
async def test_429_is_retried_then_succeeds():
    mock = MockKalshi()
    mock.queue(429, {"error": "rate limited"})
    mock.queue(200, {"balance": 1000})
    async with make_client(mock) as c:
        result = await c.get_balance()
    assert result["balance"] == 1000
    assert len(mock.requests) == 2


async def test_server_errors_are_retried_then_raise():
    mock = MockKalshi()
    for _ in range(3):
        mock.queue(503, {"error": "unavailable"})
    async with make_client(mock, max_retries=2) as c:
        with pytest.raises(KalshiError) as exc:
            await c.get_balance()
    assert exc.value.status == 503
    assert len(mock.requests) == 3


async def test_client_errors_are_not_retried():
    mock = MockKalshi()
    mock.queue(400, {"error": "bad request"})
    async with make_client(mock) as c:
        with pytest.raises(KalshiError) as exc:
            await c.get_balance()
    assert exc.value.status == 400
    assert len(mock.requests) == 1, "4xx must not be retried"


async def test_empty_body_is_handled():
    mock = MockKalshi()
    mock.responses.append(httpx.Response(204))
    async with make_client(mock) as c:
        assert await c.cancel_order("x") == {}


# -- positions and fills ---------------------------------------------------
async def test_positions_are_scoped_to_the_event():
    mock = MockKalshi()
    mock.queue(200, {"market_positions": [{"ticker": "A", "position": 3}]})
    async with make_client(mock) as c:
        positions = await c.get_positions(event_ticker="KXEVENT")
    assert positions[0]["position"] == 3
    assert "event_ticker=KXEVENT" in str(mock.requests[0].url)


# -- rate limiting ---------------------------------------------------------
async def test_reads_and_writes_use_separate_budgets():
    mock = MockKalshi()
    async with make_client(mock) as c:
        assert c._read_bucket is not c._write_bucket


async def test_token_bucket_limits_throughput():
    import time

    bucket = TokenBucket(rate_per_s=50.0, burst=1)
    started = time.monotonic()
    for _ in range(4):
        await bucket.acquire()
    # 1 burst token plus 3 refills at 50/s is at least ~60ms.
    assert time.monotonic() - started >= 0.04
