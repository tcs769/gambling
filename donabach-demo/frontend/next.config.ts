import type { NextConfig } from "next";

// The browser talks to the Python API through this same-origin proxy: no CORS to configure, and
// the PDF viewer can fetch documents directly. Point BACKEND_URL elsewhere if the API is not on
// localhost:8000.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// Cache Components (and the <Activity> route retention it brings) is deliberately off. This app
// is a client-driven wizard whose state lives in one provider, and it renders PDF canvases and
// responsive charts that misbehave when a route is kept alive while hidden.
const nextConfig: NextConfig = {
  // The proxy gives up on the API after 30 seconds by default. A plan in the liability-matched style takes 6 to 8 seconds on an
  // idle machine and several times that on a busy one, so the app waits for it for as long as it takes (a plan that the API
  // really cannot make is reported by the API itself).
  experimental: { proxyTimeout: 300_000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/:path*` }];
  },
};

export default nextConfig;
