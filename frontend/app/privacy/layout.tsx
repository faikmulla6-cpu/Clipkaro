import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ClipKaro Privacy Notice",
  description: "Read how ClipKaro AI handles account data, creator media, processing data, connected publishing credentials, retention, security and privacy rights.",
  alternates: { canonical: "/privacy" },
  openGraph: { type: "website", url: "/privacy", siteName: "ClipKaro AI", title: "ClipKaro Privacy Notice", description: "Read how ClipKaro AI handles account data, creator media, processing data, connected publishing credentials, retention, security and privacy rights." },
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
