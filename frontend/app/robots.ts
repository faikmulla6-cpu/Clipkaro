import type { MetadataRoute } from "next";

const privatePaths = [
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
];

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      { userAgent: "*", allow: "/", disallow: privatePaths },
      { userAgent: "OAI-SearchBot", allow: "/", disallow: privatePaths },
    ],
    host: "https://clipkaro.pro",
    sitemap: "https://clipkaro.pro/sitemap.xml",
  };
}
