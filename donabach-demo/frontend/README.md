# Donabach demo: frontend

Next.js (App Router) + TypeScript + Recharts. It talks to the Python API through a same-origin proxy
(`/api/*` -> `http://localhost:8000/*`, see `next.config.ts`; override with `BACKEND_URL`).

    npm install        # also copies the pdf.js worker into public/
    npm run dev        # http://localhost:3000

`src/lib/api-schema.d.ts` is generated from the backend's OpenAPI document. Regenerate it after changing an
API model, with the backend running: `npm run gen:api`.
