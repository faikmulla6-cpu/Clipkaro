import type { Metadata } from "next";
import { HomeExperience } from "@/components/HomeExperience";
import { LEGAL_LINKS } from "@/lib/legal";

export const metadata: Metadata = {
  title: { absolute: "ClipKaro AI — AI Video Clipper for YouTube Shorts & Reels" },
  description: "Turn long videos into Shorts with ClipKaro AI: import a supported YouTube URL or upload a file, find strong moments, edit captions and framing, then publish to Instagram Reels or YouTube Shorts with free Post Karo.",
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
    "AI video clipper India",
    "post Shorts to Instagram",
    "post Shorts to YouTube",
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
    title: "ClipKaro AI — AI Video Clipper for YouTube Shorts & Reels",
    description: "From one long video to strong Shorts: find moments with AI, review captions and framing, export, then publish to Instagram Reels or YouTube Shorts from ClipKaro.",
    images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "ClipKaro AI creator workflow platform" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "ClipKaro AI — AI Video Clipper for YouTube Shorts & Reels",
    description: "ClipKaro AI turns long videos into creator-ready Shorts and lets you publish finished clips to Instagram Reels and YouTube Shorts with free Post Karo.",
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
  description: "ClipKaro AI is an AI video clipper and video repurposing platform for creators, educators, podcasters and businesses that turns long-form video into short-form clips and supports direct publishing to Instagram Reels and YouTube Shorts.",
};

const websiteStructuredData = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  "@id": "https://clipkaro.pro/#website",
  name: "ClipKaro AI",
  alternateName: ["ClipKaro", "ClipKaroAI"],
  url: "https://clipkaro.pro/",
  publisher: { "@id": "https://clipkaro.pro/#organization" },
  hasPart: LEGAL_LINKS.map(([name, href]) => ({
    "@type": "WebPage",
    name,
    url: `https://clipkaro.pro${href}`,
  })),
};

const softwareStructuredData = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "@id": "https://clipkaro.pro/#software",
  name: "ClipKaro AI",
  url: "https://clipkaro.pro/",
  applicationCategory: "MultimediaApplication",
  operatingSystem: "Web",
  publisher: { "@id": "https://clipkaro.pro/#organization" },
  mainEntityOfPage: { "@id": "https://clipkaro.pro/#website" },
  description: "AI video clipping and repurposing for Indian creators: supported YouTube URL import, original-file upload fallback, ranked clip discovery, transcript review, Hindi/Hinglish workflows, captions, vertical editing, export, free Post Karo publishing to Instagram Reels and YouTube Shorts, Content Packs and Creator Pulse.",
  offers: {
    "@type": "Offer",
    priceCurrency: "INR",
    price: "0",
    url: "https://clipkaro.pro/pricing",
    description: "A free plan is available; paid plans are listed on the pricing page.",
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
    "Smart Transcript Review with inline corrections",
    "India Quality Mode for Hindi, Hinglish and Indian-English creator workflows",
    "Roman Hinglish caption support",
    "Caption-safe vertical video rendering",
    "Creator Studio zoom and horizontal reframe controls",
    "9:16, 4:5 and 1:1 export controls",
    "Caption style and caption position controls",
    "One video to complete Content Pack",
    "Free Post Karo publishing to connected Instagram Reels and YouTube Shorts accounts",
    "Publishing copy for additional social workflows",
    "₹1 Creator Pulse YouTube channel analysis",
    "Verified recent-upload momentum comparison",
    "Evidence-led next-video recommendation with title, angle and opening hook",
    "One downloadable Creator Pulse thumbnail when generation is available",
    "Saved Creator Pulse history and previous-scan comparison",
    "Private source and export media handling",
    "Brand Kit support",
    "Free plan with Post Karo included",
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
    {
      "@type": "Question",
      name: "Can ClipKaro publish finished Shorts directly to Instagram and YouTube?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Yes. Post Karo lets signed-in users publish finished Shorts to connected Instagram Reels and YouTube Shorts accounts after the creator reviews and confirms the post. Post Karo is included on every ClipKaro plan, including Free.",
      },
    },
    {
      "@type": "Question",
      name: "Is Post Karo free?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "Yes. Post Karo is included on every ClipKaro plan, including Free. Plan limits still control Karo Minutes, Short creation capacity, export resolution and watermark rules.",
      },
    },
    {
      "@type": "Question",
      name: "Who is ClipKaro built for?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "ClipKaro is built for YouTubers, podcasters, educators, coaches, founders, businesses and creator teams that already have long-form video and want a faster create-to-publish workflow.",
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
    { "@type": "HowToStep", name: "Export or publish the Short", text: "Render the creator-approved short-form output, then download it or publish to a connected Instagram Reels or YouTube Shorts account with Post Karo." },
  ],
};

export default function Home() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationStructuredData) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteStructuredData) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareStructuredData) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqStructuredData) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(urlToShortsHowToStructuredData) }} />
      <HomeExperience />
    </>
  );
}
