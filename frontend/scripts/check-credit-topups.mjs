import assert from "node:assert/strict";
import fs from "node:fs";
const read = p => fs.readFileSync(new URL(`../${p}`,import.meta.url),"utf8");
const backend = fs.readFileSync(new URL("../../backend/app/api/credit_topups.py",import.meta.url),"utf8");
const migration = fs.readFileSync(new URL("../../backend/migrations/versions/20261021_11_credit_topups.py",import.meta.url),"utf8");
const app = read("components/AppShell.tsx");
const dialog = read("components/CreditTopupDialog.tsx");
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
console.log("Credit top-up pricing, UI and captured-payment contracts passed.");
