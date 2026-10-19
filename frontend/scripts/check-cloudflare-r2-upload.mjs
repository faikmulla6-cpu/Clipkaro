import assert from "node:assert/strict";
import fs from "node:fs";
import { DirectStorageUploadError, isTransientStorageUploadError } from "../lib/direct-storage-upload.ts";

const internal = new DirectStorageUploadError(500, '<?xml version="1.0"?><Error><Code>InternalError</Code><Message>We encountered an internal error. Please try again.</Message></Error>');
assert.equal(internal.code, "InternalError");
assert.equal(internal.status, 500);
assert.equal(isTransientStorageUploadError(internal), true);
assert.match(internal.message, /Cloudflare R2/);
assert.ok(!internal.message.includes("<?xml"), "Raw storage XML must not be shown");
for (const status of [408, 429, 500, 502, 503, 504]) {
  assert.equal(isTransientStorageUploadError(new DirectStorageUploadError(status, "")), true);
}
for (const [status, code] of [[403,"SignatureDoesNotMatch"], [403,"AccessDenied"], [401,"Unauthorized"], [400,"InvalidRequest"]]) {
  const err = new DirectStorageUploadError(status, `<Error><Code>${code}</Code></Error>`);
  assert.equal(isTransientStorageUploadError(err), false, `Must never retry permanent auth/request failure ${status}/${code}`);
}
assert.equal(isTransientStorageUploadError(new Error("CORS or network failure")), false);
const upload = fs.readFileSync(new URL("../components/DirectUploadFallback.tsx", import.meta.url), "utf8");
assert.match(upload, /isTransientStorageUploadError\(cause\)/);
assert.match(upload, /Date\.parse\(session\.expires_at\)/, "Do not retry expired presigned URLs");
assert.match(upload, /await send\(xhr, file, true\)/, "Pass unchanged file and signed content type");
assert.match(upload, /\/uploads\/\$\{session\.upload_session_id\}\/complete/, "Only finalize original single upload session");
assert.ok(!upload.includes("session = await api<UploadSession>\""), "Avoid creating additional upload sessions inside retry");
console.log("Cloudflare R2 XML upload classification and single-retry safeguards: passed");
