# mentionbot

Trades Kalshi **mention markets** live. During an event it transcribes the
speaker in real time, asks Jev (TypeSafe System One) for each term's probability
of resolving Yes, and trades when Jev's estimate differs from the market by
`entry_gap` cents or more, net of fees.

> **This trades real money from the first run. There is no paper mode.**
> The startup screen requires you to type `LIVE` before anything is sent.

## How it works

```
live stream ──yt-dlp──► ffmpeg ──16kHz PCM──► AssemblyAI ──finalized turns──┐
                                                                            │
Kalshi WS ──orderbook snapshot/delta──► derived Yes/No asks ───┐            │
                                                               ▼            ▼
                                                        strategy ◄── mention counter
                                                               ▲            │
                                              Jev probabilities┘◄───────────┘
                                                               │
                                                     limit orders ──► Kalshi REST
```

1. **Kalshi** — markets for the event are loaded, their titles parsed into term
   variants and thresholds, and their rules text screened. The order book is
   streamed over WebSocket.
2. **Audio** — `yt-dlp` resolves the stream, `ffmpeg` converts it to 16 kHz mono
   PCM, which is streamed to AssemblyAI with every term variant passed as a
   keyterm.
3. **Counting** — finalized words are matched deterministically (whole word,
   case-insensitive, plus `s`/`es`/`'s`/`s'`). Words below
   `min_word_confidence` cannot take part in a match.
4. **Jev** — every `jev_interval_s` one request carries the event state and one
   Noul question per unresolved market. Live prices are deliberately excluded so
   Jev cannot simply echo the market.
5. **Trading** — limit orders only, one position per market, sized and capped.

## Setup

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
# ffmpeg must be on PATH (apt install ffmpeg / brew install ffmpeg)
```

Credentials come **only** from the environment — never from `config.yaml`, and
they are never logged:

| Variable | Purpose |
| --- | --- |
| `KALSHI_API_KEY_ID` | Kalshi API key ID (UUID) |
| `KALSHI_PRIVATE_KEY_PATH` | path to the RSA private key PEM (read **and** write key) |
| `ASSEMBLYAI_API_KEY` | real-time speech-to-text |
| `TYPESAFE_API_KEY` | Jev — or `AI_GATEWAY_API_KEY` if routed through Vercel AI Gateway |

`.env`, `*.key` and `*.pem` are gitignored.

## Running

```bash
python -m mentionbot.cli \
  --event-ticker KXSPEECH-26OCT04 \
  --stream-url "https://www.youtube.com/watch?v=..." \
  --description "Trump press conference on the economy" \
  --duration-minutes 60
```

The startup screen lists the markets, the settings and the caps, plus any
markets excluded by the rules screen. Type `LIVE` to begin.

### Kill switch

| Action | Effect |
| --- | --- |
| press `k` (or create a `STOP` file) | cancel all open orders, stop new entries |
| press `f` (or write `FLATTEN` into `STOP`) | additionally sell every position at the bid |

Trading also halts automatically when realized + unrealized loss reaches
`max_loss_per_event`.

## Settings (`config.yaml`)

| Setting | Meaning |
| --- | --- |
| `entry_gap` / `exit_gap` | edge in cents, **net of fee**, to open / to close |
| `jev_interval_s` | seconds between Jev refreshes |
| `transcript_window_s` | seconds of transcript sent to Jev |
| `contracts_per_entry` | size of one entry |
| `max_contracts_per_market` / `max_dollars_per_event` | hard caps |
| `max_loss_per_event` | auto-halt threshold |
| `min_word_confidence` | STT confidence floor for counting a word |
| `max_price_after_mention` | price ceiling for Yes once a mention is heard |
| `order_timeout_s` | cancel unfilled orders after this long |
| `stale_data_s` | block entries if book or transcript is older than this |
| `jev_model` | **pinned** Jev version; a `-latest`/`-preview` alias is rejected |

## The trading rule

All prices in cents; every edge is net of the Kalshi taker fee
(`ceil(0.07 x C x P x (1-P))`), because we always cross the spread.

| State | Condition | Order |
| --- | --- | --- |
| flat | `jev_p - yes_ask - fee >= entry_gap` | buy Yes at `yes_ask` |
| flat | `(100 - jev_p) - no_ask - fee >= entry_gap` | buy No at `no_ask` |
| holding Yes | `jev_p - yes_bid - fee <= exit_gap` | sell at `yes_bid` |
| holding No | `(100 - jev_p) - no_bid - fee <= exit_gap` | sell at `no_bid` |
| term already said | — | hold Yes to settlement; sell any No at the bid |

Kalshi quotes **bids on both sides**, so the asks are derived:
`yes_ask = 100 - best_no_bid` and `no_ask = 100 - best_yes_bid`.

## Rules screen

Our counter matches whole words plus plural and possessive forms. Before
trading, each market's rules text is screened for *different* matching —
compound words, exact-form-only, excluded plurals, per-sentence caps,
on-screen text, other speakers. Any market that differs is **excluded and
listed on the startup screen** until you approve it. The screen is
deliberately trigger-happy: a false flag costs one skipped market, a missed
flag costs money.

## Logs

Each run writes to `logs/<UTC timestamp>/`:

| File | Contents |
| --- | --- |
| `transcript.jsonl` | finalized turns with per-word timestamps and confidence |
| `jev.jsonl` | every Jev request and response, with model and latency |
| `decisions.jsonl` | mentions detected, entry/exit decisions, reconciliation |
| `orders.jsonl` | placements, rejections, cancels |
| `fills.jsonl` | fills from both the WebSocket and REST reconciliation |
| `run.log` | plain-text engine log |

## Tests

```bash
python -m pytest        # 327 tests, no network
ruff check mentionbot tests
```

Covers request signing (cross-checked against the official `kalshi-python-sync`
SDK), the fee schedule, ask derivation and book maintenance, mention matching
on sample text, the rules screen, entry/exit and side selection, caps, the kill
switch, position reconciliation, and the engine loop against a mocked Kalshi
API.

## Notes and caveats

- **`max_price_after_mention` rarely binds at `entry_gap: 15`.** With fair value
  pinned to 100 after a mention, a 96c Yes ask shows an edge of only ~3c, so the
  entry gap already blocks it long before the 95c cap does. The cap matters if
  you lower `entry_gap`. It is enforced whenever *any* mention has been heard,
  not only once the threshold is met, since a mis-hear is exactly what it guards
  against.
- **Fees are charged at the taker rate and rounded up to the whole cent.** That
  is the conservative direction — overstating the fee can only make the bot
  trade less.
- **Exit orders are also cancelled at `order_timeout_s`** and re-priced on the
  next cycle, rather than left resting where the market has moved away.
- **Jev health gates entries only.** If a Jev call fails or times out, new
  entries stop until it recovers; exits and the kill switch always work.
- Positions and fills are reconciled against Kalshi's portfolio endpoints at
  startup and every 30 seconds; Kalshi is the source of truth on disagreement.
