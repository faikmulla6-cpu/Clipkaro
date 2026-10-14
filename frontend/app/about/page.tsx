import type { Metadata } from "next";
import { PublicSiteFooter } from "@/components/PublicSiteFooter";
import { PublicSiteNav } from "@/components/PublicSiteNav";
import { AboutExperience } from "./AboutExperience";
import unified from "./unified.module.css";

const title = "About ClipKaro AI — Affordable AI Video Clipping, Creator Studio & Post Karo";
const description = "Learn how ClipKaro combines long-video-to-Shorts AI, creator-controlled editing, ₹1 Creator Pulse intelligence and unlimited Post Karo publishing access in an affordable India-first workflow.";

export const metadata: Metadata = {
  title,
  description,
  keywords: ["ClipKaro AI", "YouTube URL to Shorts", "paste YouTube link to Shorts", "YouTube video clipper", "upload video to Shorts", "AI video clipping", "YouTube creator intelligence", "YouTube channel analysis", "Creator Pulse", "Indian creator AI"],
  alternates: { canonical: "/about" },
  openGraph: { type: "website", url: "/about", siteName: "ClipKaro AI", title, description, images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "ClipKaro AI" }] },
  twitter: { card: "summary_large_image", title, description, images: ["/assets/clipkaro-icon.png"] },
};

const aboutStructuredData = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": "https://clipkaro.pro/#organization",
      name: "ClipKaro AI",
      alternateName: ["ClipKaro", "ClipKaroAI"],
      url: "https://clipkaro.pro/",
      logo: "https://clipkaro.pro/assets/clipkaro-icon.png",
    },
    {
      "@type": "SoftwareApplication",
      "@id": "https://clipkaro.pro/#software",
      name: "ClipKaro AI",
      applicationCategory: "MultimediaApplication",
      operatingSystem: "Web",
      url: "https://clipkaro.pro/",
      publisher: { "@id": "https://clipkaro.pro/#organization" },
      description,
      offers: { "@type": "Offer", priceCurrency: "INR", price: "0", url: "https://clipkaro.pro/pricing" },
      featureList: [
        "YouTube URL import for supported videos, Shorts and live replays",
        "Original-file upload fallback when direct URL acquisition is unavailable",
        "AI clip detection and ranking",
        "Smart Transcript Review",
        "Hindi, Hinglish and Indian-English creator workflows",
        "Caption-safe vertical rendering",
        "Creator Studio drag-and-place captions, 65% to 160% sizing, alignment, zoom, reframe and Hook Text On/Off",
        "₹1 Creator Pulse YouTube channel intelligence",
        "Unlimited Post Karo publishing access to connected Instagram Reels and YouTube Shorts accounts on every plan",
        "Free plan, ₹59 one-time Mini Pass and Creator plan from ₹199 per month",
      ],
    },
    {
      "@type": "AboutPage",
      "@id": "https://clipkaro.pro/about#page",
      name: "About ClipKaro AI",
      url: "https://clipkaro.pro/about",
      description,
      about: { "@id": "https://clipkaro.pro/#software" },
      publisher: { "@id": "https://clipkaro.pro/#organization" },
      inLanguage: "en-IN",
      dateModified: "2026-09-23",
    },
    {
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "Home", item: "https://clipkaro.pro/" },
        { "@type": "ListItem", position: 2, name: "About ClipKaro AI", item: "https://clipkaro.pro/about" },
      ],
    },
  ],
};

export default function AboutPage() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(aboutStructuredData) }} />
      <div className={unified.wrap}><PublicSiteNav /><AboutExperience /><PublicSiteFooter /></div>
    </>
  );
}
