"""Real-time transcription via AssemblyAI streaming (v3).

Every term variant is passed as a keyterm so recognition is biased toward the
exact contract words. Only finalized turns are consumed - partials are ignored
and each turn is counted exactly once, even if the server re-emits it.

The transcriber reconnects on its own. While it is down ``connected`` is False
and the engine blocks new entries.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from assemblyai.streaming.v3 import (
    AsyncRealTimeTranscriber,
    BeginEvent,
    RealTimeParameters,
    RealTimeTranscriberOptions,
    StreamingEvents,
    TerminationEvent,
    TurnEvent,
)

from .mentions import Word

log = logging.getLogger(__name__)

# AssemblyAI caps the keyterm list; keep well inside it.
MAX_KEYTERMS = 100


@dataclass
class Segment:
    """One finalized turn."""

    text: str
    words: list[Word]
    received_at: float
    turn_order: int


@dataclass
class TranscriptWindow:
    """Rolling buffer of recent finalized text, for Jev's state."""

    window_s: float = 120.0
    _segments: deque[Segment] = field(default_factory=deque)

    def add(self, segment: Segment, now: float | None = None) -> None:
        self._segments.append(segment)
        # Trim against the segment's own clock so callers with a synthetic
        # clock (and tests) stay consistent.
        self._trim(segment.received_at if now is None else now)

    def _trim(self, now: float | None = None) -> None:
        cutoff = (time.time() if now is None else now) - self.window_s
        while self._segments and self._segments[0].received_at < cutoff:
            self._segments.popleft()

    def text(self, now: float | None = None) -> str:
        self._trim(now)
        return " ".join(s.text for s in self._segments if s.text).strip()

    @property
    def last_received_at(self) -> float:
        return self._segments[-1].received_at if self._segments else 0.0


def keyterms_for(variants: list[str]) -> list[str]:
    """De-duplicated keyterm list, capped to the API limit."""
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        key = v.strip().casefold()
        if key and key not in seen:
            seen.add(key)
            out.append(v.strip())
    if len(out) > MAX_KEYTERMS:
        log.warning("truncating %d keyterms to %d", len(out), MAX_KEYTERMS)
    return out[:MAX_KEYTERMS]


class Transcriber:
    """Streams PCM to AssemblyAI and emits finalized segments."""

    def __init__(
        self,
        api_key: str,
        *,
        keyterms: list[str],
        sample_rate: int = 16000,
        speech_model: str = "universal-streaming-english",
        on_segment: Callable[[Segment], None] | None = None,
    ):
        self._api_key = api_key
        self.keyterms = keyterms_for(keyterms)
        self.sample_rate = sample_rate
        self.speech_model = speech_model
        self.on_segment = on_segment

        self.connected = False
        self.last_segment_at: float = 0.0
        self.session_id: str | None = None
        self._seen_turns: set[tuple[str, int]] = set()
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    # -- lifecycle -------------------------------------------------------
    def start(self, audio: AsyncIterator[bytes]) -> None:
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(
                self._run_forever(audio), name="assemblyai-stream"
            )

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.connected = False

    def _params(self) -> RealTimeParameters:
        return RealTimeParameters(
            sample_rate=self.sample_rate,
            encoding="pcm_s16le",
            speech_model=self.speech_model,
            # Bias recognition toward the exact contract words.
            keyterms_prompt=self.keyterms,
            # Raw turns: no formatting pass, so no duplicate re-emission and
            # word confidences stay as the model produced them.
            format_turns=False,
        )

    async def _run_forever(self, audio: AsyncIterator[bytes]) -> None:
        attempt = 0
        while not self._stop.is_set():
            # The SDK client is single-use: build a fresh one per attempt.
            transcriber = AsyncRealTimeTranscriber(
                options=RealTimeTranscriberOptions(api_key=self._api_key)
            )
            transcriber.on(StreamingEvents.Begin, self._on_begin)
            transcriber.on(StreamingEvents.Turn, self._on_turn)
            transcriber.on(StreamingEvents.Termination, self._on_termination)
            transcriber.on(StreamingEvents.Error, self._on_error)
            try:
                await transcriber.connect(self._params())
                self.connected = True
                attempt = 0
                log.info("AssemblyAI connected (%d keyterms)", len(self.keyterms))
                await transcriber.stream(audio)
            except asyncio.CancelledError:
                with contextlib.suppress(Exception):
                    await transcriber.disconnect(terminate=True)
                raise
            except Exception as exc:
                log.warning("AssemblyAI stream failed (%s); reconnecting", exc)
            finally:
                self.connected = False
                with contextlib.suppress(Exception):
                    await transcriber.disconnect(terminate=False)

            if self._stop.is_set():
                return
            attempt += 1
            await asyncio.sleep(min(2.0**attempt * 0.5, 15.0))

    # -- event handlers --------------------------------------------------
    def _on_begin(self, _client, event: BeginEvent) -> None:
        self.session_id = str(event.id)
        log.info("AssemblyAI session %s", self.session_id)

    def _on_termination(self, _client, event: TerminationEvent) -> None:
        self.connected = False
        log.info("AssemblyAI session terminated after %ss", event.audio_duration_seconds)

    def _on_error(self, _client, error: Exception) -> None:
        self.connected = False
        log.error("AssemblyAI error: %s", error)

    def _on_turn(self, _client, event: TurnEvent) -> None:
        # Only finalized turns feed the counter.
        if not event.end_of_turn:
            return
        key = (self.session_id or "?", event.turn_order)
        if key in self._seen_turns:
            return  # the server can re-emit a turn; count it once
        self._seen_turns.add(key)

        words = [
            Word(
                text=w.text,
                confidence=float(w.confidence),
                start_ms=int(w.start),
                end_ms=int(w.end),
            )
            for w in (event.words or [])
            if w.word_is_final
        ]
        if not words and not (event.transcript or "").strip():
            return

        segment = Segment(
            text=event.transcript or " ".join(w.text for w in words),
            words=words,
            received_at=time.time(),
            turn_order=event.turn_order,
        )
        self.last_segment_at = segment.received_at
        if self.on_segment is not None:
            self.on_segment(segment)

    # -- health ----------------------------------------------------------
    def is_stale(self, stale_after_s: float, now: float | None = None) -> bool:
        """True while disconnected, or if no segment has arrived recently.

        Before the first segment arrives we rely on the connection flag alone:
        a speaker who has not said anything yet is not stale data.
        """
        if not self.connected:
            return True
        if not self.last_segment_at:
            return False
        return ((time.time() if now is None else now) - self.last_segment_at) > stale_after_s
