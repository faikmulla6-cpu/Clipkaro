"use client";

import type { ComponentProps, MouseEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

type TransitionLinkProps = Omit<ComponentProps<typeof Link>, "href"> & {
  href: string;
};

const EXTERNAL_TARGET = /^(?:https?:|mailto:|tel:)/i;

export function TransitionLink({ href, onClick, ...props }: TransitionLinkProps) {
  const router = useRouter();

  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    onClick?.(event);
    if (event.defaultPrevented) return;
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (href.startsWith("#") || EXTERNAL_TARGET.test(href)) return;

    event.preventDefault();

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) {
      router.push(href);
      return;
    }

    const root = document.documentElement;
    root.classList.remove("ck-route-transition-arriving");
    root.classList.add("ck-route-transition-leaving");

    window.setTimeout(() => router.push(href), 260);
    window.setTimeout(() => root.classList.add("ck-route-transition-arriving"), 500);
    window.setTimeout(() => {
      root.classList.remove("ck-route-transition-leaving", "ck-route-transition-arriving");
    }, 920);
  }

  return <Link href={href} onClick={handleClick} {...props} />;
}
