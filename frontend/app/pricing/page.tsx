import type { Metadata } from "next";
import { PublicPricingView, type PublicPlanView } from "@/components/PublicPricingView";
import { PricingExperience } from "./PricingExperience";

const title = "ClipKaro Pricing — Start Free, ₹59 Mini Pass, Unlimited Post Karo";
const description = "Extremely affordable AI video clipping for creators: start free, get a ₹59 one-time Mini Pass or Creator from ₹199/month. Unlimited Post Karo publishing access is included on every plan.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: "/pricing" },
  openGraph: { type: "website", url: "/pricing", siteName: "ClipKaro AI", title, description, images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "ClipKaro AI" }] },
  twitter: { card: "summary_large_image", title, description, images: ["/assets/clipkaro-icon.png"] },
};

const publicPlans: PublicPlanView[] = [
  { id: "free", name: "Free", price: "₹0", suffix: "/month", tagline: "Try ClipKaro before paying", features: ["15 total source-processing minutes / month", "Up to 2 Short exports / month", "Source media kept 24 hours", "720p with ClipKaro watermark", "Unlimited Post Karo · Instagram + YouTube"] },
  { id: "mini_pass", name: "Mini Pass", price: "₹59", suffix: " one-time", tagline: "5 Shorts. Up to 25 minutes of source for each one.", features: ["5 Short credits", "Each Short can process a source video up to 25 min", "Up to 125 source-processing minutes across the pass", "Processed source kept until pass expiry · max 30 days", "1080p · no watermark", "Unlimited Post Karo · Instagram + YouTube"] },
  { id: "creator", name: "Creator", price: "₹199", suffix: "/month", tagline: "For new creators building consistency", features: ["60 total source-processing minutes / month", "Up to 15 Short exports / month", "Paid source media kept up to 30 days", "1080p · no watermark", "Full AI clip quality", "Unlimited Post Karo · Instagram + YouTube"] },
  { id: "growth", name: "Growth", price: "₹399", suffix: "/month", tagline: "For serious creators publishing every week", features: ["180 total source-processing minutes / month", "Up to 50 Short exports / month", "Paid source media kept up to 30 days", "1080p · no watermark", "Brand kit + creator workflow", "Unlimited Post Karo · Instagram + YouTube"], popular: true },
  { id: "pro", name: "Pro", price: "₹799", suffix: "/month", tagline: "For daily creators and growing channels", features: ["480 total source-processing minutes / month", "Up to 150 Short exports / month", "Paid source media kept up to 30 days", "1080p · no watermark", "Priority creator workflow", "Unlimited Post Karo · Instagram + YouTube"] },
  { id: "agency", name: "Agency", price: "₹1,999", suffix: "/month", tagline: "For client work and high-volume teams", features: ["1,500 total source-processing minutes / month", "Up to 500 Short exports / month", "Paid source media kept up to 30 days", "1080p · no watermark", "Agency-scale usage", "Unlimited Post Karo · Instagram + YouTube"] },
];

const pricingStructuredData = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "@id": "https://clipkaro.pro/#software",
  name: "ClipKaro AI",
  applicationCategory: "MultimediaApplication",
  operatingSystem: "Web",
  url: "https://clipkaro.pro/",
  description,
  offers: [
    { "@type": "Offer", name: "Free", price: "0", priceCurrency: "INR", url: "https://clipkaro.pro/pricing" },
    { "@type": "Offer", name: "Mini Pass", price: "59", priceCurrency: "INR", url: "https://clipkaro.pro/pricing", description: "One-time purchase valid for 30 days." },
    { "@type": "Offer", name: "Creator", price: "199", priceCurrency: "INR", url: "https://clipkaro.pro/pricing", priceSpecification: { "@type": "UnitPriceSpecification", price: "199", priceCurrency: "INR", unitText: "MONTH" } },
    { "@type": "Offer", name: "Growth", price: "399", priceCurrency: "INR", url: "https://clipkaro.pro/pricing", priceSpecification: { "@type": "UnitPriceSpecification", price: "399", priceCurrency: "INR", unitText: "MONTH" } },
    { "@type": "Offer", name: "Pro", price: "799", priceCurrency: "INR", url: "https://clipkaro.pro/pricing", priceSpecification: { "@type": "UnitPriceSpecification", price: "799", priceCurrency: "INR", unitText: "MONTH" } },
    { "@type": "Offer", name: "Agency", price: "1999", priceCurrency: "INR", url: "https://clipkaro.pro/pricing", priceSpecification: { "@type": "UnitPriceSpecification", price: "1999", priceCurrency: "INR", unitText: "MONTH" } },
  ],
};

export default function PricingPage() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(pricingStructuredData) }} />
      <PricingExperience publicFallback={<PublicPricingView plans={publicPlans} />} />
    </>
  );
}
