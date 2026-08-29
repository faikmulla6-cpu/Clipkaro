import Link from "next/link";
import { TransitionLink } from "./TransitionLink";

type LogoProps = {
  light?: boolean;
  transition?: boolean;
  href?: string;
};

export function Logo({ light = false, transition = false, href = "/" }: LogoProps) {
  const className = `logo ${light ? "logo-light" : ""}`;
  const content = (
    <>
      <span className="logo-mark" aria-hidden="true">
        <img className="logo-icon" src="/assets/clipkaro-icon.png" alt="ClipKaro AI logo" />
      </span>
      <span className="logo-wordmark">ClipKaro<span className="logo-ai">AI</span></span>
    </>
  );

  if (transition) {
    return <TransitionLink href={href} className={className} aria-label="ClipKaro AI home">{content}</TransitionLink>;
  }

  return <Link href={href} className={className} aria-label="ClipKaro AI home">{content}</Link>;
}
