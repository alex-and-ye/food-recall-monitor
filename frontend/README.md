# Frontend

Next.js operator dashboard for **Food Recall Monitor**. It browses official food-recall alerts and early-warning incidents from the FastAPI backend, shows aggregate stats and a 3D globe of geocoded recalls, surfaces pipeline warnings, and keeps list/stats views fresh via Server-Sent Events (SSE).

Browser API calls typically go to `/api` on this Next server; Next **rewrites** those to the FastAPI origin. Long-lived SSE streams use dedicated App Router handlers under `/api/stream/*` so they do not shadow REST list endpoints.

For the full Docker Compose stack (Chroma + backend + frontend), see the [repository root README](../README.md).

---

## Purpose

At a high level the frontend:

1. **Official recalls** — list, filter, paginate, and open detail pages for structured alerts; live-refresh when the alerts collection changes.
2. **Early warnings** — list, filter, and open detail pages for discovered food-safety incidents; live-refresh via the incidents SSE stream.
3. **Exploration & ops** — alert statistics, a WebGL globe of geocoded official recalls, and acknowledgeable pipeline warnings.
4. **API edge** — proxy browser traffic to FastAPI (`rewrites` for REST; Node `http`/`https` proxies for SSE without Undici body timeouts).

---

## Folder and file structure

```text
frontend/
├── package.json            # Scripts (dev/build/start/lint) and dependencies
├── package-lock.json
├── next.config.ts          # standalone output, optional LAN origins, /api → backend rewrites
├── tsconfig.json           # TypeScript; `@/*` → `./src/*`
├── postcss.config.mjs      # Tailwind CSS 4 PostCSS plugin
├── eslint.config.mjs       # ESLint (eslint-config-next)
├── next-env.d.ts           # Next.js generated TypeScript refs
├── Dockerfile              # Multi-stage Node image; standalone server on :3000
├── .env.example            # Template for NEXT_PUBLIC_API_URL, BACKEND_URL, ALLOWED_DEV_ORIGINS
├── .dockerignore
├── .gitignore
│
├── scripts/
│   └── dev.mjs             # `npm run dev` → `next dev` (forwards CLI args)
│
└── src/
    ├── app/                # Next.js App Router: pages + SSE route handlers
    │   ├── layout.tsx      # Root layout: metadata + DashboardShell
    │   ├── globals.css     # Global / Tailwind styles
    │   ├── page.tsx        # Home: official alerts feed
    │   ├── alerts/[id]/page.tsx
    │   ├── early-warnings/page.tsx
    │   ├── incidents/[id]/page.tsx
    │   ├── stats/page.tsx
    │   ├── globe/page.tsx
    │   ├── warnings/page.tsx
    │   └── api/stream/     # SSE proxies (not rewritten as plain /api/* REST)
    │       ├── alerts/route.ts      # → GET /api/alerts/events
    │       └── incidents/route.ts  # → GET /api/incidents/events
    │
    ├── components/         # Shared UI (shell, cards, toolbars, globe, …)
    ├── hooks/              # SSE change-stream hooks (alerts / incidents)
    ├── lib/                # Search URL helpers, UI tokens, backend origin, SSE proxy
    ├── services/api/       # Browser HTTP client + ApiError
    └── types/              # Domain types aligned with backend payloads
```

### Package roles

| Package / area | Role |
| --- | --- |
| `src/app/` | Routes and layouts; thin pages that wire hooks, API calls, and components |
| `src/app/api/stream/` | Node runtime SSE proxies to FastAPI event endpoints |
| `src/components/` | Presentational and chrome UI reused across pages |
| `src/hooks/` | Client hooks that subscribe to SSE and trigger debounced refreshes |
| `src/lib/` | Pure helpers (search ↔ URL, shared class names, risk styles) and server-side proxy utilities |
| `src/services/api/` | Typed `fetch` wrappers against `NEXT_PUBLIC_API_URL` |
| `src/types/` | Shared TypeScript models for alerts, incidents, and warnings |
| `scripts/` | Local tooling entrypoints (dev server wrapper) |

### Notable files

| Path | Purpose |
| --- | --- |
| `next.config.ts` | `output: "standalone"` for Docker; `BACKEND_URL` rewrites; optional `ALLOWED_DEV_ORIGINS` |
| `src/services/api/client.ts` | `getAlerts`, `getIncidents`, stats/version, warnings acknowledge, SSE URL helpers |
| `src/lib/proxyBackendEventStream.ts` | Raw Node HTTP(S) SSE proxy (avoids Undici’s default body timeout) |
| `src/lib/backendOrigin.ts` | Resolves `BACKEND_URL` for server-side handlers |
| `src/lib/alertSearch.ts` / `incidentSearch.ts` | Form state ↔ URL query ↔ API query params |
| `src/components/DashboardShell.tsx` | Sidebar + header chrome; map-page layout tweaks |
| `src/components/GlobeComponent.tsx` | `react-globe.gl` / Three.js pin map (client-only) |

---

## Architecture

### Layering

```text
Browser
    ↓
app/* pages (client components)
    ↓
hooks/  ·  services/api/client  ·  components/
    ↓
NEXT_PUBLIC_API_URL (usually /api)
    ↓
┌───────────────────────────────┬────────────────────────────────┐
│ next.config rewrites          │ app/api/stream/* route handlers │
│ /api/* → BACKEND_URL/api/*    │ → proxyBackendEventStream       │
│ (REST: alerts, incidents, …)  │ → BACKEND_URL /api/*/events     │
└───────────────────────────────┴────────────────────────────────┘
    ↓
