import { cartoonFeature, planFeatureMinutes, planPriceLabel, smartLayoutFeature, type PricingPlanId } from "./pricing-contract";

export type PublicPlanView = {
  id: PricingPlanId;
  name: string;
  price: string;
  suffix: string;
  tagline: string;
  features: string[];
  popular?: boolean;
};

export const PUBLIC_PLAN_CARDS: readonly PublicPlanView[] = [
  {
    id: "free",
    name: "Free",
    price: planPriceLabel("free"),
    suffix: "/month",
    tagline: "Try ClipKaro before paying",
    features: [
      cartoonFeature("free"),
      smartLayoutFeature("free"),
      "2 AI Shorts / month",
      "15 total source-processing minutes / month",
      "Up to 2 exports / month",
      "Source media kept 24 hours",
      "720p with ClipKaro watermark",
      "Unlimited Post Karo · Instagram + YouTube",
    ],
  },
  {
    id: "mini_pass",
    name: "Mini Pass",
    price: planPriceLabel("mini_pass"),
    suffix: " one-time",
    tagline: "5 finished AI Shorts",
    features: [
      cartoonFeature("mini_pass"),
      smartLayoutFeature("mini_pass"),
      "5 finished AI Shorts",
      planFeatureMinutes("mini_pass"),
      "Creation ends at 5 Shorts, 25 total minutes, or 30 days",
      "Previously purchased passes retain their 125-minute allowance",
      "Unlimited re-exports of finished Shorts with retained source media",
      "1080p · no watermark",
      "Unlimited Post Karo · Instagram + YouTube",
    ],
  },
  {
    id: "creator",
    name: "Creator",
    price: planPriceLabel("creator"),
    suffix: "/month",
    tagline: "For new creators building consistency",
    features: [
      cartoonFeature("creator"),
      smartLayoutFeature("creator"),
      "15 unique finished AI Shorts / month",
      planFeatureMinutes("creator"),
      "Unlimited re-exports of finished Shorts",
      "Paid source media kept up to 30 days",
      "1080p · no watermark",
      "Full AI clip quality",
      "Unlimited Post Karo · Instagram + YouTube",
    ],
  },
  {
    id: "growth",
    name: "Growth",
    price: planPriceLabel("growth"),
    suffix: "/month",
    tagline: "For serious creators publishing every week",
    features: [
      cartoonFeature("growth"),
      smartLayoutFeature("growth"),
      "50 unique finished AI Shorts / month",
      planFeatureMinutes("growth"),
      "Unlimited re-exports of finished Shorts",
      "Paid source media kept up to 30 days",
      "1080p · no watermark",
      "Brand kit + creator workflow",
      "Unlimited Post Karo · Instagram + YouTube",
    ],
    popular: true,
  },
  {
    id: "pro",
    name: "Pro",
    price: planPriceLabel("pro"),
    suffix: "/month",
    tagline: "For daily creators and growing channels",
    features: [
      cartoonFeature("pro"),
      smartLayoutFeature("pro"),
      "150 unique finished AI Shorts / month",
      planFeatureMinutes("pro"),
      "Unlimited re-exports of finished Shorts",
      "Paid source media kept up to 30 days",
      "1080p · no watermark",
      "Priority creator workflow",
      "Unlimited Post Karo · Instagram + YouTube",
    ],
  },
  {
    id: "agency",
    name: "Agency",
    price: planPriceLabel("agency"),
    suffix: "/month",
    tagline: "For client work and high-volume teams",
    features: [
      cartoonFeature("agency"),
      smartLayoutFeature("agency"),
      "500 AI Shorts / month",
      "1,500 total source-processing minutes / month",
      "Unlimited exports & re-exports",
      "Paid source media kept up to 30 days",
      "1080p · no watermark",
      "Agency-scale usage",
      "Unlimited Post Karo · Instagram + YouTube",
    ],
  },
];
