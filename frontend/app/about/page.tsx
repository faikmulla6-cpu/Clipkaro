import type { Metadata } from "next";
import { AboutCreatorPulse } from "@/components/AboutCreatorPulse";
import { AboutExperience } from "./AboutExperience";

const title = "About ClipKaro AI — Video Clipping & YouTube Creator Intelligence";
const description = "Discover how ClipKaro helps creators turn long videos into Shorts and use Creator Pulse to analyse public YouTube performance, find momentum and decide what to create next.";

export const metadata: Metadata = {
  title,
  description,
  keywords: [
    "ClipKaro AI",
    "AI video clipping",
    "YouTube creator intelligence",
    "YouTube channel analysis",
    "Creator Pulse",
    "YouTube video idea generator",
    "Indian creator AI",
  ],
  alternates: { canonical: "/about" },
  openGraph: {
    type: "website",
    url: "/about",
    title,
    description,
    images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "ClipKaro AI" }],
  },
  twitter: {
    card: "summary_large_image",
    title,
    description,
    images: ["/assets/clipkaro-icon.png"],
  },
};

export default function AboutPage() {
  return (
    <>
      <AboutExperience />
      <AboutCreatorPulse />
    </>
  );
}
