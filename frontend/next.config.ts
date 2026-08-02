/**
 * Next.js configuration for the Food Recall Monitor frontend: standalone
 * Docker output, optional LAN/Tailscale dev origins, and `/api` rewrites to
 * the FastAPI backend.
 */

import type { NextConfig } from "next";

/** Server-side FastAPI origin for `/api/*` rewrites (no trailing slash). */
const backendUrl = (
  process.env.BACKEND_URL ?? "http://localhost:8080"
).replace(/\/$/, "");

/**
 * Comma-separated hosts allowed to use Next.js dev assets (HMR) over LAN/Tailscale.
 */
const allowedDevOrigins = (process.env.ALLOWED_DEV_ORIGINS ?? "")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  /** Smaller production image for Docker (see `frontend/Dockerfile`). */
  output: "standalone",
  ...(allowedDevOrigins.length > 0 ? { allowedDevOrigins } : {}),
  /**
   * Rewrites browser `/api/*` calls to the backend.
   * SSE proxies live under `app/api/stream/*` so they never shadow
   * `/api/alerts` or `/api/incidents` list endpoints rewritten here.
   */
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
