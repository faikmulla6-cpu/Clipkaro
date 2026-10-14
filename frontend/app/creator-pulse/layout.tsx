import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Creator Pulse | ClipKaro AI",
  robots: {
    index: false,
    follow: false,
    nocache: true,
    googleBot: {
      index: false,
      follow: false,
      noimageindex: true,
      nosnippet: true,
    },
  },
};

export default function CreatorPulseLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
