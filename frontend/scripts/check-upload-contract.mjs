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
console.log("Plan-aware multipart upload contract passed.");
