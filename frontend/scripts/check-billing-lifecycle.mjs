import fs from "node:fs";

const pricing = fs.readFileSync(new URL("../app/pricing/page.tsx", import.meta.url), "utf8");
const lifecycle = fs.readFileSync(new URL("../../backend/app/api/billing_lifecycle.py", import.meta.url), "utf8");
const main = fs.readFileSync(new URL("../../backend/app/main.py", import.meta.url), "utf8");

const requiredPricing = [
  '"subscription_change"',
  'scheduled_plan',
  'Upgrade to ${plan.name} now',
  'Downgrade to ${plan.name} next cycle',
  '/billing/cancel-scheduled-change',
  'Available after subscription ends',
];
for (const needle of requiredPricing) {
  if (!pricing.includes(needle)) throw new Error(`Billing UX contract missing: ${needle}`);
}

const requiredBackend = [
  'schedule = "now" if is_upgrade else "cycle_end"',
  'usage_period_key(user)',
  'UPDATE usage_reservations SET period_key=',
  'subscription.updated',
  'retrieve_scheduled_changes',
  'cancel_scheduled_changes',
  'cancel_at_cycle_end',
  'provider_plan_id',
  '@router.post("/billing/verify")',
  'X-Razorpay-Event-Id',
  '_sanitize_webhook_payload',
  'payment.captured',
  'order.paid',
  '_activate_one_time_checkout',
];
for (const needle of requiredBackend) {
  if (!lifecycle.includes(needle)) throw new Error(`Billing backend contract missing: ${needle}`);
}

for (const path of [
  '/billing/status',
  '/billing/razorpay/webhook',
  '/billing/checkout',
  '/billing/verify',
  '/billing/sync',
  '/billing/cancel',
]) {
  if (!main.includes(`"${path}"`)) throw new Error(`Legacy billing route is not explicitly replaced: ${path}`);
}

if (pricing.includes("Cancel it first")) {
  throw new Error("Pricing UI must never require cancellation before an upgrade.");
}

console.log("Billing lifecycle contract passed.");
