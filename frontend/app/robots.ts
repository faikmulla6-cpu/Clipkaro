import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: [
        "/account",
        "/admin",
        "/analytics",
        "/api",
        "/api-local",
        "/brand",
        "/calendar",
        "/creator-pulse",
        "/dashboard",
        "/editor",
        "/exports",
        "/forgot-password",
        "/login",
        "/projects",
        "/reset-password",
        "/signup",
        "/templates",
        "/upload",
        "/verify-email",
      ],
    },
    sitemap: "https://clipkaro.pro/sitemap.xml",
  };
}
