import type { MetadataRoute } from "next";
import { SEO_PAGES } from "@/lib/seo-pages";

const routes = [
  "",
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
  const now = new Date();
  const staticRoutes = routes.map((route) => ({
    url: `https://clipkaro.pro${route}`,
    lastModified: now,
    changeFrequency: (route === "" ? "weekly" : "monthly") as "weekly" | "monthly",
    priority: route === "" ? 1 : route === "/pricing" ? 0.9 : 0.6,
  }));
  const seoRoutes = SEO_PAGES.map((page) => ({
    url: `https://clipkaro.pro/${page.slug}`,
    lastModified: now,
    changeFrequency: "monthly" as const,
    priority: 0.75,
  }));
  return [...staticRoutes, ...seoRoutes];
}
