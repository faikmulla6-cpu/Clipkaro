// Enforce source size limits and multipart endpoints across UI and backend.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const backend = readFileSync(resolve(root, "backend/app/services/upload_limits.py"), "utf8");
const frontend = readFileSync(resolve(root, "frontend/lib/upload-policy.ts"), "utf8");
const limits = { free: 500, mini_pass: 500, creator: 1024, growth: 2048, pro: 4096, agency: 4096 };
for (const [name, size] of Object.entries(limits)) {
  const matchBackend = backend.includes('"' + name + '": ' + size);
  const matchFrontend = frontend.includes(name + ': ' + size);
  if (!matchBackend || !matchFrontend) {
    throw new Error("Mismatched source upload MB limit for " + name + ": " + size);
  }
}
const client = readFileSync(resolve(root, "frontend/components/DirectUploadFallback.tsx"), "utf8");
const api = readFileSync(resolve(root, "backend/app/api/cloud_uploads.py"), "utf8");
for (const tag of ["MULTIPART", "part_size", "/abort", "/complete"]) {
  if (!client.includes(tag) || !api.includes(tag)) {
    throw new Error("Missing matching multipart contract: " + tag);
  }
}
if (!client.includes("object_storage_provider") || !api.includes("object_storage_provider_name")) {
  throw new Error("Direct upload cannot safely discover the server-side storage provider.");
}
// Keep the public YouTube link import closed until the source pipeline is reliable.
const uploadStudio = readFileSync(resolve(root, "frontend/components/UploadStudio.tsx"), "utf8");
const home = readFileSync(resolve(root, "frontend/components/HomeExperience.tsx"), "utf8");
for (const required of [
  "const YOUTUBE_URL_IMPORT_AVAILABLE = false;",
  "if (!YOUTUBE_URL_IMPORT_AVAILABLE) return;",
  "YOUTUBE_URL_IMPORT_AVAILABLE ? (",
  'data-youtube-import-status="coming-soon"',
  'href="#clipkaro-file-upload"',
  'id="clipkaro-file-upload"',
  "<DirectUploadFallback",
]) {
  if (!uploadStudio.includes(required)) {
    throw new Error("YouTube Coming Soon release gate or file-upload fallback missing: " + required);
  }
}
if (!home.includes("YOUTUBE URL IMPORT · COMING SOON") || !home.includes("Upload your original video.")) {
  throw new Error("Home page must accurately disclose YouTube URL import availability.");
}
console.log("Plan-aware multipart upload and YouTube Coming Soon contracts passed.");
