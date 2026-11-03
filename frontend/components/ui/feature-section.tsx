"use client";

import * as React from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  Clapperboard,
  Download,
  Languages,
  Scissors,
  Sparkles,
  Subtitles,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

const tasks = [
  {
    title: "AI Clip Finder",
    subtitle: "Find strong, self-contained moments",
    icon: Scissors,
  },
  {
    title: "Smart Transcript Review",
    subtitle: "Review uncertain wording before captions",
    icon: Subtitles,
  },
  {
    title: "India Quality Mode",
    subtitle: "Hindi, Hinglish & Indian-English workflows",
    icon: Languages,
  },
  {
    title: "Creator Studio",
    subtitle: "Refine framing for vertical short-form video",
    icon: Clapperboard,
  },
  {
    title: "Content Pack",
    subtitle: "Prepare titles, descriptions, captions & hashtags",
    icon: Sparkles,
  },
  {
    title: "Export controls",
    subtitle: "You decide what actually gets published",
    icon: Download,
  },
] as const;

export default function FeatureSection() {
  const reduceMotion = useReducedMotion();
  const loopItems = React.useMemo(() => [...tasks, ...tasks], []);

  return (
    <section
      className="relative w-full overflow-hidden bg-[#f7faf5] px-5 py-20 text-[#142219] sm:px-8 lg:py-24"
      aria-labelledby="connected-workflow-title"
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-70"
        aria-hidden="true"
        style={{
          background:
            "radial-gradient(circle at 16% 18%, rgba(223,255,87,.24), transparent 28%), radial-gradient(circle at 88% 72%, rgba(22,95,67,.10), transparent 34%)",
        }}
      />

      <div className="relative mx-auto grid max-w-[1180px] grid-cols-1 items-center gap-12 md:grid-cols-[minmax(0,440px)_minmax(0,1fr)] lg:gap-20">
        <div className="relative w-full" data-public-reveal="left">
          <div className="absolute -left-3 -top-3 h-24 w-24 rounded-full bg-[#dfff57]/35 blur-2xl" aria-hidden="true" />
          <Card className="relative overflow-hidden border-[#dce8d8] bg-white/90 backdrop-blur-xl">
            <div className="flex items-center justify-between border-b border-[#e7eee4] px-5 py-4">
              <div>
                <p className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-[#4f8658]">Connected workflow</p>
                <p className="mt-1 text-sm font-bold text-[#17271d]">One recording keeps moving forward</p>
              </div>
              <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-[#eff8e8] text-[#1c6742]">
                <Sparkles className="h-4 w-4" />
              </span>
            </div>

            <CardContent className="relative h-[336px] overflow-hidden" style={{ padding: 0 }}>
              <motion.div
                className="absolute left-0 top-0 flex w-full flex-col"
                animate={reduceMotion ? undefined : { y: ["0%", "-50%"] }}
                transition={reduceMotion ? undefined : { repeat: Infinity, repeatType: "loop", duration: 17, ease: "linear" }}
              >
                {loopItems.map((task, index) => {
                  const Icon = task.icon;
                  const duplicate = index >= tasks.length;
                  return (
                    <div
                      key={`${task.title}-${index}`}
                      aria-hidden={duplicate || undefined}
                      className="flex min-h-[72px] items-center gap-3 border-b border-[#e8eee6] px-4 py-3.5"
                    >
                      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-[#dce9d8] bg-[#f2f8ee] text-[#176b49] shadow-[0_7px_18px_rgba(27,91,55,0.07)]">
                        <Icon className="h-[18px] w-[18px]" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px] font-bold text-[#18281e]">{task.title}</p>
                        <p className="mt-1 text-[11px] leading-4 text-[#718078]">{task.subtitle}</p>
                      </div>
                      <span className="h-2 w-2 shrink-0 rounded-full bg-[#b9e84f] shadow-[0_0_0_4px_rgba(223,255,87,.18)]" aria-hidden="true" />
                    </div>
                  );
                })}
              </motion.div>

              <div className="pointer-events-none absolute inset-x-0 top-0 h-14 bg-linear-to-b from-white via-white/80 to-transparent" aria-hidden="true" />
              <div className="pointer-events-none absolute inset-x-0 bottom-0 h-14 bg-linear-to-t from-white via-white/80 to-transparent" aria-hidden="true" />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6" data-public-reveal="right">
          <Badge variant="secondary" className="px-3 py-1.5 text-[11px] uppercase tracking-[0.12em]">
            Creator workflow
          </Badge>

          <div className="space-y-4">
            <h2 id="connected-workflow-title" className="max-w-[720px] font-[Manrope] text-[clamp(34px,4.6vw,58px)] font-extrabold leading-[0.98] tracking-[-0.045em] text-[#142219]">
              One video. One connected workflow.
            </h2>
            <p className="max-w-[680px] text-[15px] leading-7 text-[#68756d] sm:text-base">
              ClipKaro keeps the useful steps together — from finding strong moments and reviewing the transcript to refining vertical framing, preparing publishing copy and exporting the clips you choose.
            </p>
          </div>

          <div className="flex flex-wrap gap-2.5">
            <Badge className="px-4 py-2 text-xs">AI Clip Finder</Badge>
            <Badge variant="secondary" className="px-4 py-2 text-xs">India-first captions</Badge>
            <Badge variant="outline" className="px-4 py-2 text-xs">Creator controlled</Badge>
          </div>

          <p className="max-w-[640px] border-l-2 border-[#b9e84f] pl-4 text-xs leading-5 text-[#7a857e]">
            ClipKaro suggests and prepares. You review the content and keep the final publishing decision.
          </p>
        </div>
      </div>
    </section>
  );
}
