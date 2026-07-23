/** Server-side FastAPI origin used by Next route handlers (no /api suffix). */
export function getBackendOrigin(): string {
  return (process.env.BACKEND_URL ?? "http://localhost:8080").replace(/\/$/, "");
}
