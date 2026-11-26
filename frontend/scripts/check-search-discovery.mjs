import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd(), "..");
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");
const requireText = (text, needle, label) => {
  if (!text.includes(needle)) throw new Error(`Search discovery contract failed: ${label}`);
};

const home = read("frontend/components/HomeExperience.tsx");
const homePage = read("frontend/app/page.tsx");
const about = read("frontend/app/about/AboutExperience.tsx");
const cartoonMaker = read("frontend/app/ai-cartoon-maker/page.tsx");
const layout = read("frontend/app/layout.tsx");
const nextConfig = read("frontend/next.config.js");
const robots = read("frontend/app/robots.ts");
const sitemap = read("frontend/app/sitemap.ts");
const llms = read("frontend/app/llms.txt/route.ts");
const slugs = read("frontend/lib/seo-page-slugs.ts");
const seoPages = read("frontend/lib/seo-pages.ts");
const seoTemplate = read("frontend/app/(seo)/[slug]/page.tsx");
const pricing = read("frontend/app/pricing/page.tsx");
const nav = read("frontend/components/PublicSiteNav.tsx");
const footer = read("frontend/components/PublicSiteFooter.tsx");

requireText(layout, "AI Video Clipper for Shorts, Reels & Post Karo", "global metadata must describe the primary product");
if (layout.includes("canonical:")) throw new Error("Search discovery contract failed: root layout must not impose a homepage canonical on child routes");
if (layout.includes('"max-video-preview"') || layout.includes("robots: {")) throw new Error("Search discovery contract failed: global layout must not force index directives onto private app routes");
requireText(homePage, '"max-video-preview": -1', "Googlebot may use full video previews on the public homepage");
requireText(homePage, '"max-image-preview": "large"', "Googlebot may use large image previews on the public homepage");
requireText(home, "AI VIDEO CLIPPER FOR INDIA", "homepage must state the primary category visibly");
requireText(home, "Unlimited Post Karo on every plan", "homepage must state the unlimited publishing differentiator");
requireText(home, "Is Post Karo unlimited?", "homepage must answer the publishing-limit question directly");
requireText(home, "What can Creator Studio edit?", "homepage must expose editor controls in answer-first copy");
requireText(home, "Is ClipKaro an affordable AI clipper with unlimited posting?", "homepage must answer the affordable + unlimited commercial-intent query directly");
requireText(home, '/affordable-ai-video-clipper-unlimited-posting', "homepage must internally link the affordable + unlimited intent page");
requireText(homePage, '"WebApplication"', "homepage must identify ClipKaro as web software");
requireText(homePage, "Unlimited Post Karo publishing access", "homepage structured data must reflect current publishing capability");
requireText(homePage, "65% to 160%", "homepage structured data must reflect current Creator Studio caption controls");
if (homePage.includes('"FAQPage"') || homePage.includes('"HowTo"')) throw new Error("Search discovery contract failed: homepage must not emit retired Google FAQ/HowTo rich-result markup");

