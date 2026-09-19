import type { MetadataRoute } from "next";
import { SEO_PAGES } from "@/lib/seo-pages";

const routes = [
  "",
  "/youtube-channel-analyzer",
  "/about",
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
  const publicRefresh = new Date("2026-09-19T12:00:00Z");

  const staticRoutes = routes.map((route) => ({
    url: `https://clipkaro.pro${route}`,
    changeFrequency: (route === "" || route === "/youtube-channel-analyzer" ? "weekly" : "monthly") as "weekly" | "monthly",
    priority: route === "" ? 1 : route === "/youtube-channel-analyzer" ? 0.95 : route === "/pricing" ? 0.9 : route === "/about" ? 0.8 : 0.6,
    ...(route === "" || route === "/about" ? { lastModified: publicRefresh } : {}),
  }));
  const seoRoutes = SEO_PAGES.map((page, index) => ({
    url: `https://clipkaro.pro/${page.slug}`,
    changeFrequency: (index === 0 ? "weekly" : "monthly") as "weekly" | "monthly",
    priority: index === 0 ? 0.9 : 0.75,
    ...(index === 0 ? { lastModified: publicRefresh } : {}),
  }));
  return [...staticRoutes, ...seoRoutes];
}
