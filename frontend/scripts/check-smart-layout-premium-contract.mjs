/** Dependency-free Node24 parity check for server-authoritative premium credits. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { SMART_LAYOUT_PREMIUM, smartLayoutFeature } from "../lib/pricing-contract.ts";

const backend = readFileSync(new URL("../../backend/app/services/smart_layout_credits.py", import.meta.url), "utf8");
const pricing = readFileSync(new URL("../app/pricing/page.tsx", import.meta.url), "utf8");
const accountPricing = readFileSync(new URL("../app/pricing/PricingExperience.tsx", import.meta.url), "utf8");
const editor = readFileSync(new URL("../app/editor/[clipId]/page.tsx", import.meta.url), "utf8");
for (const [plan, { credits, daily }] of Object.entries(SMART_LAYOUT_PREMIUM)) {
  const pat = new RegExp('"' + plan + '"\\s*:\\s*\\(' + credits + '\\s*,\\s*' + daily + '\\)');
  assert.match(backend, pat, 'backend/frontend credit parity for ' + plan);
  assert.ok(pricing.includes('smartLayoutFeature("' + plan + '")'), plan + ' public pricing feature');
  assert.ok(accountPricing.includes('smartLayoutFeature("' + plan + '")'), plan + ' account pricing feature');
  assert.ok(smartLayoutFeature(plan).includes(credits ? 'beta' : 'not included'));
}
assert.match(editor, /setAnalysisConfirmed\(true\)/, "explicit user consent");
assert.match(editor, /smartQuota\.remaining/, "plan credit visibility");
assert.match(editor, /smartQuota\.daily_remaining/, "rolling daily credit visibility");
assert.match(editor, /smartClipCost/, "selected clip cost visibility");
console.log("Premium Smart Layout: backend/frontend pricing parity and explicit consent passed");
