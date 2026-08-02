/**
 * Proxies long-lived Server-Sent Events (SSE) responses from the FastAPI backend
 * into Next.js route handlers without Undici's default body timeout.
 */

import * as http from "node:http";
import * as https from "node:https";
import { getBackendOrigin } from "@/lib/backendOrigin";

/**
 * Proxies a long-lived Server-Sent-Events response from FastAPI.
 *
 * Uses Node's raw `http`/`https` client instead of the global `fetch` (undici).
 * Undici applies a default 300s body timeout that forcibly kills streaming
 * responses left open longer than that—exactly what an SSE connection does.
 * That timeout was aborting the upstream socket and also appeared to disrupt
 * sibling keep-alive requests to the same backend host (surfaced as random
 * ECONNRESET / "socket hang up" on other `/api/*` rewrites). Plain
 * `http.request` has no such body timeout.
 *
 * @param request - Incoming Next.js request (for abort signal and Last-Event-ID).
 * @param backendPath - Backend path including `/api`, e.g. `/api/alerts/events`.
 * @param unavailableMessage - Body text returned on upstream failure.
 * @returns Streaming `text/event-stream` response, or an error status response.
 */
export async function proxyBackendEventStream(
  request: Request,
  backendPath: string,
  unavailableMessage: string,
): Promise<Response> {
  const upstreamUrl = new URL(`${getBackendOrigin()}${backendPath}`);
  const lastEventId = request.headers.get("last-event-id");
  const client = upstreamUrl.protocol === "https:" ? https : http;

  const upstream = await new Promise<http.IncomingMessage | null>(
    (resolve) => {
      const req = client.request(
        upstreamUrl,
        {
          method: "GET",
          headers: {
            Accept: "text/event-stream",
            ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
          },
          // No timeout: this connection is meant to stay open indefinitely.
          timeout: 0,
        },
        (res) => resolve(res),
      );
      req.on("error", () => resolve(null));
      request.signal.addEventListener("abort", () => req.destroy());
      req.end();
    },
  );

  if (upstream == null || upstream.statusCode == null) {
    return new Response(unavailableMessage, { status: 502 });
  }

  if (upstream.statusCode < 200 || upstream.statusCode >= 300) {
    upstream.resume();
    return new Response(unavailableMessage, { status: upstream.statusCode });
  }

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      upstream.on("data", (chunk: Buffer) => {
        try {
          controller.enqueue(new Uint8Array(chunk));
        } catch {
          // Controller already closed (client disconnected); ignore.
        }
      });
      upstream.on("end", () => {
        try {
          controller.close();
        } catch {
          // Already closed.
        }
      });
      upstream.on("error", () => {
        try {
          controller.error(new Error(unavailableMessage));
        } catch {
          // Already settled.
        }
      });
    },
    cancel() {
      upstream.destroy();
    },
  });

  request.signal.addEventListener("abort", () => upstream.destroy());

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
    },
  });
}
