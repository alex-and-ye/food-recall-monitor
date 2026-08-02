/**
 * Next.js route handler that proxies the FastAPI early-warning incidents SSE stream.
 *
 * Mounted under `/api/stream/*` so it does not shadow the `/api/incidents` list
 * rewrite to the backend.
 */

import { proxyBackendEventStream } from "@/lib/proxyBackendEventStream";

/** Always compute a fresh response (no static caching of the stream). */
export const dynamic = "force-dynamic";

/** Use the Node.js runtime so raw `http`/`https` streaming is available. */
export const runtime = "nodejs";

/**
 * Proxies `GET /api/incidents/events` from the backend as `text/event-stream`.
 *
 * @param request - Incoming Next.js request.
 * @returns Proxied SSE response or an upstream error response.
 */
export async function GET(request: Request): Promise<Response> {
  return proxyBackendEventStream(
    request,
    "/api/incidents/events",
    "Upstream incident events unavailable",
  );
}
