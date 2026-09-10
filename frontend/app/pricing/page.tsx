import type { Metadata } from "next";
import { PublicPricingView, type PublicPlanView } from "@/components/PublicPricingView";
import { PricingExperience } from "./PricingExperience";

const title = "ClipKaro AI Pricing — Free, Mini Pass and creator plans";
const description = "Compare ClipKaro AI plans for turning long videos into Shorts. Start free, buy a one-time Mini Pass, or choose a monthly creator, growth, pro, or agency plan.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: "/pricing" },
  openGraph: { type: "website", url: "/pricing", siteName: "ClipKaro AI", title, description, images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "ClipKaro AI" }] },
  twitter: { card: "summary_large_image", title, description, images: ["/assets/clipkaro-icon.png"] },
};

const publicPlans: PublicPlanView[] = [
  { id: "free", name: "Free", price: "₹0", suffix: "/month", tagline: "Try ClipKaro before paying", features: ["15 Karo Minutes / month", "2 Shorts / month", "720p with ClipKaro watermark"] },
  { id: "mini_pass", name: "Mini Pass", price: "₹59", suffix: " one-time", tagline: "No subscription. Use it when you need it.", features: ["25 Karo Minutes", "5 Shorts", "1080p · no watermark", "Valid for 30 days"] },
  { id: "creator", name: "Creator", price: "₹199", suffix: "/month", tagline: "For new creators building consistency", features: ["60 Karo Minutes / month", "15 Shorts / month", "1080p · no watermark", "Full AI clip quality"] },
  { id: "growth", name: "Growth", price: "₹399", suffix: "/month", tagline: "For serious creators publishing every week", features: ["180 Karo Minutes / month", "50 Shorts / month", "1080p · no watermark", "Brand kit + creator workflow"], popular: true },
  { id: "pro", name: "Pro", price: "₹799", suffix: "/month", tagline: "For daily creators and growing channels", features: ["480 Karo Minutes / month", "150 Shorts / month", "1080p · no watermark", "Priority creator workflow"] },
  { id: "agency", name: "Agency", price: "₹1,999", suffix: "/month", tagline: "For client work and high-volume teams", features: ["1,500 Karo Minutes / month", "500 Shorts / month", "1080p · no watermark", "Agency-scale usage"] },
];

export default function PricingPage() {
  return <PricingExperience publicFallback={<PublicPricingView plans={publicPlans} />} />;
}
