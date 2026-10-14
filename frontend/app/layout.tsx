import type { Metadata, Viewport } from "next";
import "./tailwind.css";
import "./globals.css";
import "./mobile-audit.css";
import "./brand.css";
import "./interaction-polish.css";
import "./sidebar-polish.css";
import "./quality-fixes.css";
import "./frontend-audit-fixes.css";
import "./pro-editor.css";
import { AuthProvider } from "@/components/AuthProvider";

const brandIcon = "/assets/clipkaro-icon.png?v=2";
const tabIcon = "/assets/clipkaro-icon.png?v=4";

const browserCsp = "default-src 'self'; base-uri 'self'; object-src 'none'; form-action 'self' https://*.razorpay.com; img-src 'self' data: blob: https://storage.googleapis.com https://*.razorpay.com; media-src 'self' blob: https://storage.googleapis.com https://*.backblazeb2.com https://*.r2.cloudflarestorage.com; font-src 'self' data: https://fonts.gstatic.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; script-src 'self' 'unsafe-inline' https://checkout.razorpay.com https://*.razorpay.com; connect-src 'self' https://storage.googleapis.com https://*.backblazeb2.com https://*.r2.cloudflarestorage.com https://*.razorpay.com wss://*.razorpay.com; frame-src https://*.razorpay.com; worker-src 'self' blob:; manifest-src 'self'; upgrade-insecure-requests";

export const metadata: Metadata = {
  metadataBase: new URL("https://clipkaro.pro"),
  title: "ClipKaro AI — AI Video Clipper for Shorts, Reels & Post Karo",
  description: "Turn long videos into creator-ready Shorts with AI-ranked moments, Creator Studio editing, ₹1 Creator Pulse intelligence and unlimited Post Karo publishing access on every plan.",
  creator: "ClipKaro AI",
  publisher: "ClipKaro AI",
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
    "AI video clipper India",
    "Post Karo",
    "unlimited Post Karo publishing",
    "affordable AI video clipper India",
    "publish Shorts to Instagram and YouTube",
  ],
  manifest: "/site.webmanifest",
  category: "video",
  icons: {
    icon: [{ url: tabIcon, type: "image/png" }],
    shortcut: tabIcon,
    apple: brandIcon,
  },
  openGraph: {
    type: "website",
    url: "https://clipkaro.pro",
    siteName: "ClipKaro AI",
    title: "ClipKaro AI — Long Video to Shorts + Unlimited Post Karo",
    description: "AI clipping, Creator Studio editing, ₹1 Creator Pulse and unlimited Post Karo publishing access for finished Instagram Reels and YouTube Shorts.",
    images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "ClipKaro AI video clipping and content repurposing platform" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "ClipKaro AI — Long Video to Shorts + Unlimited Post Karo",
    description: "Turn long video into Shorts, refine the edit, get ₹1 Creator Pulse intelligence and publish with unlimited Post Karo access.",
    images: ["/assets/clipkaro-icon.png"],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#07110d",
  colorScheme: "light",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-IN" data-scroll-behavior="smooth">
      <head>
        {/* Hostinger currently replaces upstream CSP headers with only upgrade-insecure-requests.
            Keep an in-document CSP as a browser-enforced fallback. X-Frame-Options still handles framing. */}
        <meta httpEquiv="Content-Security-Policy" content={browserCsp} />
      </head>
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
