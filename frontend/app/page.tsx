import type { Metadata } from "next";
import { HomeExperience } from "@/components/HomeExperience";
import { LEGAL_LINKS, TRUST_PROFILE } from "@/lib/legal";

export const metadata: Metadata = {
  title: { absolute: "ClipKaro AI — Long Video to Shorts + Unlimited Post Karo" },
  description: "Turn long videos into Shorts with AI-ranked moments, speaker-aware Smart Layout framing, Creator Studio editing and unlimited Post Karo publishing access. Start free.",
  keywords: [
    "AI video clipper",
    "Smart Layout podcast video framing",
    "Dual Stack speaker layout",
    "Auto Director Shorts",
    "Speaker Focus portrait video",
    "YouTube URL to Shorts",
    "paste YouTube link to Shorts",
    "YouTube link video clipper",
    "upload video to Shorts",
    "YouTube Shorts maker",
    "YouTube channel analyzer",
    "YouTube channel analysis",
    "AI YouTube analytics",
    "YouTube analytics for creators",
    "YouTube video idea generator",
    "long video to Shorts",
    "Hinglish video clipper",
    "Hindi video to Reels",
    "ClipKaro Creator Pulse",
    "AI video clipper India",
    "post Shorts to Instagram",
    "post Shorts to YouTube",
    "unlimited social publishing for creators",
    "affordable AI video clipper India",
    "affordable clipping website with unlimited posting",
    "AI video clipper unlimited posting",
    "AI Shorts editor captions",
    "long video to Reels",
  ],
  alternates: { canonical: "/" },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
  openGraph: {
    type: "website",
    url: "/",
    siteName: "ClipKaro AI",
    title: "ClipKaro AI — Long Video to Shorts + Unlimited Post Karo",
    description: "Turn long videos into Shorts with AI-ranked clips, speaker-aware Smart Layout modes, Creator Studio editing and unlimited Post Karo access.",
    images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "ClipKaro AI creator workflow platform" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "ClipKaro AI — Long Video to Shorts + Unlimited Post Karo",
    description: "AI clipping, creator-controlled editing, ₹1 Creator Pulse intelligence and unlimited Post Karo publishing access for Instagram Reels + YouTube Shorts.",
    images: ["/assets/clipkaro-icon.png"],
  },
};

const organizationStructuredData = {
  "@context": "https://schema.org",
  "@type": "Organization",
  "@id": "https://clipkaro.pro/#organization",
  name: "ClipKaro AI",
  alternateName: ["ClipKaro", "ClipKaroAI"],
  url: "https://clipkaro.pro/",
  logo: "https://clipkaro.pro/assets/clipkaro-icon.png",
  founder: {
    "@type": "Person",
    name: TRUST_PROFILE.founderName,
    jobTitle: TRUST_PROFILE.founderTitle,
  },
  contactPoint: {
    "@type": "ContactPoint",
    contactType: "customer support",
    email: TRUST_PROFILE.supportEmail,
    url: "https://clipkaro.pro/contact",
  },
  description: "ClipKaro AI is an India-first AI video clipping and creator workflow platform that turns long-form video into creator-reviewed Shorts, provides Creator Studio editing and supports unlimited Post Karo publishing access to Instagram Reels and YouTube Shorts on every plan.",
  knowsAbout: ["AI video clipping", "short-form video repurposing", "YouTube Shorts", "Instagram Reels", "Hindi and Hinglish creator workflows", "creator publishing workflows"],
};

const websiteStructuredData = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  "@id": "https://clipkaro.pro/#website",
  name: "ClipKaro AI",
  alternateName: ["ClipKaro", "ClipKaroAI"],
  url: "https://clipkaro.pro/",
  publisher: { "@id": "https://clipkaro.pro/#organization" },
  inLanguage: "en-IN",
  hasPart: LEGAL_LINKS.map(([name, href]) => ({
    "@type": "WebPage",
    name,
    url: `https://clipkaro.pro${href}`,
  })),
};

const homePageStructuredData = {
  "@context": "https://schema.org",
  "@type": "WebPage",
  "@id": "https://clipkaro.pro/#home",
  url: "https://clipkaro.pro/",
  name: "ClipKaro AI — Long Video to Shorts + Unlimited Post Karo",
  description: "Turn long videos into Shorts with AI-ranked moments, Creator Studio editing, ₹1 Creator Pulse intelligence and unlimited Post Karo publishing access.",
  isPartOf: { "@id": "https://clipkaro.pro/#website" },
  about: { "@id": "https://clipkaro.pro/#software" },
  publisher: { "@id": "https://clipkaro.pro/#organization" },
  inLanguage: "en-IN",
  dateModified: "2026-10-26",
};

const softwareStructuredData = {
  "@context": "https://schema.org",
  "@type": ["SoftwareApplication", "WebApplication"],
  "@id": "https://clipkaro.pro/#software",
  name: "ClipKaro AI",
  url: "https://clipkaro.pro/",
  applicationCategory: "MultimediaApplication",
  operatingSystem: "Web",
  publisher: { "@id": "https://clipkaro.pro/#organization" },
  mainEntityOfPage: { "@id": "https://clipkaro.pro/#website" },
  description: "India-first AI video clipping and creator workflow software: turn long videos into ranked Shorts, refine them in Creator Studio, use ₹1 Creator Pulse for next-video intelligence, and publish with unlimited Post Karo access to Instagram Reels and YouTube Shorts.",
  isAccessibleForFree: true,
  browserRequirements: "Modern web browser with internet access",
  offers: {
    "@type": "Offer",
    priceCurrency: "INR",
    price: "0",
    url: "https://clipkaro.pro/pricing",
    description: "Start free. A ₹59 one-time Mini Pass and monthly creator plans are also available; unlimited Post Karo publishing access is included on every plan.",
  },
  audience: {
    "@type": "Audience",
    audienceType: "YouTubers, podcasters, educators, coaches, founders, businesses and creator teams",
  },
  inLanguage: ["en", "hi", "hi-Latn"],
  featureList: [
    "YouTube URL import for supported videos, Shorts and live replays",
    "Original-file upload fallback when direct URL acquisition is unavailable",
    "AI clip detection and ranking",
    "Premium Smart Layout with Auto Director, Dual Stack and Speaker Focus portrait framing",
    "Smart Transcript Review with inline corrections",
    "India Quality Mode for Hindi, Hinglish and Indian-English creator workflows",
    "Roman Hinglish caption support",
    "Caption-safe vertical video rendering",
    "Creator Studio zoom and manual horizontal reframe controls",
    "9:16, 4:5 and 1:1 export controls",
    "Drag-and-place captions with 65% to 160% size control and automatic text reflow",
    "Left, centre and right caption alignment",
    "Hook Text on/off control",
    "Caption presets, source-caption preservation and Brand Kit controls",
    "One video to complete Content Pack",
    "Unlimited Post Karo publishing access to connected Instagram Reels and YouTube Shorts accounts on every plan",
    "Publishing copy for additional social workflows",
    "₹1 Creator Pulse YouTube channel analysis",
    "Verified recent-upload momentum comparison",
    "Evidence-led next-video recommendation with title, angle and opening hook",
    "One downloadable Creator Pulse thumbnail when generation is available",
    "Saved Creator Pulse history and previous-scan comparison",
    "Private source and export media handling",
    "Free plan with 15 Karo Minutes and 2 Shorts per month",
    "₹59 one-time Mini Pass and Creator plan from ₹249 per month",
  ],
};


export default function Home() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationStructuredData) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteStructuredData) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareStructuredData) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(homePageStructuredData) }} />
      <HomeExperience />
    </>
  );
}
