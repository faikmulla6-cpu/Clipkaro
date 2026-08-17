import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd(), "..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");
const expected = process.env.EXPECTED_RELEASE_VERSION || "7.8.0";

const pkg = JSON.parse(read("frontend/package.json"));
const backendVersionSource = read("backend/app/core/version.py");
const backendMatch = backendVersionSource.match(/APP_VERSION\s*=\s*["']([^"']+)["']/);
if (!backendMatch) throw new Error("Release identity contract failed: backend APP_VERSION is unreadable");
const backendVersion = backendMatch[1];
const frontendVersion = String(pkg.version || "");

if (backendVersion !== frontendVersion) {
  throw new Error(`Release identity contract failed: backend=${backendVersion}, frontend=${frontendVersion}`);
}
if (backendVersion !== expected) {
  throw new Error(`Release identity contract failed: expected ${expected}, found ${backendVersion}`);
}

const qa = read("docs/QA_REPORT.md");
if (!qa.startsWith(`# QA report — Launch Edition ${expected}`)) {
  throw new Error("Release identity contract failed: live QA report does not target the current version");
}
if (!qa.includes("docs/archive/QA_REPORT_2.0.1.md")) {
  throw new Error("Release identity contract failed: legacy QA evidence must be explicitly archived");
}
if (qa.includes("# QA report — Launch Edition 2.0.1")) {
  throw new Error("Release identity contract failed: current QA report still identifies itself as 2.0.1");
}

const archive = read("docs/archive/QA_REPORT_2.0.1.md");
if (!archive.includes("Historical archive")) {
  throw new Error("Release identity contract failed: legacy report must be clearly marked historical");
}

console.log(`Release identity contract: passed (${expected})`);
