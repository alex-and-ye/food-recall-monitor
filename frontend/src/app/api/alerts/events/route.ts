import { proxyBackendEventStream } from "@/lib/proxyBackendEventStream";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Proxies FastAPI alert SSE so EventSource is not buffered by Next rewrites. */
export async function GET(request: Request): Promise<Response> {
  return proxyBackendEventStream(
    request,
    "/api/alerts/events",
    "Upstream alert events unavailable",
  );
}
