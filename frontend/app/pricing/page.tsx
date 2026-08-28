import type { Metadata } from "next";
import { PricingExperience } from "./PricingExperience";

const title = "ClipKaro AI Pricing — Free, Mini Pass and creator plans";
const description = "Compare ClipKaro AI plans for turning long videos into Shorts. Start free, buy a one-time Mini Pass, or choose a monthly creator, growth, pro, or agency plan.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: "/pricing" },
  openGraph: {
    type: "website",
    url: "/pricing",
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

export default function PricingPage() {
  return <PricingExperience />;
}
