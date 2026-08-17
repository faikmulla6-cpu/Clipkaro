export const LEGAL_VERSION = "2026-08-09";
export const LEGAL_EFFECTIVE_DATE = "9 August 2026";

export const LEGAL_LINKS = [
  ["Terms", "/terms"],
  ["Privacy", "/privacy"],
  ["Refunds", "/refund-policy"],
  ["Acceptable use", "/acceptable-use"],
  ["Copyright", "/copyright"],
  ["Legal notice", "/legal-notice"],
] as const;

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