import type { MetadataRoute } from "next";
import { SEO_PAGES } from "@/lib/seo-pages";

const routes = [
  "",
  "/youtube-channel-analyzer",
  "/about",
  "/ai-cartoon-maker",
  "/pricing",
  "/contact",
  "/terms",
  "/privacy",
  "/refund-policy",
  "/acceptable-use",
  "/copyright",
  "/legal-notice",
];

export default function sitemap(): MetadataRoute.Sitemap {
  const publicRefresh = new Date("2026-09-24T12:00:00Z");
  const highIntentSlugs = new Set([
    "youtube-video-to-shorts-ai",
    "ai-video-clipper-india",
    "post-shorts-instagram-youtube",
    "shorts-video-editor-ai",
    "affordable-ai-video-clipper-unlimited-posting",
  ]);

  const staticRoutes = routes.map((route) => ({
    url: `https://clipkaro.pro${route}`,
    changeFrequency: (route === "" || route === "/youtube-channel-analyzer" || route === "/pricing" ? "weekly" : "monthly") as "weekly" | "monthly",
    priority: route === "" ? 1 : route === "/youtube-channel-analyzer" ? 0.95 : route === "/pricing" ? 0.92 : route === "/about" ? 0.82 : 0.6,
    ...(route === "" || route === "/about" || route === "/pricing" || route === "/youtube-channel-analyzer" ? { lastModified: publicRefresh } : {}),
  }));
  const seoRoutes = SEO_PAGES.map((page) => ({
    url: `https://clipkaro.pro/${page.slug}`,
    changeFrequency: (highIntentSlugs.has(page.slug) ? "weekly" : "monthly") as "weekly" | "monthly",
    priority: highIntentSlugs.has(page.slug) ? 0.9 : 0.76,
    lastModified: publicRefresh,
  }));
  return [...staticRoutes, ...seoRoutes];
}
