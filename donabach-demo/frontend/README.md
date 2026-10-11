# Donabach demo: frontend

Next.js (App Router) + TypeScript + Recharts. It talks to the Python API through a same-origin proxy
(`/api/*` -> `http://localhost:8000/*`, see `next.config.ts`; override with `BACKEND_URL`).

    npm install        # also copies the pdf.js worker into public/
    npm run dev        # http://localhost:3000

`src/lib/api-schema.d.ts` is generated from the backend's OpenAPI document. Regenerate it after changing an
API model, with the backend running: `npm run gen:api`.

    npm run e2e        # walk the whole demo in Chromium and check it (API and app must be running)
                       # env: BASE_URL (default http://localhost:3000), OUT_DIR (screenshots), CHROMIUM_PATH
    npm run typecheck  # tsc --noEmit
    npm run check:colors  # the chart series colours: contrast on the panel and colour-blind separation, all four pairs

The PDF viewer loads pdf.js's legacy build (it bundles the polyfills pdf.js 6 needs); the matching worker is copied to
`public/pdf.worker.min.mjs` by `npm install` and is git-ignored.

The e2e reads its expectations from the API's own responses, including the year-by-year plan (below). The API keeps
finished year-by-year plans in memory, so against an API that has already planned the households the e2e uses, the
"Refining plan…" checks find the plan ready at once and say so in a note: start the API fresh (it precomputes the
demo household's plan at startup, which the e2e waits for, up to 60 s) to exercise them for real. A production build
(`BACKEND_URL=http://localhost:8000 npm run build && npm start`) is what the e2e is run against.

## The year-by-year plan

`POST /plan` and `POST /plan/whatif` answer with the fixed-strategy plan at once. Its year-by-year (adaptive) part
is either in the same response (`plan.adaptive`, when the API already has it: the demo household, repeated requests)
or a background job (`plan.adaptive_job`) that the app polls every 700 ms (`GET /plan/adaptive/{id}`). The state
lives in `src/lib/state.tsx`: each plan keeps its own year-by-year state (`ready`, `refining` with the job's
progress, `failed` with the API's error text), so a newer plan never shows an older plan's year-by-year part, and
polling a job stops as soon as the plan it belongs to is replaced (a new what-if, a reset, new answers).

While a job runs the Plan and Comparison screens show the fixed plan and say "Refining plan…" (a pill beside the
title; on Comparison also a placeholder panel that holds the room of the panels that will replace it). The Plan
table switches between "Year-by-year plan" (the default once it is ready) and "Fixed strategy"; the years where the
planner changed something from the fixed strategy are tinted and tagged "Changed: …", and the year drawer shows
"Why this year" from the plan's own `decisions` and `year_details`. A what-if shows a "What changed in the plan"
panel against the plan it started from. `src/lib/adaptive.ts` holds the words and the before/after arithmetic.

The fourth chart colour (the adaptive planner, drawn dotted) and how it was chosen are documented next to the
series tokens in `src/app/globals.css`; `npm run check:colors` covers all four.
