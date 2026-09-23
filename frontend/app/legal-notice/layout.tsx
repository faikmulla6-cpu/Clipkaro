import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ClipKaro Legal & Consumer Information",
  description: "Review ClipKaro AI operator, consumer, billing, support and grievance information before using paid creator services.",
  alternates: { canonical: "/legal-notice" },
  openGraph: { type: "website", url: "/legal-notice", siteName: "ClipKaro AI", title: "ClipKaro Legal & Consumer Information", description: "Review ClipKaro AI operator, consumer, billing, support and grievance information before using paid creator services." },
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
