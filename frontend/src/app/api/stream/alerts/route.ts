import { proxyBackendEventStream } from "@/lib/proxyBackendEventStream";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Proxies FastAPI alert SSE. Kept under /api/stream/* so it does not shadow
 * the /api/alerts list rewrite to the backend.
 */
export async function GET(request: Request): Promise<Response> {
  return proxyBackendEventStream(
    request,
    "/api/alerts/events",
    "Upstream alert events unavailable",
  );
}
