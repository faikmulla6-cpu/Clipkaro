import assert from "node:assert/strict";
import fs from "node:fs";
const load = (p) => fs.readFileSync(new URL(p, import.meta.url), "utf8");
const bill = load("../../backend/app/services/billing.py");
const price = load("../lib/pricing-contract.ts");
const cartoonUsage = load("../../backend/app/services/cartoon_usage.py");
const pricing = load("../app/pricing/PricingExperience.tsx");
const page = load("../app/pricing/page.tsx");
const publicCards = load("../lib/public-plan-cards.ts");
const home = load("../components/HomeExperience.tsx");
const shell = load("../components/AppShell.tsx");
const youtube = load("../components/UploadStudio.tsx");
const terms = load("../app/terms/page.tsx");
const legal = load("../app/legal-notice/page.tsx");
const policy = load("../app/llms.txt/route.ts");
const expectations = {
  mini_pass: [59, 25, 25, 5],
  creator: [249, 120, 60, 15],
  growth: [599, 300, 90, 50],
  pro: [1299, 600, 180, 150],
  agency: [1999, 1500, 240, 500]
};
for (const [key, [rupees, minutes, maximum, shorts]] of Object.entries(expectations)) {
  const catalog = bill.split('"' + key + '": {')[1]?.split("\n    },")[0] ?? "";
  assert.match(catalog, new RegExp('"price": ' + rupees + ','));
  assert.match(catalog, new RegExp('"price_paise": ' + rupees * 100 + ','));
  assert.match(catalog, new RegExp('"processing_minutes": ' + minutes + ','));
  assert.match(catalog, new RegExp('"shorts": ' + shorts + ','));
  const front = price.split("  " + key + ": {")[1]?.split("},")[0] ?? "";
  assert.ok(front.includes("price: " + rupees));
  assert.ok(front.includes("minutes: " + minutes));
  assert.ok(front.includes("maxVideo: " + maximum));
  assert.ok(front.includes("shorts: " + shorts));
}
assert.match(pricing, /Plan details are updating\. Checkout is temporarily unavailable/);
for (const [key, seconds] of Object.entries({ free: 30, mini_pass: 60, creator: 300, growth: 900, pro: 1800, agency: 3600 })) {
  assert.ok(cartoonUsage.includes(`"${key}": ${seconds}`));
  assert.ok(price.includes(`${key}: ${seconds}`));
  assert.ok(publicCards.includes(`cartoonFeature("${key}")`));
  assert.ok(publicCards.includes(`smartLayoutFeature("${key}")`));
  assert.ok(publicCards.includes(`planPriceLabel("${key}")`));
  assert.ok(pricing.includes(`cartoonFeature("${key}")`));
}
assert.match(pricing, /planFeatureMinutes\("mini_pass"\)/);
assert.match(pricing, /planFeatureMinutes\("creator"\)/);
assert.match(pricing, /planFeatureMinutes\("growth"\)/);
assert.match(pricing, /planFeatureMinutes\("pro"\)/);
assert.match(page, /price: String\(PUBLIC_PRICING\.pro\.price\)/);
assert.match(page, /price: String\(PUBLIC_PRICING\.creator\.price\)/);
assert.match(shell, /ck-credit-ribbon/);
assert.match(shell, /Source projects/);
assert.match(shell, /CreditTopupDialog/);
assert.match(youtube, /source_video_limit_minutes/);
assert.match(terms, /Previously purchased Mini Pass entitlements/);
assert.match(legal, /Existing Mini Pass purchases retain their original 125-minute allowance/);
assert.match(policy, /Creator costs ₹249\/month/);
assert.match(page, /plans=\{PUBLIC_PLAN_CARDS\}/);
assert.match(home, /PUBLIC_PLAN_CARDS\.map\(/);
const staticPublic = [pricing, page, home, publicCards, load("../components/PublicPricingView.tsx"), legal, policy];
for (const [i, file] of staticPublic.entries()) {
  assert.ok(!/₹199\/month|₹399\/month|₹799\/month|Creator from ₹199/.test(file), "Stale price shown in public pricing surface #" + i);
}
console.log("Canonical ClipKaro new and grandfathered pricing contracts passed");