for (const slug of ["ai-video-clipper-india", "post-shorts-instagram-youtube", "shorts-video-editor-ai", "affordable-ai-video-clipper-unlimited-posting"]) {
  requireText(slugs, `"${slug}"`, `public SEO slug ${slug} must remain registered`);
}
requireText(seoPages, 'title: "AI Video Clipper India"', "AI video clipper acquisition content must remain defined");
requireText(seoPages, 'title: "Post Shorts to Instagram and YouTube"', "Post Karo acquisition content must remain defined");
requireText(seoPages, 'title: "Creator Studio AI Shorts Editor"', "Creator Studio acquisition content must remain defined");
requireText(seoPages, 'title: "Affordable AI Video Clipper with Unlimited Posting"', "affordable + unlimited commercial-intent content must remain defined");
requireText(seoPages, "no ClipKaro per-post publishing quota", "commercial-intent page must define unlimited Post Karo accurately");
requireText(seoTemplate, "QUICK ANSWER", "SEO pages must expose answer-first visible copy");
requireText(seoTemplate, '"SoftwareApplication"', "SEO pages must identify the product entity");
requireText(seoTemplate, '"BreadcrumbList"', "SEO pages must keep breadcrumb structured data");
if (seoTemplate.includes('"FAQPage"')) throw new Error("Search discovery contract failed: SEO template must not emit FAQPage rich-result markup");
requireText(pricing, "pricingStructuredData", "pricing page must expose machine-readable current offers");
requireText(pricing, 'name: "Free", price: "0"', "pricing schema must include the free plan");
requireText(pricing, 'name: "Mini Pass", price: "59"', "pricing schema must include the ₹59 Mini Pass");
requireText(pricing, 'name: "Creator", price: String(PUBLIC_PRICING.creator.price)', "pricing schema must use the current Creator plan price");
for (const privatePath of ['"/account"', '"/admin"', '"/api"', '"/creator-pulse"', '"/dashboard"', '"/editor"', '"/post-karo"', '"/projects"', '"/upload"']) {
  requireText(robots, privatePath, `${privatePath} must stay excluded from search indexing`);
}
requireText(robots, '"Googlebot"', "Googlebot discovery rule must remain explicit");
requireText(robots, '"OAI-SearchBot"', "OpenAI search discovery rule must remain explicit");
requireText(robots, '"PerplexityBot"', "Perplexity discovery rule must remain explicit");
requireText(nextConfig, '"X-Robots-Tag"', "private app routes must emit an X-Robots-Tag");
requireText(nextConfig, '"noindex, nofollow, noarchive"', "private app routes must be explicitly noindexed");
requireText(nextConfig, '"/post-karo/:path*"', "authenticated Post Karo must stay out of the search index");
requireText(nextConfig, '"/creator-pulse/:path*"', "authenticated Creator Pulse must stay out of the search index");
requireText(nextConfig, '"/cartoon-studio/:path*"', "authenticated Cartoon Studio must stay out of the search index");
const cartoonPublicPath = "/ai-cartoon-maker";
for (const [source, label] of [[home, "homepage"], [about, "About page"]]) {
  requireText(source, `href="${cartoonPublicPath}"`, `${label} must link to the public cartoon maker`);
}
requireText(cartoonMaker, `canonical: "${cartoonPublicPath}"`, "cartoon maker must have its own canonical");
requireText(cartoonMaker, 'robots: { index: true, follow: true }', "public cartoon maker must be indexable");
requireText(cartoonMaker, 'href="/cartoon-studio"', "public cartoon maker must have a studio CTA");
requireText(nav, `href: "${cartoonPublicPath}",\n    label: "Cartoon Studio"`, "Product navigation must link to the public cartoon maker");
requireText(sitemap, `"${cartoonPublicPath}"`, "sitemap must list the public cartoon maker");
if (robots.includes(`"${cartoonPublicPath}"`) || nextConfig.includes(`"${cartoonPublicPath}/:path*"`) || sitemap.includes('"/cartoon-studio"')) {
  throw new Error("Search discovery contract failed: public cartoon maker and private studio must have separate indexing rules");
}
requireText(sitemap, "SEO_PAGES.map", "sitemap must automatically include all public SEO pages");
requireText(sitemap, "2026-09-24", "sitemap freshness signal must reflect the current public update");

requireText(llms, "no ClipKaro per-post publishing quota", "answer-engine facts must define unlimited Post Karo accurately");
requireText(llms, "does not guarantee virality", "answer-engine facts must preserve performance boundaries");
requireText(llms, "https://clipkaro.pro/shorts-video-editor-ai", "answer-engine index must include Creator Studio");
requireText(llms, "https://clipkaro.pro/affordable-ai-video-clipper-unlimited-posting", "answer-engine index must include the affordable + unlimited intent page");
requireText(llms, "₹1-per-successful-analysis", "answer-engine facts must reflect Creator Pulse pricing");
requireText(footer, 'href="/affordable-ai-video-clipper-unlimited-posting"', "footer must internally link the affordable + unlimited intent page");
for (const href of ["/ai-video-clipper-india", "/shorts-video-editor-ai", "/post-shorts-instagram-youtube"]) {
  requireText(nav, `href: "${href}"`, `${href} must be internally linked in navigation`);
  requireText(footer, `href="${href}"`, `${href} must be internally linked in footer`);
}

for (const route of ["terms", "privacy", "refund-policy", "acceptable-use", "copyright", "legal-notice"]) {
  const legalLayout = read(`frontend/app/${route}/layout.tsx`);
  requireText(legalLayout, `canonical: "/${route}"`, `${route} must have its own canonical`);
}
console.log("Search discovery / GEO / AEO contract: passed");
