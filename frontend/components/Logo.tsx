import { Sparkles } from "lucide-react";
import Link from "next/link";

export function Logo({ light = false }: { light?: boolean }) {
  return (
    <Link href="/" className={`logo ${light ? "logo-light" : ""}`}>
      <span className="logo-mark"><Sparkles size={18} strokeWidth={2.5} /></span>
      <span>ClipKaro<span className="logo-ai">AI</span></span>
    </Link>
  );
}
