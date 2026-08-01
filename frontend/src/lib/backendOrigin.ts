/**
 * Resolves the server-side FastAPI origin used by Next.js route handlers.
 */

/**
 * Returns the backend base URL without a trailing slash (no `/api` suffix).
 *
 * @returns Absolute origin from `BACKEND_URL`, or `http://localhost:8080`.
 */
export function getBackendOrigin(): string {
  return (process.env.BACKEND_URL ?? "http://localhost:8080").replace(/\/$/, "");
}
