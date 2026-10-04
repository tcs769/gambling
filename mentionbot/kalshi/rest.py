"""Kalshi REST client: signed requests, rate limiting, 429 backoff."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

import httpx

from .auth import KalshiSigner

log = logging.getLogger(__name__)

PROD_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Kalshi meters reads and writes against separate budgets. These defaults sit
# below the Basic tier allowance; raise them only to match your actual tier.
DEFAULT_READ_RPS = 8.0
DEFAULT_WRITE_RPS = 4.0

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class KalshiError(RuntimeError):
    """A non-retryable error response from Kalshi."""

    def __init__(self, status: int, body: str, path: str):
        super().__init__(f"Kalshi {status} on {path}: {body[:300]}")
        self.status = status
        self.body = body
        self.path = path


class TokenBucket:
    """Simple async token bucket rate limiter."""

    def __init__(self, rate_per_s: float, burst: float | None = None):
        self.rate = rate_per_s
        self.capacity = burst if burst is not None else max(1.0, rate_per_s)
        self._tokens = self.capacity
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(
                    self.capacity, self._tokens + (now - self._last) * self.rate
                )
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                await asyncio.sleep((1.0 - self._tokens) / self.rate)


class KalshiClient:
    """Async Kalshi REST client.

    Every request is signed. Reads and writes draw on separate rate budgets and
    429s back off exponentially with jitter.
    """

    def __init__(
        self,
        signer: KalshiSigner,
        base_url: str = PROD_BASE,
        *,
        read_rps: float = DEFAULT_READ_RPS,
        write_rps: float = DEFAULT_WRITE_RPS,
        timeout: float = 10.0,
        max_retries: int = 5,
        client: httpx.AsyncClient | None = None,
    ):
        self.signer = signer
        self.base_url = base_url.rstrip("/")
        self._base_path = httpx.URL(self.base_url).path.rstrip("/")
        self._read_bucket = TokenBucket(read_rps)
        self._write_bucket = TokenBucket(write_rps)
        self._max_retries = max_retries
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> KalshiClient:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    # -- plumbing --------------------------------------------------------
    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Issue one signed request, retrying on 429/5xx/transport errors."""
        method = method.upper()
        bucket = self._write_bucket if method in WRITE_METHODS else self._read_bucket
        # The signed path includes the /trade-api/v2 prefix but never the query.
        signed_path = self._base_path + path
        url = self.base_url + path

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            await bucket.acquire()
            headers = {
                **self.signer.headers(method, signed_path),
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            try:
                resp = await self._client.request(
                    method, url, params=params, json=json, headers=headers
                )
            except httpx.HTTPError as exc:  # transport-level failure
                last_exc = exc
                if attempt >= self._max_retries:
                    raise
                await self._sleep_backoff(attempt)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                last_exc = KalshiError(resp.status_code, resp.text, path)
                if attempt >= self._max_retries:
                    raise last_exc
                await self._sleep_backoff(attempt, resp.headers.get("Retry-After"))
                continue

            if resp.status_code >= 400:
                raise KalshiError(resp.status_code, resp.text, path)

            if not resp.content:
                return {}
            return resp.json()

        raise last_exc or RuntimeError("unreachable")

    @staticmethod
    async def _sleep_backoff(attempt: int, retry_after: str | None = None) -> None:
        if retry_after:
            try:
                await asyncio.sleep(min(float(retry_after), 30.0))
                return
            except ValueError:
                pass
        delay = min(2.0**attempt * 0.25, 8.0)
        await asyncio.sleep(delay + random.uniform(0, 0.25))

    async def get(self, path: str, **params: Any) -> dict[str, Any]:
        clean = {k: v for k, v in params.items() if v is not None}
        return await self.request("GET", path, params=clean or None)

    # -- market data -----------------------------------------------------
    async def get_event(self, event_ticker: str) -> dict[str, Any]:
        return await self.get(f"/events/{event_ticker}")

    async def get_markets(
        self, event_ticker: str, *, status: str | None = None
    ) -> list[dict[str, Any]]:
        """All markets in an event, following pagination."""
        out: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page = await self.get(
                "/markets",
                event_ticker=event_ticker,
                limit=200,
                status=status,
                cursor=cursor,
            )
            out.extend(page.get("markets") or [])
            cursor = page.get("cursor") or None
            if not cursor:
                return out

    async def get_market(self, ticker: str) -> dict[str, Any]:
        return (await self.get(f"/markets/{ticker}")).get("market", {})

    async def get_orderbook(self, ticker: str, depth: int = 10) -> dict[str, Any]:
        resp = await self.get(f"/markets/{ticker}/orderbook", depth=depth)
        return resp.get("orderbook") or {}

    # -- portfolio -------------------------------------------------------
    async def get_balance(self) -> dict[str, Any]:
        return await self.get("/portfolio/balance")

    async def get_positions(self, event_ticker: str | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page = await self.get(
                "/portfolio/positions",
                event_ticker=event_ticker,
                limit=200,
                cursor=cursor,
            )
            out.extend(page.get("market_positions") or [])
            cursor = page.get("cursor") or None
            if not cursor:
                return out

    async def get_fills(self, ticker: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        page = await self.get("/portfolio/fills", ticker=ticker, limit=limit)
        return page.get("fills") or []

    async def get_orders(
        self, *, ticker: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page = await self.get(
                "/portfolio/orders",
                ticker=ticker,
                status=status,
                limit=200,
                cursor=cursor,
            )
            out.extend(page.get("orders") or [])
            cursor = page.get("cursor") or None
            if not cursor:
                return out

    # -- orders ----------------------------------------------------------
    async def create_order(
        self,
        *,
        ticker: str,
        side: str,
        action: str,
        count: int,
        price_cents: int,
        client_order_id: str,
        post_only: bool = False,
    ) -> dict[str, Any]:
        """Place a limit order. ``side`` is yes|no, ``action`` is buy|sell."""
        if side not in ("yes", "no"):
            raise ValueError(f"side must be yes|no, got {side!r}")
        if action not in ("buy", "sell"):
            raise ValueError(f"action must be buy|sell, got {action!r}")
        if not 1 <= price_cents <= 99:
            raise ValueError(f"limit price must be 1..99 cents, got {price_cents}")
        if count < 1:
            raise ValueError(f"count must be >= 1, got {count}")

        body: dict[str, Any] = {
            "ticker": ticker,
            "client_order_id": client_order_id,
            "side": side,
            "action": action,
            "count": count,
            "type": "limit",
            # The price field is always the price of the side being traded.
            ("yes_price" if side == "yes" else "no_price"): price_cents,
        }
        if post_only:
            body["post_only"] = True
        resp = await self.request("POST", "/portfolio/orders", json=body)
        return resp.get("order") or resp

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        return await self.request("DELETE", f"/portfolio/orders/{order_id}")

    async def cancel_all(self, tickers: set[str] | None = None) -> list[str]:
        """Cancel every resting order (optionally limited to ``tickers``).

        Kalshi has no single cancel-all endpoint, so we list resting orders and
        cancel them one by one. Returns the order ids we cancelled.
        """
        resting = await self.get_orders(status="resting")
        cancelled: list[str] = []
        for order in resting:
            if tickers is not None and order.get("ticker") not in tickers:
                continue
            oid = order.get("order_id")
            if not oid:
                continue
            try:
                await self.cancel_order(oid)
                cancelled.append(oid)
            except KalshiError as exc:
                # A fill or an earlier cancel can land first; that is fine.
                log.warning("cancel failed for %s: %s", oid, exc)
        return cancelled
