import type { Metadata } from "next";
import { AboutExperience } from "./AboutExperience";

const title = "About ClipKaro — AI video intelligence built for creators";
const description = "Discover why ClipKaro was built, how its AI media pipeline works, the principles behind the product, and the story of founder Faik Hameed Mulla.";

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
