import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd(), "..");
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");
const requireText = (text, needle, label) => {
  if (!text.includes(needle)) throw new Error(`Search discovery contract failed: ${label}`);
};

const home = read("frontend/components/HomeExperience.tsx");
const homePage = read("frontend/app/page.tsx");
const layout = read("frontend/app/layout.tsx");
const robots = read("frontend/app/robots.ts");
const sitemap = read("frontend/app/sitemap.ts");
const llms = read("frontend/app/llms.txt/route.ts");
const slugs = read("frontend/lib/seo-page-slugs.ts");
const seoPages = read("frontend/lib/seo-pages.ts");
const seoTemplate = read("frontend/app/(seo)/[slug]/page.tsx");
const pricing = read("frontend/app/pricing/page.tsx");
const nav = read("frontend/components/PublicSiteNav.tsx");
const footer = read("frontend/components/PublicSiteFooter.tsx");

requireText(layout, "AI Video Clipper for YouTube Shorts & Reels", "global metadata must describe the primary product");
requireText(layout, '"max-video-preview": -1', "Googlebot may use full video previews");
requireText(layout, '"max-image-preview": "large"', "Googlebot may use large image previews");
requireText(home, "AI VIDEO CLIPPER FOR INDIA", "homepage must state the primary category visibly");
requireText(home, "Post Karo free on every plan", "homepage must state the free publishing differentiator visibly");
requireText(home, "Can ClipKaro publish Shorts to Instagram and YouTube?", "homepage must expose an answer-first publishing question");
requireText(homePage, '"SoftwareApplication"', "homepage must publish SoftwareApplication structured data");
requireText(homePage, "Free Post Karo publishing", "homepage structured data must reflect current publishing capability");
requireText(homePage, "Is Post Karo free?", "homepage answer schema must reflect current pricing truth");

for (const slug of ["ai-video-clipper-india", "post-shorts-instagram-youtube"]) {
  requireText(slugs, `"${slug}"`, `public SEO slug ${slug} must remain registered`);
  requireText(seoPages, `"${slug}"`, `public SEO content ${slug} must remain defined`);
}
requireText(seoTemplate, "QUICK ANSWER", "SEO pages must expose answer-first visible copy");
requireText(seoTemplate, '"FAQPage"', "SEO pages must keep visible FAQs machine-readable");
requireText(seoTemplate, '"SoftwareApplication"', "SEO pages must identify the product entity");
requireText(pricing, "pricingStructuredData", "pricing page must expose machine-readable current offers");
requireText(pricing, 'name: "Free", price: "0"', "pricing schema must include the free plan");
requireText(pricing, 'name: "Mini Pass", price: "59"', "pricing schema must include the ₹59 Mini Pass");

for (const privatePath of ['"/account"', '"/admin"', '"/api"', '"/creator-pulse"', '"/dashboard"', '"/editor"', '"/post-karo"', '"/projects"', '"/upload"']) {
  requireText(robots, privatePath, `${privatePath} must stay excluded from search indexing`);
}
requireText(robots, '"Googlebot"', "Googlebot discovery rule must remain explicit");
requireText(robots, '"OAI-SearchBot"', "OpenAI search discovery rule must remain explicit");
requireText(robots, '"PerplexityBot"', "Perplexity discovery rule must remain explicit");
requireText(sitemap, "SEO_PAGES.map", "sitemap must automatically include all public SEO pages");
requireText(sitemap, "2026-09-22", "sitemap freshness signal must reflect this launch update");

requireText(llms, "Post Karo is included on every ClipKaro plan, including Free.", "answer-engine facts must reflect Post Karo pricing");
requireText(llms, "does not guarantee virality", "answer-engine facts must preserve performance boundaries");
requireText(llms, "https://clipkaro.pro/ai-video-clipper-india", "answer-engine index must include AI video clipper landing page");
requireText(llms, "https://clipkaro.pro/post-shorts-instagram-youtube", "answer-engine index must include Post Karo landing page");

requireText(nav, 'href: "/ai-video-clipper-india"', "primary AI video clipper page must be internally linked in navigation");
requireText(nav, 'href: "/post-shorts-instagram-youtube"', "Post Karo landing page must be internally linked in navigation");
requireText(footer, 'href="/ai-video-clipper-india"', "primary AI video clipper page must be internally linked in footer");
requireText(footer, 'href="/post-shorts-instagram-youtube"', "Post Karo landing page must be internally linked in footer");

console.log("Search discovery / GEO / AEO contract: passed");
