/** Fail-closed classification for Cloudflare R2 signed object PUT responses.
 * Never display or log the signed URL, token, or provider response body.
 */
export class DirectStorageUploadError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, body: string) {
    const code = /<Code>\s*([A-Za-z0-9_-]{1,64})\s*<\/Code>/.exec(body.slice(0, 2048))?.[1] || "";
    const message = code === "InternalError" || status >= 500
      ? "Cloudflare R2 had a temporary upload error. Please try again shortly."
      : code === "RequestTimeout" || status === 408
        ? "Cloudflare R2 upload timed out. Check your connection and try again."
        : code === "SlowDown" || status === 429
          ? "Cloudflare R2 is busy. Please try again shortly."
          : code === "SignatureDoesNotMatch" || code === "AccessDenied" || status === 403
            ? "Private storage rejected the upload authorization. Please retry with a new upload session."
            : "Cloudflare R2 did not accept this upload (HTTP " + status + "). Please try again.";
    super(message);
    this.name = "DirectStorageUploadError";
    this.status = status;
    this.code = code;
  }
}

/** A single retry of the same bounded, signed PUT is safe for transient R2 errors. */
export function isTransientStorageUploadError(error: unknown): boolean {
  if (!(error instanceof DirectStorageUploadError)) return false;
  return ["InternalError", "RequestTimeout", "SlowDown", "ServiceUnavailable"].includes(error.code)
    || [408, 429, 500, 502, 503, 504].includes(error.status);
}
