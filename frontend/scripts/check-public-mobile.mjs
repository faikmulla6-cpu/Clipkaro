import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd(), "..");
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");
const requireText = (text, needle, label) => {
  if (!text.includes(needle)) throw new Error(`Public mobile contract failed: ${label}`);
};

const layout = read("frontend/app/layout.tsx");
const nav = read("frontend/components/PublicSiteNav.tsx");
const home = read("frontend/components/HomeExperience.module.css");
const seo = read("frontend/app/(seo)/[slug]/seo-product-page.module.css");
const pricing = read("frontend/components/PublicPricingView.module.css");
const pulse = read("frontend/app/youtube-channel-analyzer/page.module.css");
const footer = read("frontend/components/PublicSiteFooter.module.css");
const about = read("frontend/app/about/about-polish.module.css");
const mobileAudit = read("frontend/app/mobile-audit.css");

requireText(layout, 'width: "device-width"', "viewport must follow the device width");
requireText(layout, "initialScale: 1", "viewport must use a 1x initial scale");
requireText(layout, 'viewportFit: "cover"', "viewport must support safe-area devices");
requireText(nav, "h-11 w-11", "mobile navigation toggle must keep a 44px touch target");
requireText(nav, "safe-area-inset-bottom", "mobile navigation drawer must respect the bottom safe area");
for (const [css, label] of [
  [home, "homepage"],
  [seo, "SEO landing pages"],
  [pricing, "pricing"],
  [pulse, "Creator Pulse"],
  [footer, "public footer"],
]) {
  requireText(css, "@media(max-width:", `${label} must include mobile breakpoints`);
}

requireText(home, "Mobile hardening: public homepage", "homepage mobile hardening must remain");
requireText(home, ".productRail{grid-template-columns:1fr}", "homepage product rail must collapse on narrow phones");
requireText(home, ".workspaceSide{display:none}", "desktop workspace sidebar must simplify on mobile");
requireText(seo, "Mobile hardening: acquisition landing pages", "SEO pages need explicit phone hardening");
requireText(pricing, "Mobile hardening: pricing", "pricing cards need explicit phone hardening");
requireText(pulse, "Mobile hardening: Creator Pulse public page", "Creator Pulse needs explicit phone hardening");
requireText(about, "@media(max-width:620px)", "About page must retain its phone layout");
requireText(mobileAudit, "@media(max-width:600px)", "authenticated workspace must retain phone hardening");

console.log("Public/mobile responsive contract: passed");
