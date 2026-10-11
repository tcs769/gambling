import type { NextConfig } from "next";

// The browser talks to the Python API through this same-origin proxy: no CORS to configure, and
// the PDF viewer can fetch documents directly. Point BACKEND_URL elsewhere if the API is not on
// localhost:8000.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// Cache Components (and the <Activity> route retention it brings) is deliberately off. This app
// is a client-driven wizard whose state lives in one provider, and it renders PDF canvases and
// responsive charts that misbehave when a route is kept alive while hidden.
const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/:path*` }];
  },
};

export default nextConfig;
