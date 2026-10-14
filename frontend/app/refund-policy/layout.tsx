import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ClipKaro Refund Policy",
  description: "Read ClipKaro AI refund and cancellation rules for Mini Pass purchases and recurring creator plans before checkout.",
  alternates: { canonical: "/refund-policy" },
  openGraph: { type: "website", url: "/refund-policy", siteName: "ClipKaro AI", title: "ClipKaro Refund Policy", description: "Read ClipKaro AI refund and cancellation rules for Mini Pass purchases and recurring creator plans before checkout." },
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
