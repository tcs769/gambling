"""Entry point: load the event, show the startup screen, trade it live."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .audio import AudioStream, check_tools
from .config import ConfigError, Credentials, Settings
from .dashboard import Dashboard
from .engine import Engine
from .jev import JevClient
from .jsonl_log import JsonlLogger, new_run_dir
from .kalshi.auth import KalshiSigner
from .kalshi.rest import KalshiClient, KalshiError
from .kalshi.ws import KalshiWebSocket
from .rules_check import screen_all
from .safety import STOP_FILE, KillSwitch
from .terms import TermMarket, term_market_from_api
from .transcribe import Transcriber

console = Console()
log = logging.getLogger("mentionbot")

TRADEABLE_STATUSES = {"active", "open", "initialized"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="mentionbot",
        description="Trade Kalshi mention markets live against real-time transcription.",
    )
    p.add_argument("--event-ticker", required=True, help="Kalshi event ticker")
    p.add_argument("--stream-url", required=True, help="Live stream URL (YouTube, C-SPAN, ...)")
    p.add_argument(
        "--description",
        required=True,
        help='Event and speaker, e.g. "Trump press conference on the economy"',
    )
    p.add_argument("--duration-minutes", type=float, required=True, help="Scheduled duration")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--log-dir", default="logs")
    p.add_argument("--no-dashboard", action="store_true")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def setup_logging(run_dir: Path, verbose: bool) -> None:
    handler = logging.FileHandler(run_dir / "run.log")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(handler)
    # The dashboard owns the terminal; console logging would corrupt it.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)


def startup_screen(
    args: argparse.Namespace,
    settings: Settings,
    tradable: list[TermMarket],
    flagged: list[TermMarket],
    balance_cents: int | None,
) -> None:
    table = Table(title="Markets to trade", expand=True)
    table.add_column("Ticker", no_wrap=True)
    table.add_column("Term")
    table.add_column("Variants")
    table.add_column("Needs", justify="right")
    table.add_column("Open", justify="right")
    for m in tradable:
        table.add_row(
            m.ticker,
            m.label,
            " / ".join(m.variants),
            str(m.threshold),
            "-" if m.opening_price is None else f"{m.opening_price}c",
        )

    caps = (
        f"entry_gap [bold]{settings.entry_gap}c[/]   "
        f"exit_gap [bold]{settings.exit_gap}c[/]   "
        f"jev every [bold]{settings.jev_interval_s}s[/]   "
        f"model [bold]{settings.jev_model}[/]\n"
        f"size [bold]{settings.contracts_per_entry}[/]/entry, "
        f"max [bold]{settings.max_contracts_per_market}[/]/market, "
        f"max [bold]${settings.max_dollars_per_event:.2f}[/] this event\n"
        f"auto-halt at [bold]-${settings.max_loss_per_event:.2f}[/]   "
        f"min word confidence [bold]{settings.min_word_confidence}[/]   "
        f"stale after [bold]{settings.stale_data_s}s[/]\n"
        f"order timeout [bold]{settings.order_timeout_s}s[/]   "
        f"max Yes price after a mention [bold]{settings.max_price_after_mention}c[/]"
    )

    console.print(
        Panel(
            f"[bold]{args.description}[/]\n"
            f"event [bold]{args.event_ticker}[/]   "
            f"duration [bold]{args.duration_minutes:.0f}m[/]\n"
            f"stream {args.stream_url}\n"
            + (f"account balance [bold]${balance_cents / 100:,.2f}[/]" if balance_cents is not None else ""),
            title="Event",
            border_style="cyan",
        )
    )
    console.print(table)
    console.print(Panel(caps, title="Settings and caps", border_style="cyan"))

    if flagged:
        ftable = Table(title="EXCLUDED markets (need your approval)", expand=True)
        ftable.add_column("Ticker", no_wrap=True)
        ftable.add_column("Term")
        ftable.add_column("Reason", ratio=2)
        for m in flagged:
            ftable.add_row(m.ticker, m.label or m.title, m.flagged_reason or "")
        console.print(ftable)

    console.print(
        Panel(
            "[bold red]THIS TRADES REAL MONEY IMMEDIATELY. THERE IS NO PAPER MODE.[/]\n"
            f"Kill switch: press [bold]k[/] to cancel orders and stop entries, "
            f"[bold]f[/] to flatten at the bid.\n"
            f"Or create a [bold]{STOP_FILE}[/] file in this folder "
            f"(write FLATTEN inside it to flatten).",
            border_style="red",
        )
    )


def confirm_live() -> bool:
    try:
        answer = input("Type LIVE to begin trading with real money: ")
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip() == "LIVE"


async def load_markets(client: KalshiClient, event_ticker: str) -> list[TermMarket]:
    raw = await client.get_markets(event_ticker)
    if not raw:
        raise ConfigError(f"no markets found for event {event_ticker!r}")
    usable = [
        m for m in raw if (m.get("status") or "").lower() in TRADEABLE_STATUSES
    ] or raw
    return [term_market_from_api(m) for m in usable]


async def run(args: argparse.Namespace) -> int:
    settings = Settings.load(args.config)
    creds = Credentials.from_env()
    check_tools()

    run_dir = new_run_dir(args.log_dir)
    setup_logging(run_dir, args.verbose)

    signer = KalshiSigner.from_pem_path(creds.kalshi_key_id, creds.kalshi_private_key_path)
    client = KalshiClient(signer)

    try:
        markets = await load_markets(client, args.event_ticker)
        tradable, flagged = screen_all(markets)

        balance_cents: int | None = None
        try:
            balance_cents = int((await client.get_balance()).get("balance") or 0)
        except KalshiError as exc:
            console.print(f"[yellow]could not read balance: {exc}[/]")

        startup_screen(args, settings, tradable, flagged, balance_cents)

        if not tradable:
            console.print("[red]No tradable markets after the rules screen. Exiting.[/]")
            return 1
        if not confirm_live():
            console.print("[yellow]Not confirmed. Nothing was traded.[/]")
            return 1

        return await trade(args, settings, creds, client, tradable, flagged, run_dir)
    finally:
        await client.aclose()


async def trade(
    args: argparse.Namespace,
    settings: Settings,
    creds: Credentials,
    client: KalshiClient,
    tradable: list[TermMarket],
    flagged: list[TermMarket],
    run_dir: Path,
) -> int:
    tickers = [m.ticker for m in tradable]
    keyterms = [v for m in tradable for v in m.variants]

    logger = JsonlLogger(run_dir)
    logger.write(
        "decisions",
        {
            "kind": "startup",
            "event": args.event_ticker,
            "description": args.description,
            "duration_minutes": args.duration_minutes,
            "settings": settings.__dict__,
            "markets": [
                {"ticker": m.ticker, "term": m.label, "variants": m.variants,
                 "threshold": m.threshold, "opening_price": m.opening_price}
                for m in tradable
            ],
            "excluded": [
                {"ticker": m.ticker, "reason": m.flagged_reason} for m in flagged
            ],
        },
    )

    jev = JevClient(
        creds.typesafe_api_key, settings.jev_model, timeout_s=settings.jev_timeout_s
    )
    kill = KillSwitch(Path.cwd())
    audio = AudioStream(args.stream_url, sample_rate=settings.sample_rate)
    transcriber = Transcriber(
        creds.assemblyai_api_key,
        keyterms=keyterms,
        sample_rate=settings.sample_rate,
        speech_model=settings.speech_model,
    )
    ws = KalshiWebSocket(client.signer, tickers)

    engine = Engine(
        settings=settings,
        client=client,
        markets=tradable,
        flagged=flagged,
        event_ticker=args.event_ticker,
        event_description=args.description,
        duration_minutes=args.duration_minutes,
        jev=jev,
        transcriber=transcriber,
        ws=ws,
        kill=kill,
        logger=logger,
        audio_connected=audio,
    )
    transcriber.on_segment = engine.on_segment
    ws.set_fill_handler(engine.on_fill)

    use_dashboard = not args.no_dashboard and sys.stdout.isatty()
    try:
        ws.start()
        kill.start(keyboard=use_dashboard)
        transcriber.start(audio.chunks())
        with Dashboard(enabled=use_dashboard) as dash:
            engine.dashboard = dash
            await engine.run()
    except KeyboardInterrupt:
        console.print("[yellow]interrupted; cancelling orders[/]")
        await engine.shutdown()
    finally:
        await transcriber.stop()
        await audio.stop()
        await ws.stop()
        await kill.stop()
        await jev.aclose()
        logger.close()

    pos = engine.portfolio
    console.print(
        Panel(
            f"realized [bold]{pos.realized_cents() / 100:+.2f}[/]   "
            f"spent [bold]${pos.gross_spend_cents / 100:.2f}[/]\n"
            f"open positions: "
            + (
                ", ".join(
                    f"{t} {p.side.upper()} x{p.count}"
                    for t, p in pos.positions.items()
                    if not p.is_flat and p.side
                )
                or "none"
            )
            + f"\nlogs: {run_dir}",
            title="Session complete",
            border_style="cyan",
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(run(args))
    except ConfigError as exc:
        console.print(f"[red]configuration error:[/] {exc}")
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
