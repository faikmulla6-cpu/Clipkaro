import type { Metadata } from "next";
import { HomeExperience } from "@/components/HomeExperience";
import { LEGAL_LINKS } from "@/lib/legal";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export const metadata: Metadata = {
  title: "ClipKaro AI — AI Video Clipper, Shorts Maker & Creator Pulse",
  description: "Turn long videos into Shorts with AI-ranked moments, transcript review, India-first captions and creator controls. Use Creator Pulse for ₹1 YouTube channel analysis and one clear next-content move.",
  keywords: [
    "AI video clipper",
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
  ],
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    url: "/",
    siteName: "ClipKaro AI",
    title: "ClipKaro AI — AI Video Clipper, Shorts Maker & Creator Pulse",
    description: "Turn long videos into creator-ready Shorts, then use Creator Pulse to understand public YouTube momentum and decide what to create next.",
    images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "ClipKaro AI creator workflow platform" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "ClipKaro AI — AI Video Clipper, Shorts Maker & Creator Pulse",
    description: "AI video clipping plus ₹1 Creator Pulse channel intelligence for creators.",
    images: ["/assets/clipkaro-icon.png"],
  },
};

const websiteStructuredData = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: "ClipKaro AI",
  alternateName: ["ClipKaro", "ClipKaroAI"],
  url: "https://clipkaro.pro/",
  hasPart: LEGAL_LINKS.map(([name, href]) => ({
    "@type": "WebPage",
    name,
    url: `https://clipkaro.pro${href}`,
  })),
};

const softwareStructuredData = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "ClipKaro AI",
  url: "https://clipkaro.pro/",
  applicationCategory: "MultimediaApplication",
  operatingSystem: "Web",
  description: "AI video clipping, content repurposing and YouTube creator intelligence for Indian creators, including clip detection, transcript review, India Quality Mode, captions, vertical export, Content Packs and Creator Pulse.",
  offers: {
    "@type": "AggregateOffer",
    priceCurrency: "INR",
    lowPrice: "0",
    highPrice: "1999",
    offerCount: "6",
  },
  featureList: [
    "AI clip detection and ranking",
    "Smart Transcript Review with inline corrections",
    "India Quality Mode for Hindi, Hinglish and Indian-English creator workflows",
    "Roman Hinglish caption support",
    "Caption-safe vertical video rendering",
    "Creator Studio zoom and horizontal reframe controls",
    "9:16, 4:5 and 1:1 export controls",
    "Caption style and caption position controls",
    "One video to complete Content Pack",
    "YouTube Shorts, Instagram, X and LinkedIn publishing copy",
    "₹1 Creator Pulse YouTube channel analysis",
    "Verified recent-upload momentum comparison",
    "Evidence-led next-video recommendation with title, angle and opening hook",
    "One downloadable Creator Pulse thumbnail when generation is available",
    "Saved Creator Pulse history and previous-scan comparison",
    "Private source and export media handling",
    "Brand Kit support",
  ],
};

export default function Home() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteStructuredData) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareStructuredData) }} />
      <HomeExperience />
    </>
  );
}
