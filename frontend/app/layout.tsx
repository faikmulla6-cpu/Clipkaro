import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/components/AuthProvider";

export const metadata: Metadata = {
  title: "ClipKaro AI — Long videos into ready-to-publish Shorts",
  description: "AI-assisted Shorts creation for Indian creators: upload, find strong moments, add captions, and export.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body>
        <style>{`
          .price {
            display: flex;
            align-items: baseline;
            gap: 8px;
            flex-wrap: wrap;
          }
          .price small {
            display: inline-block;
            margin-left: 0 !important;
            letter-spacing: 0 !important;
            line-height: 1.2;
            white-space: nowrap;
          }
        `}</style>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
