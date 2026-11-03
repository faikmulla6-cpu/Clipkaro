import type { Metadata, Viewport } from "next";
import "./tailwind.css";
import "./globals.css";
import "./mobile-audit.css";
import "./brand.css";
import "./interaction-polish.css";
import "./sidebar-polish.css";
import "./quality-fixes.css";
import "./frontend-audit-fixes.css";
import { AuthProvider } from "@/components/AuthProvider";

const brandIcon = "/assets/clipkaro-icon.png?v=2";
const tabIcon = "/assets/clipkaro-icon.png?v=4";

export const metadata: Metadata = {
  metadataBase: new URL("https://clipkaro.pro"),
  title: "ClipKaro AI — YouTube URL to Shorts & AI Video Clipper",
  description: "Paste a supported YouTube URL or upload the original file, then turn long-form video into creator-ready Shorts with AI clip finding, captions, editing and export controls.",
  applicationName: "ClipKaro AI",
  keywords: [
    "AI video clipper",
    "YouTube URL to Shorts",
    "paste YouTube link to Shorts",
    "YouTube video clipper",
    "AI Shorts maker",
    "Hinglish video clipper",
    "Indian creator AI",
    "Hindi Shorts maker",
    "long video to Shorts",
    "YouTube Shorts generator",
    "Instagram Reels maker",
    "AI captions for Indian creators",
    "video content repurposing",
    "ClipKaro AI",
  ],
  alternates: {
    canonical: "/",
  },
  manifest: "/site.webmanifest",
  icons: {
    icon: [{ url: tabIcon, type: "image/png" }],
    shortcut: tabIcon,
    apple: brandIcon,
  },
  openGraph: {
    type: "website",
    url: "https://clipkaro.pro",
    siteName: "ClipKaro AI",
    title: "ClipKaro AI — YouTube URL to Shorts & AI Video Clipper",
    description: "Start with a supported YouTube URL or original-file upload, then find strong moments, review transcripts, refine captions and export creator-ready Shorts.",
    images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "ClipKaro AI video clipping and content repurposing platform" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "ClipKaro AI — YouTube URL to Shorts & AI Video Clipper",
    description: "YouTube URL intake with original-file fallback, AI clip finding, transcript review, captions, vertical exports and Content Packs for creators.",
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
