"use client";

import type { ComponentProps, MouseEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

type TransitionLinkProps = Omit<ComponentProps<typeof Link>, "href"> & {
  href: string;
};

const EXTERNAL_TARGET = /^(?:https?:|mailto:|tel:)/i;

function buildRouteOverlay() {
  const existing = document.querySelector<HTMLElement>("[data-ck-route-overlay]");
  if (existing) return existing;

  const overlay = document.createElement("div");
  overlay.dataset.ckRouteOverlay = "true";
  overlay.setAttribute("aria-hidden", "true");
  Object.assign(overlay.style, {
    position: "fixed",
    inset: "0",
    zIndex: "2147483647",
    display: "grid",
    placeItems: "center",
    pointerEvents: "none",
    overflow: "hidden",
    background: "radial-gradient(circle at 50% 44%, rgba(118,177,73,.23), transparent 30%), linear-gradient(155deg, #103829 0%, #082419 57%, #06160f 100%)",
    clipPath: "inset(0 0 100% 0)",
    willChange: "clip-path, opacity",
  });

  const glow = document.createElement("div");
  Object.assign(glow.style, {
    position: "absolute",
    width: "360px",
    height: "360px",
    borderRadius: "50%",
    background: "rgba(223,255,87,.08)",
    filter: "blur(44px)",
  });

  const mark = document.createElement("div");
  Object.assign(mark.style, {
    position: "relative",
    display: "flex",
    alignItems: "center",
    gap: "11px",
    padding: "10px 14px",
    border: "1px solid rgba(223,255,87,.16)",
    borderRadius: "18px",
    background: "rgba(4,13,9,.28)",
    boxShadow: "0 22px 70px rgba(0,0,0,.22)",
    opacity: "0",
    transform: "translate3d(0,-10px,0) scale(.985)",
  });

  const image = document.createElement("img");
  image.src = "/assets/clipkaro-icon.png";
  image.alt = "";
  Object.assign(image.style, {
    width: "42px",
    height: "42px",
    borderRadius: "12px",
    objectFit: "cover",
    display: "block",
  });

  const wordmark = document.createElement("span");
  wordmark.textContent = "ClipKaro AI";
  Object.assign(wordmark.style, {
    color: "#f3f7f3",
    fontFamily: "Manrope, system-ui, sans-serif",
    fontSize: "17px",
    fontWeight: "800",
    letterSpacing: "-.45px",
  });

  mark.append(image, wordmark);
  overlay.append(glow, mark);
  document.body.appendChild(overlay);

  overlay.animate(
    [
      { clipPath: "inset(0 0 100% 0)" },
      { clipPath: "inset(0 0 0 0)" },
    ],
    { duration: 285, easing: "cubic-bezier(.22,.61,.36,1)", fill: "forwards" },
  );

  mark.animate(
    [
      { opacity: 0, transform: "translate3d(0,-10px,0) scale(.985)" },
      { opacity: 1, transform: "translate3d(0,0,0) scale(1)" },
    ],
    { duration: 210, delay: 95, easing: "cubic-bezier(.22,.61,.36,1)", fill: "forwards" },
  );

  return overlay;
}

export function TransitionLink({ href, onClick, ...props }: TransitionLinkProps) {
  const router = useRouter();

  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    onClick?.(event);
    if (event.defaultPrevented) return;
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (href.startsWith("#") || EXTERNAL_TARGET.test(href)) return;

    event.preventDefault();
    router.prefetch(href);

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) {
      router.push(href);
      return;
    }

    const overlay = buildRouteOverlay();

    window.setTimeout(() => router.push(href), 245);
    window.setTimeout(() => {
      overlay.animate(
        [
          { clipPath: "inset(0 0 0 0)", opacity: 1 },
          { clipPath: "inset(100% 0 0 0)", opacity: .98 },
        ],
        { duration: 330, easing: "cubic-bezier(.65,0,.35,1)", fill: "forwards" },
      );
    }, 500);
    window.setTimeout(() => overlay.remove(), 870);
  }

  return <Link href={href} onClick={handleClick} {...props} />;
}
