# Waramoug customer portal: frontend

Next.js (App Router) + TypeScript + CSS modules. It talks to the Python API through a same-origin proxy
(`/api/*` -> `http://localhost:8000/*`, see `next.config.ts`; override with `BACKEND_URL`, which is read when the app is
built). The proxy waits up to five minutes for the API (`experimental.proxyTimeout`).

    npm install        # also copies the pdf.js worker into public/
    npm run dev        # http://localhost:3000

`src/lib/api-schema.d.ts` is generated from the API's OpenAPI document. Regenerate it after an API change, with the API
running: `npm run gen:api`.

## The flow

Documents (`/`) -> Reading (`/reading`) -> Review (`/review`) -> Goals (`/goals`) -> Invest (`/invest`) -> Compare (`/compare`).
The rail on the left has four steps (Documents, Review, Goals, Invest; Reading counts as Documents and Compare as Invest).
Steps that have not been reached are not links.

All state is in one provider (`src/lib/portal-state.tsx`) and is mirrored to `sessionStorage`, so going back or reloading
keeps the dropped PDF, the edits and confirmations, the goal answers, the last portfolio and the approvals
(`approved[plan_id][move_key]`). Nothing is sent twice: the PDF goes to the API once, when it is dropped.

- **Documents**: a drop area (a dropped or chosen PDF is `POST /portal/documents/upload`) and a "Use sample documents" link
  (`POST /portal/documents/sample`).
- **Reading**: the documents found, one about every half second, then Review.
- **Review**: the fields by document (from the API), each number editable, the PDF beside it (pdf.js; a field's `page` is the page
  of the one PDF and its `bbox` is in PDF points from the top-left). The flagged field must be confirmed or edited. Edits are sent
  as `overrides`.
- **Goals**: tap-to-select answers, prefilled from `GET /portal/defaults`. "Invest" posts `/portal/household` and then
  `/portal/invest` with the income event, the previous result and the words for what changed (`src/lib/change-label.ts`).
- **Invest** and **Compare** show the result (`Plan`).

The previous flow (Upload, Questions, Profile, Forecast, Plan, Compare and the showcase) is kept, not routed, in
`src/app/_legacy/`, with its components in `src/components/*` and its browser checks in `e2e/legacy/`.

## Checks

    npx tsc --noEmit && npx eslint src e2e scripts
    BACKEND_URL=http://localhost:8000 npx next build

Browser checks (Playwright; the API on :8000 and `next start` running; env: `BASE_URL`, default http://localhost:3000, and
`CHROMIUM_PATH` if Playwright's own browser is not installed):

    npm run e2e        # documents, reading, review, goals, navigation, wording
    node e2e/review.mjs   # or any one of them

The PDF viewer loads pdf.js's legacy build (it bundles the polyfills pdf.js 6 needs); the matching worker is copied to
`public/pdf.worker.min.mjs` by `npm install` and is git-ignored.
