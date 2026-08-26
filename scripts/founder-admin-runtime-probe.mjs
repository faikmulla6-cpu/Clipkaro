import { readFile } from "node:fs/promises";

const baseUrlValue = String(process.env.ADMIN_API_BASE_URL || "").trim();
const serviceToken = String(process.env.ADMIN_API_SERVICE_TOKEN || "").trim();

if (!baseUrlValue) {
  throw new Error("ADMIN_API_BASE_URL is required for the runtime probe.");
}

const baseUrl = new URL(baseUrlValue);
const loopbackHosts = new Set(["127.0.0.1", "localhost", "::1"]);
if (baseUrl.protocol !== "http:" || !loopbackHosts.has(baseUrl.hostname)) {
  throw new Error("Runtime probe is hard-locked to a local HTTP loopback target.");
}

const contractCandidates = [
  new URL("../contracts/founder-admin-v1.json", import.meta.url),
  new URL("../docs/founder-admin-contract-v1.json", import.meta.url),
];

let contract;
for (const candidate of contractCandidates) {
  try {
    contract = JSON.parse(await readFile(candidate, "utf8"));
    break;
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}
if (!contract) throw new Error("Founder Admin contract manifest was not found.");

if (contract.contract !== "clipkaro-founder-admin" || contract.version !== 1 || contract.mode !== "read_only") {
  throw new Error("Unexpected Founder Admin contract identity or mode.");
}
if (!Array.isArray(contract.write_methods_allowed) || contract.write_methods_allowed.length !== 0) {
  throw new Error("Runtime probe refuses a contract that declares write methods.");
}
if (!Array.isArray(contract.endpoints) || contract.endpoints.length !== 9) {
  throw new Error("Founder Admin runtime probe requires exactly nine endpoints.");
}
if (contract.endpoints.some((endpoint) => endpoint.method !== "GET")) {
  throw new Error("Founder Admin runtime probe accepts GET-only contracts.");
}
if (serviceToken.length < Number(contract.authentication?.configured_token_min_length || 48)) {
  throw new Error("Runtime service token is weaker than the contract minimum.");
}

const resolvePath = (endpoint) => {
  const template = endpoint.path || endpoint.path_template;
  if (!template) throw new Error("Contract endpoint is missing a path.");
  return template.replace("{user_id}", "demo-user");
};

const request = async (path, token) => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    return await fetch(new URL(path, baseUrl), {
      method: "GET",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
      },
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
};

const firstPath = resolvePath(contract.endpoints[0]);
const rejected = await request(firstPath, "invalid-runtime-probe-token");
if (rejected.status !== Number(contract.failure_modes?.unauthorized || 401)) {
  throw new Error(`Invalid service token returned HTTP ${rejected.status}, expected 401.`);
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
];

const verifiedPaths = [];
for (const endpoint of contract.endpoints) {
  const path = resolvePath(endpoint);
  const response = await request(path, serviceToken);
  if (response.status !== 200) {
    const body = await response.text();
    throw new Error(`${path} returned HTTP ${response.status}: ${body.slice(0, 300)}`);
  }

  const cacheControl = String(response.headers.get("cache-control") || "").toLowerCase();
  if (!cacheControl.includes("no-store")) {
    throw new Error(`${path} is missing Cache-Control: no-store.`);
  }

  const body = await response.json();
  const serialized = JSON.stringify(body);
  if (serialized.includes(serviceToken)) {
    throw new Error(`${path} echoed the Founder Admin service token.`);
  }
  for (const marker of forbiddenMarkers) {
    if (serialized.includes(marker)) {
      throw new Error(`${path} exposed forbidden field marker ${marker}.`);
    }
  }

  if (path.endsWith("/overview") && body.mode !== "read_only") {
    throw new Error("Overview did not report read_only mode.");
  }

  verifiedPaths.push(path);
}

console.log(
  JSON.stringify(
    {
      contract: contract.contract,
      version: contract.version,
      mode: contract.mode,
      verified_endpoints: verifiedPaths.length,
      invalid_token_status: rejected.status,
      target: `${baseUrl.protocol}//${baseUrl.host}`,
    },
    null,
    2,
  ),
);
