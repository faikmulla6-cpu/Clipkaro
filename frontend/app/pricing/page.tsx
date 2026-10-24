import type { Metadata } from "next";
import { PublicPricingView, type PublicPlanView } from "@/components/PublicPricingView";
import { PricingExperience } from "./PricingExperience";
import { PUBLIC_PRICING, planFeatureMinutes, planPriceLabel, smartLayoutFeature } from "@/lib/pricing-contract";

const title = "ClipKaro Pricing — AI Shorts with Unlimited Paid Exports";
const description = "Affordable AI video clipping for creators: start free, get a ₹59 Mini Pass with 5 AI Shorts, or choose a monthly plan. Every paid plan includes unlimited exports and re-exports.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: "/pricing" },
  openGraph: { type: "website", url: "/pricing", siteName: "ClipKaro AI", title, description, images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "ClipKaro AI" }] },
  twitter: { card: "summary_large_image", title, description, images: ["/assets/clipkaro-icon.png"] },
};

const publicPlans: PublicPlanView[] = [
  { id: "free", name: "Free", price: "₹0", suffix: "/month", tagline: "Try ClipKaro before paying", features: [smartLayoutFeature("free"), "2 AI Shorts / month", "15 total source-processing minutes / month", "Up to 2 exports / month", "Source media kept 24 hours", "720p with ClipKaro watermark", "Unlimited Post Karo · Instagram + YouTube"] },
  { id: "mini_pass", name: "Mini Pass", price: planPriceLabel("mini_pass"), suffix: " one-time", tagline: "5 finished AI Shorts", features: [smartLayoutFeature("mini_pass"), "5 finished AI Shorts", planFeatureMinutes("mini_pass"), "Creation ends at 5 Shorts, 25 total minutes, or 30 days", "Previously purchased passes retain their 125-minute allowance", "Unlimited re-exports of finished Shorts with retained source media", "1080p · no watermark", "Unlimited Post Karo · Instagram + YouTube"] },
  { id: "creator", name: "Creator", price: planPriceLabel("creator"), suffix: "/month", tagline: "For new creators building consistency", features: [smartLayoutFeature("creator"), "15 unique finished AI Shorts / month", planFeatureMinutes("creator"), "Unlimited re-exports of finished Shorts", "Paid source media kept up to 30 days", "1080p · no watermark", "Full AI clip quality", "Unlimited Post Karo · Instagram + YouTube"] },
  { id: "growth", name: "Growth", price: planPriceLabel("growth"), suffix: "/month", tagline: "For serious creators publishing every week", features: [smartLayoutFeature("growth"), "50 unique finished AI Shorts / month", planFeatureMinutes("growth"), "Unlimited re-exports of finished Shorts", "Paid source media kept up to 30 days", "1080p · no watermark", "Brand kit + creator workflow", "Unlimited Post Karo · Instagram + YouTube"], popular: true },
  { id: "pro", name: "Pro", price: planPriceLabel("pro"), suffix: "/month", tagline: "For daily creators and growing channels", features: [smartLayoutFeature("pro"), "150 unique finished AI Shorts / month", planFeatureMinutes("pro"), "Unlimited re-exports of finished Shorts", "Paid source media kept up to 30 days", "1080p · no watermark", "Priority creator workflow", "Unlimited Post Karo · Instagram + YouTube"] },
  { id: "agency", name: "Agency", price: "₹1,999", suffix: "/month", tagline: "For client work and high-volume teams", features: [smartLayoutFeature("agency"), "500 AI Shorts / month", "1,500 total source-processing minutes / month", "Unlimited exports & re-exports", "Paid source media kept up to 30 days", "1080p · no watermark", "Agency-scale usage", "Unlimited Post Karo · Instagram + YouTube"] },
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
    { "@type": "Offer", name: "Creator", price: String(PUBLIC_PRICING.creator.price), priceCurrency: "INR", url: "https://clipkaro.pro/pricing", priceSpecification: { "@type": "UnitPriceSpecification", price: String(PUBLIC_PRICING.creator.price), priceCurrency: "INR", unitText: "MONTH" } },
    { "@type": "Offer", name: "Growth", price: String(PUBLIC_PRICING.growth.price), priceCurrency: "INR", url: "https://clipkaro.pro/pricing", priceSpecification: { "@type": "UnitPriceSpecification", price: String(PUBLIC_PRICING.growth.price), priceCurrency: "INR", unitText: "MONTH" } },
    { "@type": "Offer", name: "Pro", price: String(PUBLIC_PRICING.pro.price), priceCurrency: "INR", url: "https://clipkaro.pro/pricing", priceSpecification: { "@type": "UnitPriceSpecification", price: String(PUBLIC_PRICING.pro.price), priceCurrency: "INR", unitText: "MONTH" } },
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
