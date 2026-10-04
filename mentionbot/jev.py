"""Jev (TypeSafe System One) odds.

One request per cycle carries the whole event state plus one Noul question per
unresolved market. A Noul answer is a probability of Yes in [0, 1], which we use
directly as that market's fair value.

Live prices are deliberately excluded from the state: Jev must form an
independent view, otherwise it would just echo the market we are trying to beat.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, Noul

from .terms import TermMarket

log = logging.getLogger(__name__)

CRITERIA_TRUE = (
    "The speaker is on, or is clearly heading toward, this term's topic, and "
    "enough time remains in the event for the remaining mentions to happen."
)
CRITERIA_FALSE = (
    "The discussion is away from this term's topic with no sign of returning, "
    "or too little time remains for the remaining mentions to happen."
)


@dataclass
class JevState:
    """Everything Jev is told about the event. Never includes live prices."""

    event_description: str
    elapsed_minutes: float
    remaining_minutes: float
    transcript_window: str
    terms: list[dict[str, Any]] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "event": self.event_description,
            "elapsed_minutes": round(self.elapsed_minutes, 1),
            "remaining_minutes": round(self.remaining_minutes, 1),
            "recent_transcript": self.transcript_window,
            "terms": self.terms,
        }


def build_question(market: TermMarket, count: int) -> Noul:
    """One Noul question for a market, given the count we have heard so far."""
    variants = "; ".join(market.variants)
    remaining = max(0, market.threshold - count)
    return Noul(
        instructions=(
            f"Will the speaker say '{market.label}' "
            f"(variants: {variants}; plurals and possessives count) "
            f"at least {market.threshold} time(s) in total before the event ends? "
            f"It has been said {count} time(s) so far, so {remaining} more "
            f"{'is' if remaining == 1 else 'are'} needed."
        ),
        criteria={"true": CRITERIA_TRUE, "false": CRITERIA_FALSE},
    )


@dataclass
class JevResult:
    """Probabilities in cents, keyed by market ticker."""

    probabilities: dict[str, int]
    model: str
    latency_s: float
    raw: dict[str, Any] = field(default_factory=dict)


class JevClient:
    """Calls Jev and tracks whether it is currently healthy.

    ``healthy`` goes False on any failure or timeout; the engine blocks new
    entries until a later call succeeds. Exits are never gated on Jev.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout_s: float = 8.0,
        base_url: str | None = None,
        client: Any | None = None,
    ):
        if model.endswith(("-latest", "-preview")):
            raise ValueError(
                f"Jev model must be pinned, not the moving alias {model!r}"
            )
        self.model = model
        self.timeout_s = timeout_s
        self.healthy = False
        self.last_ok_at: float = 0.0
        self.last_error: str | None = None
        self._client = client or AsyncTypeSafeClient(
            api_key=api_key, model=model, timeout=timeout_s, base_url=base_url
        )

    async def aclose(self) -> None:
        close = getattr(self._client, "aclose", None) or getattr(self._client, "close", None)
        if close is not None:
            result = close()
            if asyncio.iscoroutine(result):
                await result

    async def estimate(
        self, state: JevState, markets: list[tuple[TermMarket, int]]
    ) -> JevResult | None:
        """Ask Jev for one probability per market. Returns None on failure.

        ``markets`` is a list of ``(market, mentions_so_far)`` for the markets
        that are still unresolved.
        """
        if not markets:
            return None

        questions = {m.ticker: build_question(m, count) for m, count in markets}
        started = time.monotonic()
        try:
            response = await asyncio.wait_for(
                self._client.system_one(
                    state.to_payload(), questions, model=self.model
                ),
                timeout=self.timeout_s,
            )
        except TimeoutError:
            self._fail(f"timed out after {self.timeout_s}s")
            return None
        except Exception as exc:
            self._fail(f"{type(exc).__name__}: {exc}")
            return None

        latency = time.monotonic() - started
        probabilities: dict[str, int] = {}
        for ticker, answer in (getattr(response, "answers", None) or {}).items():
            value = getattr(answer, "noul", None)
            if value is None:
                continue
            probabilities[ticker] = int(round(max(0.0, min(1.0, float(value))) * 100))

        if not probabilities:
            self._fail("response contained no usable Noul answers")
            return None

        self.healthy = True
        self.last_ok_at = time.time()
        self.last_error = None
        return JevResult(
            probabilities=probabilities,
            model=getattr(response, "model", self.model),
            latency_s=latency,
            raw={
                "model": getattr(response, "model", self.model),
                "answers": dict(probabilities),
                "usage": getattr(getattr(response, "usage", None), "__dict__", {}),
            },
        )

    def _fail(self, reason: str) -> None:
        self.healthy = False
        self.last_error = reason
        log.warning("Jev call failed: %s", reason)
