"use client";

import type { AnchorHTMLAttributes, MouseEvent } from "react";

type SmoothAnchorLinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & {
  href: string;
};

function easeOutCubic(value: number) {
  return 1 - Math.pow(1 - value, 3);
}

function scrollToTarget(target: HTMLElement) {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const start = window.scrollY;
  const destination = target.getBoundingClientRect().top + start - 18;
  const distance = destination - start;

  if (Math.abs(distance) < 4) {
    window.scrollTo(0, destination);
    return;
  }

  const duration = reduceMotion ? 360 : Math.min(1100, Math.max(620, Math.abs(distance) * 0.5));
  const startedAt = window.performance.now();

  function frame() {
    const now = window.performance.now();
    const progress = Math.min(1, (now - startedAt) / duration);
    window.scrollTo(0, start + distance * easeOutCubic(progress));
    if (progress < 1) window.setTimeout(frame, 16);
  }

  frame();
}

export function SmoothAnchorLink({ href, onClick, ...props }: SmoothAnchorLinkProps) {
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    onClick?.(event);
    if (event.defaultPrevented) return;
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

    const url = new URL(href, window.location.href);
    if (!url.hash || url.origin !== window.location.origin || url.pathname !== window.location.pathname) return;

    const target = document.getElementById(decodeURIComponent(url.hash.slice(1)));
    if (!target) return;

    event.preventDefault();
    window.history.pushState(null, "", `${url.pathname}${url.search}${url.hash}`);
    scrollToTarget(target);
  }

  return <a href={href} onClick={handleClick} {...props} />;
}
