# Frontend

Next.js frontend for the Food Recall Monitor platform.

## Prerequisites

- Node.js 20+
- npm
- Backend API running on port 8080 (see `backend/README.md`)

## Setup

```bash
npm install
```

Optional: set `NEXT_PUBLIC_API_URL` in `.env.local` if the backend is not on `http://localhost:8080`.

## Scripts

```bash
npm run dev              # Start development server at http://localhost:3000
npm run dev -- --test    # Start with mock data (no backend required)
npm run build            # Create production build
npm run start            # Serve production build
npm run lint             # Run ESLint
```

API requests from the browser can use `/api/*`; Next.js rewrites those to the FastAPI backend.
