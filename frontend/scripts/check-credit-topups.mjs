import assert from "node:assert/strict";
import fs from "node:fs";
const read = p => fs.readFileSync(new URL(`../${p}`,import.meta.url),"utf8");
const backend = fs.readFileSync(new URL("../../backend/app/api/credit_topups.py",import.meta.url),"utf8");
const migration = fs.readFileSync(new URL("../../backend/migrations/versions/20261021_11_credit_topups.py",import.meta.url),"utf8");
const app = read("components/AppShell.tsx");
const dialog = read("components/CreditTopupDialog.tsx");
const legal = read("lib/legal.ts");
const legalBackend = fs.readFileSync(new URL("../../backend/app/services/legal.py",import.meta.url),"utf8");
for(const [needle, source] of [
  ["MINUTES_PAISE = 300",backend],["SHORT_PAISE = 200",backend],
  ["minutes == 0 and shorts == 0",backend],["verify_order_signature",backend],
  ["payment_matches(payment, row, payment_id)",backend],
  ["async with distributed_advisory_lock",backend],["credit_checkout",backend],
  ["credit_topup_wallets",migration],["credit_topup_spends",migration],
  ["KARO_MINUTES_QUOTA_EXCEEDED",migration],
  ["ck-credit-ribbon",app],["ck-allowance-notice",app],
  ["onClick={closeAllowanceNotice}",app],
  ["₹3 per minute",dialog],["₹2 each",dialog],
  ["/credits/verify",dialog],["onSuccess()",dialog],
]) assert.ok(source.includes(needle), `Credit checkout contract missing: ${needle}`);
assert.ok(!dialog.includes("/billing/verify"),"Allowances must never use plan billing verification");
// Top-up checkout must never record consent without a deliberate checkbox action.
const version = legal.match(/export const LEGAL_VERSION = "([^"]+)"/)?.[1];
assert.ok(version && legalBackend.includes(`LEGAL_VERSION = "${version}"`), "Frontend and backend legal document versions must match");
for (const needle of [
  'api<LegalStatus>("/legal/status")',
  'legalStatus.version === LEGAL_VERSION',
  'legalStatus.checkout_allowed',
  '(legalStatus.accepted || legalChecked)',
  'checked={legalChecked}',
  'disabled={submitting}',
  'onChange={e=>setLegalChecked(e.target.checked)}',
  'href="/terms"', 'href="/privacy"', 'href="/refund-policy"',
  'disabled={!eligible || loading || submitting || !legalReady}',
  'if(!eligible || submitting || !legalReady) return;',
  'if (!legalChecked) throw new Error(',
  'if (!acceptance.accepted || acceptance.version !== LEGAL_VERSION)',
]) assert.ok(dialog.includes(needle), `Top-up legal consent contract missing: ${needle}`);
const purchaseStart = dialog.indexOf("async function purchase()");
const consentPost = dialog.indexOf('postJSON<LegalAcceptance>("/legal/accept"');
const checkoutPost = dialog.indexOf('postJSON<Checkout>("/credits/checkout"');
assert.ok(purchaseStart >= 0 && purchaseStart < consentPost && consentPost < checkoutPost,
  "User-initiated legal acceptance must succeed before the Razorpay order is created");
assert.ok(dialog.indexOf('postJSON<LegalAcceptance>("/legal/accept"') === dialog.lastIndexOf('postJSON<LegalAcceptance>("/legal/accept"'),
  "Legal consent must not be recorded by background effects or repeated call sites");
assert.ok(!dialog.includes("/billing/checkout"), "Top-ups must never create or modify subscriptions");
console.log("Credit top-up pricing, legal consent, and captured-payment source contracts passed.");
