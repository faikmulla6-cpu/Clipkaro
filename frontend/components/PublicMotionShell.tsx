"use client";

import { useEffect, useRef, type ReactNode } from "react";
import styles from "./PublicMotionShell.module.css";

export function PublicMotionShell({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = ref.current;
    if (!root) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const items = Array.from(root.querySelectorAll<HTMLElement>("[data-public-reveal]"));

    if (reduceMotion || !("IntersectionObserver" in window)) {
      items.forEach((item) => item.classList.add("ck-public-visible"));
      root.classList.add(styles.ready);
      return;
    }

    // Anything already in the first viewport should never disappear after the
    // server-rendered paint. Mark it visible before enabling reveal styles.
    const firstViewportCutoff = window.innerHeight * 0.94;
    items.forEach((item) => {
      if (item.getBoundingClientRect().top < firstViewportCutoff) {
        item.classList.add("ck-public-visible");
      }
    });

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          (entry.target as HTMLElement).classList.add("ck-public-visible");
          observer.unobserve(entry.target);
        }
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" },
    );

    items.forEach((item) => {
      if (!item.classList.contains("ck-public-visible")) observer.observe(item);
    });
    root.classList.add(styles.ready);

    return () => observer.disconnect();
  }, []);

  return <div ref={ref} className={styles.shell}>{children}</div>;
}
