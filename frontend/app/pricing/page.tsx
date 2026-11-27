import type { Metadata } from "next";
import { PublicPricingView } from "@/components/PublicPricingView";
import { PricingExperience } from "./PricingExperience";
import { PUBLIC_PRICING } from "@/lib/pricing-contract";
import { PUBLIC_PLAN_CARDS } from "@/lib/public-plan-cards";

const title = "ClipKaro Pricing — AI Shorts with Unlimited Paid Exports";
const description = "Affordable AI clipping: start free, try a ₹59 Mini Pass or subscribe. Eligible monthly plans offer optional top-ups at ₹3 per Karo Minute (10-minute minimum) and ₹2 per extra AI Short.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: "/pricing" },
  openGraph: { type: "website", url: "/pricing", siteName: "ClipKaro AI", title, description, images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "ClipKaro AI" }] },
  twitter: { card: "summary_large_image", title, description, images: ["/assets/clipkaro-icon.png"] },
};

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
      <PricingExperience publicFallback={<PublicPricingView plans={PUBLIC_PLAN_CARDS} />} />
    </>
  );
}
