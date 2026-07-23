import { getBackendOrigin } from "@/lib/backendOrigin";

export async function proxyBackendEventStream(
  request: Request,
  backendPath: string,
  unavailableMessage: string,
): Promise<Response> {
  const upstreamUrl = `${getBackendOrigin()}${backendPath}`;
  const lastEventId = request.headers.get("last-event-id");

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, {
      headers: {
        Accept: "text/event-stream",
        ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
      },
      cache: "no-store",
      signal: request.signal,
    });
  } catch {
    return new Response(unavailableMessage, { status: 502 });
  }

  if (!upstream.ok || upstream.body == null) {
    return new Response(unavailableMessage, {
      status: upstream.status || 502,
    });
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
