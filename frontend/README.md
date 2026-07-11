# Frontend

Next.js frontend for the Food Recall Monitor platform.

## Prerequisites

- Node.js 20+
- npm
- Backend API running (default port 8080; see `backend/README.md`)

## Setup

```bash
npm install
```

Create `.env.local` when you need non-default API routing (see `.env.example`):

```bash
# Browser-facing API base (use /api so the browser hits this Next server)
NEXT_PUBLIC_API_URL=/api

# Where Next rewrites /api/* on the server (change the port as needed)
BACKEND_URL=http://localhost:8080

# Optional: hosts allowed for Next.js HMR when opening the UI via Tailscale/LAN
# ALLOWED_DEV_ORIGINS=100.x.y.z
```

Examples:

| Setup | `.env.local` |
|-------|----------------|
| Default local backend on 8080 | `NEXT_PUBLIC_API_URL=/api` and `BACKEND_URL=http://localhost:8080` (or omit `BACKEND_URL`) |
| Second backend on 8081 | `NEXT_PUBLIC_API_URL=/api` and `BACKEND_URL=http://localhost:8081` |
| Browser talks to backend directly | `NEXT_PUBLIC_API_URL=http://localhost:8080/api` (rewrites unused) |
| Remote UI over Tailscale | Set `ALLOWED_DEV_ORIGINS` to your Tailscale IP (keep this in `.env.local` only) |

`NEXT_PUBLIC_API_URL` is for the browser. `BACKEND_URL` is server-only and must be the FastAPI origin **without** a trailing `/api`. Do not commit real host IPs — put them in `.env.local`.

## Scripts

```bash
npm run dev              # Start development server at http://localhost:3000
npm run dev -- --test    # Start with mock data (no backend required)
npm run build            # Create production build
npm run start            # Serve production build
npm run lint             # Run ESLint
```

With `NEXT_PUBLIC_API_URL=/api`, the browser calls `/api/*` on the Next server; Next rewrites those to `${BACKEND_URL}/api/*`.
