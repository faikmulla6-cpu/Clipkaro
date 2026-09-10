import type { Metadata } from "next";
import { PublicSiteFooter } from "@/components/PublicSiteFooter";
import { PublicSiteNav } from "@/components/PublicSiteNav";
import { AboutExperience } from "./AboutExperience";
import unified from "./unified.module.css";

const title = "About ClipKaro AI — Video Clipping & YouTube Creator Intelligence";
const description = "Discover how ClipKaro helps creators turn long videos into Shorts and use Creator Pulse to analyse public YouTube performance, find momentum and decide what to create next.";

export const metadata: Metadata = {
  title,
  description,
  keywords: ["ClipKaro AI", "AI video clipping", "YouTube creator intelligence", "YouTube channel analysis", "Creator Pulse", "YouTube video idea generator", "Indian creator AI"],
  alternates: { canonical: "/about" },
  openGraph: { type: "website", url: "/about", siteName: "ClipKaro AI", title, description, images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "ClipKaro AI" }] },
  twitter: { card: "summary_large_image", title, description, images: ["/assets/clipkaro-icon.png"] },
};

export default function AboutPage() {
  return <div className={unified.wrap}><PublicSiteNav /><AboutExperience /><PublicSiteFooter /></div>;
}
