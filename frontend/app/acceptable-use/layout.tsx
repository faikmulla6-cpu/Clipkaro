import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ClipKaro Acceptable Use Policy",
  description: "Read the ClipKaro AI acceptable-use rules for authorised creator media, AI video clipping, exports and connected social publishing.",
  alternates: { canonical: "/acceptable-use" },
  openGraph: { type: "website", url: "/acceptable-use", siteName: "ClipKaro AI", title: "ClipKaro Acceptable Use Policy", description: "Read the ClipKaro AI acceptable-use rules for authorised creator media, AI video clipping, exports and connected social publishing." },
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
