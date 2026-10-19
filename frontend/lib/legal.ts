export const LEGAL_VERSION = "2026-10-20-r1";
export const LEGAL_EFFECTIVE_DATE = "20 October 2026";

export const LEGAL_LINKS = [
  ["Terms", "/terms"],
  ["Privacy", "/privacy"],
  ["Refunds", "/refund-policy"],
  ["Acceptable use", "/acceptable-use"],
  ["Copyright", "/copyright"],
  ["Legal notice", "/legal-notice"],
] as const;

export const TRUST_PROFILE = {
  serviceName: "ClipKaro AI",
  website: "https://clipkaro.pro",
  founderName: "Faik Hameed Mulla",
  founderTitle: "Founder and Owner",
  supportEmail: "support@clipkaro.pro",
  privacyEmail: "privacy@clipkaro.pro",
  legalEmail: "legal@clipkaro.pro",
  grievanceEmail: "grievance@clipkaro.pro",
  supportExpectation: "Support and billing questions are normally acknowledged within 48 hours. Consumer grievances are targeted for resolution within one month, subject to the information and payment-provider investigation needed.",
  mediaRetention: "Free-plan source videos and rendered export files expire automatically after the configured short media-retention window, currently 24 hours. Paid-plan source videos are retained for up to 30 days so creators can return to processed projects and export or re-export created Shorts. New Mini Pass creation access expires when 5 finished AI Shorts or 25 total Karo Minutes are used, or after 30 days, whichever comes first; previously purchased passes retain their original 125-minute entitlement. Exhausting creation credits does not immediately delete already-retained source media needed for those created Shorts. Rendered export files still use the short retention window, so creators should download finished files they want to keep. Project records, derived transcripts, clip suggestions, billing records and security logs may be retained for account history, support, legal, fraud, security and product-quality reasons.",
  deletionSummary: "Creators can delete projects in the product. Account or personal-data deletion can be requested through the privacy or grievance contacts, subject to records ClipKaro must keep for billing, tax, fraud, security, dispute or legal reasons.",
} as const;

export type LegalConfig = {
  service_name: string;
  website: string;
  version: string;
  effective_date: string;
  paid_launch_ready: boolean;
  operator_name: string;
  operator_address: string;
  legal_email: string;
  privacy_email: string;
  customer_care_email: string;
  customer_care_phone: string;
  grievance_officer_name: string;
  grievance_email: string;
  grievance_phone: string;
  gstin: string;
  pan: string;
  documents: string[];
};

export type LegalStatus = {
  version: string;
  effective_date: string;
  accepted: boolean;
  accepted_at?: string | null;
  paid_launch_ready: boolean;
  checkout_allowed: boolean;
  checkout_reason: string;
  razorpay_mode: "test" | "live";
  real_money: boolean;
  development_live_opt_in: boolean;
};
