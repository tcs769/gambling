# Recording the Donabach showcase on a Mac

Repository: https://github.com/tcs769/gambling, branch `claude/brave-euler-asv0ja` (the demo is in the `donabach-demo/` folder).

## Get the code
```bash
git clone https://github.com/tcs769/gambling.git
cd gambling
git checkout claude/brave-euler-asv0ja
# already cloned? update instead:
#   cd gambling && git fetch origin && git checkout claude/brave-euler-asv0ja && git pull origin claude/brave-euler-asv0ja
cd donabach-demo
```

## One-time setup (needs Python 3.11+ and Node 20+; check with `python3 --version`, `node --version`; `brew install python@3.13 node` if missing)
```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm install && BACKEND_URL=http://localhost:8000 npm run build && cd ..
```
(If `npm run build` stops with a Next.js security-advisory message, run the same command again; it is intermittent.)

## Every time you record (two Terminal windows)
Terminal 1, the API (no `--reload`):
```bash
cd gambling/donabach-demo/backend
.venv/bin/uvicorn app.main:app --port 8000
```
Wait for `Application startup complete.` The first start on a fresh clone compiles the simulation kernels (a few minutes); later starts take about a minute. The showcase and both what-if presets are worked out before that line appears.

Terminal 2, the app:
```bash
cd gambling/donabach-demo/frontend
npm run start -- -p 3000
```
Wait for `Ready`.

## Confirm it is ready, and that precompute is on
```bash
echo "[$DONABACH_NO_PRECOMPUTE]"      # must print [] (empty). If it prints [1], run: unset DONABACH_NO_PRECOMPUTE and restart Terminal 1.
curl -s -o /dev/null -w "%{time_total}s\n" localhost:8000/showcase/scenarios/market_drop    # under 0.2s
curl -s -o /dev/null -w "%{time_total}s\n" localhost:8000/showcase/scenarios/job_loss        # under 0.2s
curl -s localhost:3000/api/health     # {"status":"ok"}
```
The showcase uses a fixed seed, so its numbers are identical on every run whether or not the header's "Demo mode" switch (on the home page, on by default) is on.

## The flow (open http://localhost:3000/showcase in Chrome, full screen, light or dark macOS: the app is always light)
| Step | URL | Click |
|---|---|---|
| Household card | /showcase | start here |
| Advisor-only results | /showcase/wealth | "See what a good advisor gets them" |
| Reveal Donabach | /showcase/wealth (same page) | "Show what Donabach does" |
| Waterfall | /showcase/strategies | header step "Strategies" (or "Back to the strategies") |
| Job-loss preset | /showcase/whatif | header step "What if", then the radio "Job loss next year" |
| Market-drop preset | /showcase/whatif | radio "Market drops 30% next year" |

Reloading the wealth page returns it to advisor-only.

## If something goes wrong
* **Port 8000 or 3000 already in use** (`address already in use`): find the old process with `lsof -nP -iTCP:8000 -sTCP:LISTEN` (or 3000), then `kill <PID>`. A leftover old app server on 3000 serves stale files and shows broken pages: always kill it first.
* **First load slow, or the API says it is not ready**: wait for `Application startup complete.` in Terminal 1. Never use `npm run dev` for recording (it compiles each page on first visit).
* **Blank page or "failed to load"**: the API is not running or is on another port. The app expects it at http://localhost:8000.
* **Different numbers from the deck**: you are on another branch or an old build. `git status`, `git log -1`, rebuild with `npm run build`.
* **Wrong window size**: record at 1280×800 or larger; the layout is checked down to 320 px.
