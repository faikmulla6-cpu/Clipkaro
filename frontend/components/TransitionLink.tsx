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
    background: "radial-gradient(circle at 50% 48%, rgba(63,125,67,.36), transparent 31%), linear-gradient(155deg, #0b2118 0%, #06110c 68%, #030806 100%)",
    transform: "translate3d(0,100%,0)",
    willChange: "transform, opacity",
  });

  const mark = document.createElement("div");
  Object.assign(mark.style, {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "10px 14px",
    border: "1px solid rgba(223,255,87,.14)",
    borderRadius: "20px",
    background: "rgba(4,13,9,.35)",
    boxShadow: "0 22px 70px rgba(0,0,0,.28)",
    opacity: "0",
    transform: "translate3d(0,10px,0) scale(.98)",
  });

  const image = document.createElement("img");
  image.src = "/assets/clipkaro-icon.png";
  image.alt = "";
  Object.assign(image.style, {
    width: "46px",
    height: "46px",
    borderRadius: "13px",
    objectFit: "cover",
    display: "block",
  });

  const wordmark = document.createElement("span");
  wordmark.textContent = "ClipKaro AI";
  Object.assign(wordmark.style, {
    color: "#f3f7f3",
    fontFamily: "Manrope, system-ui, sans-serif",
    fontSize: "18px",
    fontWeight: "800",
    letterSpacing: "-.45px",
  });

  mark.append(image, wordmark);
  overlay.append(mark);
  document.body.appendChild(overlay);

  overlay.animate(
    [
      { transform: "translate3d(0,100%,0)" },
      { transform: "translate3d(0,0,0)" },
    ],
    { duration: 360, easing: "cubic-bezier(.22,.61,.36,1)", fill: "forwards" },
  );

  mark.animate(
    [
      { opacity: 0, transform: "translate3d(0,10px,0) scale(.98)" },
      { opacity: 1, transform: "translate3d(0,0,0) scale(1)" },
    ],
    { duration: 280, delay: 135, easing: "cubic-bezier(.22,.61,.36,1)", fill: "forwards" },
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

    window.setTimeout(() => router.push(href), 300);
    window.setTimeout(() => {
      overlay.animate(
        [
          { opacity: 1, transform: "translate3d(0,0,0)" },
          { opacity: 0, transform: "translate3d(0,-7%,0)" },
        ],
        { duration: 380, easing: "cubic-bezier(.22,.61,.36,1)", fill: "forwards" },
      );
    }, 610);
    window.setTimeout(() => overlay.remove(), 1040);
  }

  return <Link href={href} onClick={handleClick} {...props} />;
}
