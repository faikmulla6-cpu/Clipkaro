import type { Metadata } from "next";
import { PublicSiteFooter } from "@/components/PublicSiteFooter";
import { PublicSiteNav } from "@/components/PublicSiteNav";
import { AboutExperience } from "./AboutExperience";
import unified from "./unified.module.css";

const title = "About ClipKaro AI — YouTube URL to Shorts & Creator Video AI";
const description = "See how ClipKaro turns authorised YouTube URLs or uploaded video files into creator-ready Shorts with AI clip finding, transcript review and a resilient upload fallback.";

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
  "@type": "AboutPage",
  name: "About ClipKaro AI",
  url: "https://clipkaro.pro/about",
  description,
  about: {
    "@type": "SoftwareApplication",
    name: "ClipKaro AI",
    applicationCategory: "MultimediaApplication",
    operatingSystem: "Web",
    url: "https://clipkaro.pro/",
    featureList: [
      "YouTube URL import for supported videos, Shorts and live replays",
      "Original-file upload fallback when direct URL acquisition is unavailable",
      "AI clip detection and ranking",
      "Smart Transcript Review",
      "Hindi, Hinglish and Indian-English creator workflows",
      "Caption-safe vertical rendering",
      "Creator Studio editing and export controls",
      "Creator Pulse YouTube channel intelligence",
    ],
  },
};

export default function AboutPage() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(aboutStructuredData) }} />
      <div className={unified.wrap}><PublicSiteNav /><AboutExperience /><PublicSiteFooter /></div>
    </>
  );
}
