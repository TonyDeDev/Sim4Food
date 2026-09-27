import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Browser requests go through Next.js so the session cookie and backend are
  // same-origin from the UI's perspective. This avoids CORS masking useful
  // backend errors during local development.
  async rewrites() {
    const backend = (process.env.BACKEND_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '')
    return [{ source: '/backend-api/:path*', destination: `${backend}/:path*` }]
  },
};

export default nextConfig;
