import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";

const MAX_BYTES = 2 * 1024 * 1024;
const baseUrlValue = String(process.env.ADMIN_API_BASE_URL || "").trim();
const serviceToken = String(process.env.ADMIN_API_SERVICE_TOKEN || "").trim();

if (!baseUrlValue) throw new Error("ADMIN_API_BASE_URL is required.");
const baseUrl = new URL(baseUrlValue);
if (baseUrl.protocol !== "http:" || !new Set(["127.0.0.1", "localhost", "::1"]).has(baseUrl.hostname)) {
  throw new Error("Stage 2I rehearsal is hard-locked to an HTTP loopback target.");
}

const contract = JSON.parse(await readFile(new URL("../docs/founder-admin-contract-v1.json", import.meta.url), "utf8"));
if (contract.contract !== "clipkaro-founder-admin" || contract.version !== 1 || contract.mode !== "read_only") {
  throw new Error("Unexpected Founder Admin contract identity or mode.");
}
if (!Array.isArray(contract.write_methods_allowed) || contract.write_methods_allowed.length !== 0) {
  throw new Error("RC rehearsal refuses a contract that declares write methods.");
}
if (!Array.isArray(contract.endpoints) || contract.endpoints.length !== 9 || contract.endpoints.some((item) => item.method !== "GET")) {
  throw new Error("RC rehearsal requires exactly nine GET-only endpoints.");
}
if (serviceToken.length < Number(contract.authentication?.configured_token_min_length || 48)) {
  throw new Error("RC service token is weaker than the contract minimum.");
}

const resolvePath = (endpoint) => {
  const template = endpoint.path || endpoint.path_template;
  if (!template) throw new Error("Contract endpoint is missing a path.");
  return template.replace("{user_id}", "demo-user");
};

async function request(path, token) {
  const requestId = randomUUID();
  const response = await fetch(new URL(path, baseUrl), {
    method: "GET",
    cache: "no-store",
    redirect: "error",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
      "X-Request-ID": requestId,
      "X-ClipKaro-Admin-Client": "founder-console-v1",
    },
    signal: AbortSignal.timeout(8_000),
  });

  if (response.headers.get("x-request-id") !== requestId) {
    throw new Error(`${path} did not echo the exact X-Request-ID.`);
  }
  const cacheControl = String(response.headers.get("cache-control") || "").toLowerCase();
  if (!cacheControl.includes("no-store")) throw new Error(`${path} is missing Cache-Control: no-store.`);
  const contentType = String(response.headers.get("content-type") || "").toLowerCase();
  if (!contentType.includes("application/json")) throw new Error(`${path} did not return JSON.`);

  const text = await response.text();
  if (Buffer.byteLength(text, "utf8") > MAX_BYTES) throw new Error(`${path} exceeded the RC response-size ceiling.`);
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    throw new Error(`${path} returned invalid JSON.`);
  }
  return { response, body, text };
}

const firstPath = resolvePath(contract.endpoints[0]);
const rejected = await request(firstPath, "stage2i-invalid-token");
if (rejected.response.status !== Number(contract.failure_modes?.unauthorized || 401)) {
  throw new Error(`Invalid token returned HTTP ${rejected.response.status}, expected 401.`);
}

const forbiddenMarkers = [
  '"password_hash"',
  '"billing_reference"',
  '"session_version"',
  '"razorpay_key_secret"',
  '"access_token"',
  '"refresh_token"',
  '"signed_url"',
  '"object_key"',
  '"database_url"',
];

const verified = [];
for (const endpoint of contract.endpoints) {
  const path = resolvePath(endpoint);
  const { response, body, text } = await request(path, serviceToken);
  if (response.status !== 200) throw new Error(`${path} returned HTTP ${response.status}: ${text.slice(0, 300)}`);
  if (text.includes(serviceToken)) throw new Error(`${path} echoed the service token.`);
  for (const marker of forbiddenMarkers) {
    if (text.includes(marker)) throw new Error(`${path} exposed forbidden marker ${marker}.`);
  }
  if (path.endsWith("/overview") && body.mode !== "read_only") throw new Error("Overview did not report read_only mode.");
  if (path.endsWith("/system-health") && body.external_provider_probes !== "not_run") {
    throw new Error("System health unexpectedly performed external provider probes.");
  }
  verified.push(path);
}

console.log(JSON.stringify({
  stage: "2I",
  release_candidate: "founder-admin-rc1",
  contract: contract.contract,
  version: contract.version,
  mode: contract.mode,
  verified_endpoints: verified.length,
  invalid_token_status: rejected.response.status,
  target: `${baseUrl.protocol}//${baseUrl.host}`,
  external_provider_probes: "not_run",
}, null, 2));
