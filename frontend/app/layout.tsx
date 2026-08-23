import type { Metadata, Viewport } from "next";
import "./globals.css";
import "./mobile-audit.css";
import "./brand.css";
import "./interaction-polish.css";
import "./sidebar-polish.css";
import { AuthProvider } from "@/components/AuthProvider";

const brandIcon = "/assets/clipkaro-icon.png?v=2";
const tabIcon = "/assets/clipkaro-tab-icon.svg?v=1";

export const metadata: Metadata = {
  metadataBase: new URL("https://clipkaro.pro"),
  title: "ClipKaro AI — Long videos into ready-to-publish Shorts",
  description: "AI-assisted Shorts creation for Indian creators: upload, find strong moments, add captions, and export.",
  applicationName: "ClipKaro AI",
  manifest: "/site.webmanifest",
  icons: {
    icon: [{ url: tabIcon, type: "image/svg+xml" }],
    shortcut: tabIcon,
    apple: brandIcon,
  },
  openGraph: {
    type: "website",
    url: "https://clipkaro.pro",
    siteName: "ClipKaro AI",
    title: "ClipKaro AI — Long videos into ready-to-publish Shorts",
    description: "AI-assisted Shorts creation for Indian creators: upload, find strong moments, add captions, and export.",
    images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "ClipKaro AI" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "ClipKaro AI — Long videos into ready-to-publish Shorts",
    description: "AI-assisted Shorts creation for Indian creators: upload, find strong moments, add captions, and export.",
    images: ["/assets/clipkaro-icon.png"],
  },
};

export const viewport: Viewport = {
  themeColor: "#07110d",
  colorScheme: "light",
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

          @media (max-width: 640px) {
            .hero {
              padding-left: 16px;
              padding-right: 16px;
            }
            .hero h1 {
              max-width: 100%;
              font-size: clamp(40px, 11.2vw, 50px);
              line-height: 0.99;
              letter-spacing: -2.5px;
              overflow-wrap: break-word;
            }
            .lime-underline {
              white-space: normal;
              background: linear-gradient(
                to bottom,
                transparent 79%,
                var(--lime) 79%,
                var(--lime) 95%,
                transparent 95%
              );
              -webkit-box-decoration-break: clone;
              box-decoration-break: clone;
            }
            .lime-underline::after {
              display: none;
            }
          }
        `}</style>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
