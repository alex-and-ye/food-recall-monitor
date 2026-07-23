import type { NextConfig } from "next";

// Server-side only: where Next proxies /api/* (any host/port, e.g. 8080 or 8081).
// Do not reuse NEXT_PUBLIC_API_URL here - that is the browser-facing API base.
const backendUrl = (
  process.env.BACKEND_URL ?? "http://localhost:8080"
).replace(/\/$/, "");

// Comma-separated hosts allowed to use Next.js dev assets (HMR) over LAN/Tailscale.
// Keep real IPs in .env.local - never commit them.
const allowedDevOrigins = (process.env.ALLOWED_DEV_ORIGINS ?? "")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  ...(allowedDevOrigins.length > 0 ? { allowedDevOrigins } : {}),
  async rewrites() {
    // App route handlers under app/api/*/events take precedence over these
    // rewrites. Those handlers stream SSE without buffering; plain rewrites
    // can hold event-stream responses until the connection closes.
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
