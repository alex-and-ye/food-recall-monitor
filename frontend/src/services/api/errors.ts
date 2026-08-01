/**
 * Typed HTTP error raised by the browser API client for non-OK responses.
 */

/**
 * Error representing a failed API response, including HTTP status code.
 */
export class ApiError extends Error {
  /**
   * @param message - Human-readable error detail (often from FastAPI `detail`).
   * @param status - HTTP status code from the failed response.
   */
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
