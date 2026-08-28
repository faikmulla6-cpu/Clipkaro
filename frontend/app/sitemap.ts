import type { MetadataRoute } from "next";

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
  return routes.map((route) => ({
    url: `https://clipkaro.pro${route}`,
    lastModified: now,
    changeFrequency: route === "" ? "weekly" : "monthly",
    priority: route === "" ? 1 : route === "/pricing" ? 0.9 : 0.6,
  }));
}
