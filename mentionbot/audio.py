"""Live audio capture: yt-dlp resolves the stream, ffmpeg converts it.

Output is 16 kHz mono signed 16-bit little-endian PCM, which is what
AssemblyAI's streaming endpoint expects. The process is restarted automatically
if the stream drops; callers watch ``connected`` to pause trading entries while
audio is down.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from collections.abc import AsyncIterator

log = logging.getLogger(__name__)

BYTES_PER_SAMPLE = 2


class AudioError(RuntimeError):
    pass


def check_tools() -> None:
    """Fail early if ffmpeg or yt-dlp are missing."""
    missing = [t for t in ("ffmpeg", "yt-dlp") if shutil.which(t) is None]
    if missing:
        raise AudioError(
            f"missing required tool(s): {', '.join(missing)}. "
            "Install ffmpeg and `pip install yt-dlp`."
        )


async def resolve_stream_url(url: str, timeout: float = 45.0) -> str:
    """Ask yt-dlp for a direct media URL.

    Falls back to the original URL, which covers direct .m3u8/.mp3 links that
    yt-dlp does not need to handle.
    """
    if shutil.which("yt-dlp") is None:
        return url
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp",
        "--quiet",
        "--no-warnings",
        "--no-playlist",
        # Prefer an audio-only rendition; fall back to whatever exists.
        "-f",
        "bestaudio/best",
        "-g",
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        log.warning("yt-dlp timed out resolving %s; using the URL as given", url)
        return url
    if proc.returncode != 0:
        log.warning(
            "yt-dlp could not resolve %s (%s); using the URL as given",
            url,
            stderr.decode(errors="replace").strip()[:200],
        )
        return url
    lines = [ln for ln in stdout.decode().splitlines() if ln.strip()]
    return lines[0].strip() if lines else url


class AudioStream:
    """Yields raw PCM chunks from a live stream, restarting on failure."""

    def __init__(
        self,
        url: str,
        *,
        sample_rate: int = 16000,
        chunk_ms: int = 50,
        resolve: bool = True,
    ):
        self.url = url
        self.sample_rate = sample_rate
        self.chunk_bytes = int(sample_rate * BYTES_PER_SAMPLE * chunk_ms / 1000)
        self.connected = False
        self._resolve = resolve
        self._proc: asyncio.subprocess.Process | None = None
        self._stop = asyncio.Event()

    def _ffmpeg_args(self, media_url: str) -> list[str]:
        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            # Keep pulling through transient network hiccups.
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-i", media_url,
            "-vn",
            "-ac", "1",
            "-ar", str(self.sample_rate),
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "pipe:1",
        ]

    async def stop(self) -> None:
        self._stop.set()
        await self._kill()

    async def _kill(self) -> None:
        proc, self._proc = self._proc, None
        self.connected = False
        if proc is None or proc.returncode is not None:
            return
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass

    async def chunks(self) -> AsyncIterator[bytes]:
        """Yield PCM chunks until ``stop()`` is called."""
        check_tools()
        attempt = 0
        while not self._stop.is_set():
            media_url = await resolve_stream_url(self.url) if self._resolve else self.url
            try:
                self._proc = await asyncio.create_subprocess_exec(
                    *self._ffmpeg_args(media_url),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except OSError as exc:
                raise AudioError(f"could not start ffmpeg: {exc}") from exc

            self.connected = True
            attempt = 0
            assert self._proc.stdout is not None
            try:
                while not self._stop.is_set():
                    data = await self._proc.stdout.readexactly(self.chunk_bytes)
                    yield data
            except asyncio.IncompleteReadError as exc:
                if exc.partial:
                    yield exc.partial
                log.warning("audio stream ended; restarting")
            except asyncio.CancelledError:
                await self._kill()
                raise
            finally:
                self.connected = False

            await self._kill()
            if self._stop.is_set():
                return
            attempt += 1
            await asyncio.sleep(min(2.0 * attempt, 10.0))
