import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ClipKaro Copyright Policy",
  description: "Read ClipKaro AI copyright rules, creator-content responsibilities and how to report copyright concerns.",
  alternates: { canonical: "/copyright" },
  openGraph: { type: "website", url: "/copyright", siteName: "ClipKaro AI", title: "ClipKaro Copyright Policy", description: "Read ClipKaro AI copyright rules, creator-content responsibilities and how to report copyright concerns." },
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