FastAPI backend (:8080)
```

Pages import **types** and **lib** helpers for filters/URL state, call **services/api** for JSON, and use **hooks** for live updates. Components stay presentation-focused; they do not talk to FastAPI directly except where the shell needs a lightweight summary (e.g. sidebar warning badge via `getWarningsSummary`).

### Request path (REST)

```text
Page / component
  → services/api/client (getAlerts, getIncidents, …)
  → fetch(`${NEXT_PUBLIC_API_URL}/…`)
  → Next rewrite → `${BACKEND_URL}/api/…`
  → FastAPI routes (see backend/README.md)
```

| UI surface | Primary client calls | Backend prefix |
| --- | --- | --- |
| `/` (alerts feed) | `getAlerts` | `/api/alerts` |
| `/alerts/[id]` | `getAlertById` | `/api/alerts/{id}` |
| `/stats` | `getAlertStats` | `/api/alerts/stats` |
| `/globe` | `getAlerts` | `/api/alerts` |
| `/early-warnings` | `getIncidents` | `/api/incidents` |
| `/incidents/[id]` | `getIncidentById` | `/api/incidents/{id}` |
| `/warnings` | `getWarnings`, acknowledge* | `/api/warnings` |
| Sidebar badge | `getWarningsSummary` | `/api/warnings/summary` |

### Live updates (SSE)

```text
Page mounts useAlertsChangeStream / useIncidentsChangeStream
  → EventSource(getAlertsEventsUrl | getIncidentsEventsUrl)
  → GET /api/stream/alerts|incidents  (Next route handlers)
  → proxyBackendEventStream
  → GET /api/alerts/events | /api/incidents/events  (FastAPI)
  → debounced refresh callback → re-fetch list/stats via REST
```

SSE is deliberately **not** under `/api/alerts` or `/api/incidents` so those paths keep rewriting to FastAPI list endpoints. Proxies use the Node runtime (`runtime = "nodejs"`) and raw `http`/`https` so long-lived streams are not killed by Undici’s default body timeout.

### App shell

```text
layout.tsx
  → DashboardShell
       → Sidebar (nav + warnings summary)
       → Header
       → {children}  (route page)
```

The globe route (`/globe`) uses a full-viewport dark layout; other pages use the standard padded content column.

### Key config touchpoints

- **Browser API base:** `NEXT_PUBLIC_API_URL` (prefer `/api` so the browser always hits this Next origin).
- **Rewrite / SSE upstream:** `BACKEND_URL` — FastAPI origin **without** a trailing `/api`.
- **LAN / Tailscale HMR:** `ALLOWED_DEV_ORIGINS` (comma-separated hosts) in `.env.local` only.
- **Docker:** `BACKEND_URL` and `NEXT_PUBLIC_API_URL` are **build-time** args on the frontend image (rewrites are baked into the standalone build).

---

## Setup

### Prerequisites

1. **Node.js 20+** and **npm**.
2. **Backend API** reachable (default `http://localhost:8080`; see [backend README](../backend/README.md)).
3. Optional: Tailscale/LAN access to the Next dev server — set `ALLOWED_DEV_ORIGINS` if HMR fails from a non-localhost host.

### Local development

```bash
cd frontend
npm install

copy .env.example .env.local   # Windows
# cp .env.example .env.local   # macOS / Linux
# Edit .env.local if the backend is not on localhost:8080
```

Start the UI (backend should already be running for live data):

```bash
npm run dev
# → http://localhost:3000
```

With `NEXT_PUBLIC_API_URL=/api`, the browser calls `/api/*` on the Next server; Next rewrites those to `${BACKEND_URL}/api/*`. SSE uses `/api/stream/*` route handlers, which call the same `BACKEND_URL`.

### Environment variables

Copy `.env.example` to `.env.local`. Common values:

| Variable | Description | Default |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | Browser-facing API base (path or absolute URL) | `/api` |
| `BACKEND_URL` | Server-side FastAPI origin for rewrites and SSE proxies (no `/api` suffix) | `http://localhost:8080` |
| `ALLOWED_DEV_ORIGINS` | Comma-separated hosts allowed for Next.js HMR over LAN/Tailscale | _(empty)_ |

Examples:

| Setup | `.env.local` |
| --- | --- |
| Default local backend on 8080 | `NEXT_PUBLIC_API_URL=/api` and `BACKEND_URL=http://localhost:8080` (or omit `BACKEND_URL`) |
| Second backend on 8081 | `NEXT_PUBLIC_API_URL=/api` and `BACKEND_URL=http://localhost:8081` |
| Browser talks to backend directly | `NEXT_PUBLIC_API_URL=http://localhost:8080/api` (rewrites unused for REST; SSE still needs working stream routes or a direct backend EventSource URL) |
| Remote UI over Tailscale | Set `ALLOWED_DEV_ORIGINS` to your Tailscale IP (keep this in `.env.local` only) |

`NEXT_PUBLIC_API_URL` is for the browser. `BACKEND_URL` is server-only and must be the FastAPI origin **without** a trailing `/api`. Do not commit real host IPs — put them in `.env.local`.

### Scripts

```bash
npm run dev      # Development server at http://localhost:3000
npm run build    # Production build (standalone output)
npm run start    # Serve the production build
npm run lint     # ESLint
```

### Docker

- **Full stack:** from the repo root, `docker compose up --build` (see [root README](../README.md)). Compose builds the frontend with `BACKEND_URL=http://backend:8080` so the container rewrites to the backend service name.
- **Frontend image alone:** `Dockerfile` is a multi-stage Node build (`npm ci` → `next build` with `output: "standalone"`) and runs `node server.js` on port **3000**.

---

## Related docs

- [Backend README](../backend/README.md) — FastAPI APIs, pipelines, Chroma, Ollama
- [Root README](../README.md) — Docker Compose, monorepo env table, ports
