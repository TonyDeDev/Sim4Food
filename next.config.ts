import type { NextConfig } from "next";

// Server-only: next.config.ts runs on the server, so this never needs (and
// must not get) a NEXT_PUBLIC_ prefix. Same-origin proxy for the FastAPI
// backend: the browser calls /py/... on this app's own origin, Next.js
// forwards it server-to-server to FastAPI, so the httpOnly `session` cookie
// set by src/app/api/auth/{login,signup}/route.ts reaches the backend in
// every environment - not just when both sides happen to be "localhost".
const BACKEND_URL = (process.env.BACKEND_URL || "http://localhost:8000").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/py/:path*",
        destination: `${BACKEND_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
