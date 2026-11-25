/** Public pricing fallback, SEO and static landing pages share these numbers.
 * Backend PLAN_CATALOG remains the checkout and entitlement authority.
 * CI verifies exact parity with the Python catalog and the contract here.
 */
export const PUBLIC_PRICING = {
  free: { price: 0, minutes: 15, maxVideo: 15, shorts: 2, billing: "free" },
  mini_pass: { price: 59, minutes: 25, maxVideo: 25, shorts: 5, billing: "one_time" },
  creator: { price: 249, minutes: 120, maxVideo: 60, shorts: 15, billing: "subscription" },
  growth: { price: 599, minutes: 300, maxVideo: 90, shorts: 50, billing: "subscription" },
  pro: { price: 1299, minutes: 600, maxVideo: 180, shorts: 150, billing: "subscription" },
  agency: { price: 1999, minutes: 1500, maxVideo: 240, shorts: 500, billing: "subscription" },
} as const;

export type PricingPlanId = keyof typeof PUBLIC_PRICING;
export function planPriceLabel(plan: PricingPlanId) {
  return `₹${PUBLIC_PRICING[plan].price.toLocaleString("en-IN")}`;
}
export function planFeatureMinutes(plan: PricingPlanId): string {
  const p = PUBLIC_PRICING[plan];
  return plan === "mini_pass"
    ? `${p.minutes} total Karo Minutes per pass · up to ${p.maxVideo} min/video`
    : `${p.minutes} total Karo Minutes/month · up to ${p.maxVideo} min/video`;
}

export const CARTOON_SECONDS = { free: 30, mini_pass: 60, creator: 300, growth: 900, pro: 1800, agency: 3600 } as const;

export function cartoonFeature(plan: PricingPlanId): string {
  if (plan === "free") return "Cartoon Studio · one cartoon up to 30 seconds per account";
  if (plan === "mini_pass") return "Cartoon Studio · 1 finished minute per pass";
  return `Cartoon Studio · ${CARTOON_SECONDS[plan] / 60} finished minutes/month + one refill`;
}

export const CARTOON_REFILL_DETAILS =
  "Monthly plans include one extra full refill each billing cycle. When 30 seconds or less remain, the 24-hour wait starts automatically. Claim the refill in Cartoon Studio and keep any time left in that cycle. For example, Creator starts with 5 minutes and can claim another 5.";
export const CARTOON_USAGE_DETAILS =
  "Cartoon time is separate from Karo Minutes. Only newly finished cartoons count. Failed renders, repeat downloads and posting use no extra time. Connect your own planner API key to create. Active existing plans and Mini Passes also get their listed cartoon allowance.";

/** Premium face-aware analysis has its own credits, independent of clipping. */
export const SMART_LAYOUT_PREMIUM = {
  free: { credits: 1, daily: 1 },
  mini_pass: { credits: 1, daily: 1 },
  creator: { credits: 12, daily: 4 },
  growth: { credits: 40, daily: 10 },
  pro: { credits: 120, daily: 25 },
  agency: { credits: 300, daily: 60 },
} as const satisfies Record<PricingPlanId, { credits: number; daily: number }>;

export function smartLayoutFeature(plan: PricingPlanId): string {
  const { credits, daily } = SMART_LAYOUT_PREMIUM[plan];
  if (plan === "free") return "Real Smart Layout beta: 1 free preview per account, once for life (during approved rollout)";
  if (!credits) return "Real Smart Layout not included · Classic framing available";
  return `Real Smart Layout beta: ${credits} analysis ${credits === 1 ? "credit" : "credits"} ${plan === "mini_pass" ? "per pass" : "/month"} · up to ${daily}/24h`;
}
