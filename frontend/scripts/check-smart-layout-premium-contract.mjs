/** Dependency-free Node24 parity check for server-authoritative premium credits. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { SMART_LAYOUT_PREMIUM, smartLayoutFeature } from "../lib/pricing-contract.ts";

const backend = readFileSync(new URL("../../backend/app/services/smart_layout_credits.py", import.meta.url), "utf8");
const api = readFileSync(new URL("../../backend/app/api/smart_layout_v2.py", import.meta.url), "utf8");
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
assert.match(editor, /setAnalysisConfirmedFor\(clipAnalysisKey\)/, "analysis consent is scoped to the exact clip/range");
assert.match(editor, /layoutPlansClipKey === clipAnalysisKey/, "cached plans cannot leak across clips/ranges");
assert.match(editor, /billing_action\?: SmartLayoutBillingAction/, "frontend consumes server-authoritative billing outcome");
assert.match(editor, /currentBillingAction === "new_charge".*Analysis complete/s, "new paid analysis is labelled as charged");
assert.match(editor, /currentBillingAction === "cached_reuse".*Saved analysis reused/s, "only cached results claim reuse");
assert.doesNotMatch(editor, /\{realPlan && <p className="smart-quota-reused"><Check size=\{13\}\/> Saved analysis reused/, "reuse message is not unconditional");
assert.match(editor, /smartQuota\.remaining/, "plan credit visibility");
assert.match(editor, /smartQuota\.daily_remaining/, "rolling daily credit visibility");
assert.match(editor, /smartClipCost/, "selected clip cost visibility");
assert.match(backend, /return job_id, "free_refresh" if free_recompute else "new_charge"/, "backend distinguishes free refresh from a new credit reservation");
assert.match(api, /"billing_action": "cached_reuse"/, "API marks cached results as reused");
assert.match(api, /"billing_action": "existing_job"/, "API marks an already-running job as no additional reservation");
assert.match(api, /"billing_action": action/, "API returns the authoritative reservation action");
assert.match(editor, /currentBillingAction === "free_refresh".*Saved analysis refreshed/s, "free refresh is not shown as a fresh paid analysis");
assert.match(editor, /currentBillingAction === "existing_job".*Existing analysis reused/s, "an existing job is not shown as a fresh paid analysis");
console.log("Premium Smart Layout: pricing parity, clip-scoped consent, and billing-status contracts passed");
