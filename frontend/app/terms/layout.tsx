import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ClipKaro Terms of Service",
  description: "Read ClipKaro AI Terms of Service covering account use, creator-content rights, AI limitations, paid plans, cancellations, publishing responsibilities and disputes.",
  alternates: { canonical: "/terms" },
  openGraph: { type: "website", url: "/terms", siteName: "ClipKaro AI", title: "ClipKaro Terms of Service", description: "Read ClipKaro AI Terms of Service covering account use, creator-content rights, AI limitations, paid plans, cancellations, publishing responsibilities and disputes." },
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
