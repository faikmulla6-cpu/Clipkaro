import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: [
        "/account",
        "/analytics",
        "/api",
        "/brand",
        "/calendar",
        "/dashboard",
        "/editor",
        "/exports",
        "/projects",
        "/templates",
        "/upload",
      ],
    },
    sitemap: "https://clipkaro.pro/sitemap.xml",
  };
}
