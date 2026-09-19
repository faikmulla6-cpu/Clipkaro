import type { Metadata } from "next";
import { HomeExperience } from "@/components/HomeExperience";
import { LEGAL_LINKS } from "@/lib/legal";

export const metadata: Metadata = {
  title: "ClipKaro AI — YouTube URL to Shorts & AI Video Clipper",
  description: "Paste a supported YouTube URL or upload the original video, then turn long-form content into creator-ready Shorts with AI clip finding, captions and editing.",
  keywords: [
    "AI video clipper",
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
  ],
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    url: "/",
    siteName: "ClipKaro AI",
    title: "ClipKaro AI — YouTube URL to Shorts & AI Video Clipper",
    description: "Paste a supported YouTube link or upload the original file, then find strong moments, refine captions and framing, and export creator-ready Shorts.",
    images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "ClipKaro AI creator workflow platform" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "ClipKaro AI — YouTube URL to Shorts & AI Video Clipper",
    description: "Paste a supported YouTube URL or upload the source file, then turn long-form video into creator-ready Shorts with ClipKaro AI.",
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
  description: "AI video clipping, YouTube URL import, resilient original-file upload fallback, content repurposing and YouTube creator intelligence for Indian creators, including clip detection, transcript review, India Quality Mode, captions, vertical export, Content Packs and Creator Pulse.",
  offers: {
    "@type": "AggregateOffer",
    priceCurrency: "INR",
    lowPrice: "0",
    highPrice: "1999",
    offerCount: "6",
  },
  featureList: [
    "YouTube URL import for supported videos, Shorts and live replays",
    "Original-file upload fallback when direct URL acquisition is unavailable",
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

const faqStructuredData = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: [
    {
      "@type": "Question",
      name: "Can I paste a YouTube URL into ClipKaro?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Yes. ClipKaro accepts supported YouTube video, Shorts and live-replay URLs. You must own the video or have permission to process it.",
      },
    },
    {
      "@type": "Question",
      name: "What happens if a YouTube URL cannot be imported?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "If direct acquisition is unavailable for a source, ClipKaro provides an original-file upload fallback so the creator can continue the same analysis, editing and export workflow.",
      },
    },
    {
      "@type": "Question",
      name: "Can ClipKaro turn a long YouTube video into Shorts?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "ClipKaro can analyse an authorised source video, rank promising moments, support transcript review, captions and reframing, and render creator-approved short-form exports.",
      },
    },
  ],
};

const urlToShortsHowToStructuredData = {
  "@context": "https://schema.org",
  "@type": "HowTo",
  name: "How to turn a YouTube URL into Shorts with ClipKaro",
  description: "Start from a supported YouTube link or upload the original file, then analyse, review and export creator-approved Shorts.",
  step: [
    { "@type": "HowToStep", name: "Paste the YouTube URL", text: "Paste an authorised YouTube video, Shorts or live-replay URL. If direct acquisition is unavailable, upload the original file instead." },
    { "@type": "HowToStep", name: "Analyse the video", text: "ClipKaro transcribes the source and ranks promising moments." },
    { "@type": "HowToStep", name: "Review and refine", text: "Review the suggested moments, transcript, captions and framing." },
    { "@type": "HowToStep", name: "Export the Short", text: "Render the creator-approved short-form output in the selected format." },
  ],
};

export default function Home() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteStructuredData) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareStructuredData) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqStructuredData) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(urlToShortsHowToStructuredData) }} />
      <HomeExperience />
    </>
  );
}
