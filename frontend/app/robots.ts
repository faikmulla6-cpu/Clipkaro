import type { MetadataRoute } from "next";

const privatePaths = [
  "/account",
  "/admin",
  "/analytics",
  "/api",
  "/api-local",
  "/brand",
  "/calendar",
  "/content-packs",
  "/creator-pulse",
  "/dashboard",
  "/editor",
  "/exports",
  "/forgot-password",
  "/help",
  "/login",
  "/post-karo",
  "/projects",
  "/reset-password",
  "/signup",
  "/templates",
  "/upload",
  "/verify-email",
];

const discoveryAgents = [
  "*",
  "Googlebot",
  "bingbot",
  "OAI-SearchBot",
  "ChatGPT-User",
  "PerplexityBot",
  "ClaudeBot",
] as const;

export default function robots(): MetadataRoute.Robots {
  return {
    rules: discoveryAgents.map((userAgent) => ({
      userAgent,
      allow: ["/", "/llms.txt"],
      disallow: privatePaths,
    })),
    host: "https://clipkaro.pro",
    sitemap: "https://clipkaro.pro/sitemap.xml",
  };
}
