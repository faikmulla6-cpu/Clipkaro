// Validate browser-side duration-to-entitlement comparisons with real TypeScript.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";
import ts from "typescript";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = readFileSync(resolve(root, "lib/upload-minutes.ts"), "utf8");
const converted = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const module = { exports: {} };
runInNewContext(converted, { module, exports: module.exports }, { timeout: 1500 });
const warn = module.exports.uploadQuotaWarning;
if (typeof warn !== "function") throw new Error("Quota calculation unavailable.");

const creator = {
  plan: "creator", processing_minutes_remaining: 0.1,
  source_video_limit_minutes: 60, shorts_remaining: 10,
};
function assertCase(name, actual, expected) {
  if (actual !== expected) throw new Error(name + " expected " + expected + " but got " + actual);
}
assertCase("User screenshot 17.8-minute MP4 rejected before upload", Boolean(warn(1069.464, creator)), true);
assertCase("Small 5-second source allowed", warn(5, creator), null);
assertCase("Rounded 8-second borderline allowed for backend decision", warn(8, creator), null);
assertCase("Fresh Creator 40-minute source allowed", warn(2400, { ...creator, processing_minutes_remaining: 120 }), null);
assertCase("Growth per-source 90 minute cap", Boolean(warn(95 * 60, {
  plan: "growth", processing_minutes_remaining: 300,
  source_video_limit_minutes: 90, shorts_remaining: 30,
})), true);
assertCase("No shorts left", Boolean(warn(60, { ...creator, processing_minutes_remaining: 10, shorts_remaining: 0 })), true);
assertCase("Unknown metadata never causes false rejection", warn(null, creator), null);
console.log("Local video duration + live quota preflight contract passed.");
