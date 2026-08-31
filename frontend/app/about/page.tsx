import type { Metadata } from "next";
import { AboutExperience } from "./AboutExperience";

const title = "About ClipKaro — AI video intelligence for Indian creators";
const description = "Discover ClipKaro's creator workflow: AI clip ranking, India Quality Mode, Smart Transcript Review, Content Packs, caption-safe export, zoom and reframe controls.";

export const metadata: Metadata = {
  title,
  description,
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
  return <AboutExperience />;
}
