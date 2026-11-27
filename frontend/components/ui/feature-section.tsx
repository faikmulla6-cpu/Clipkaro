import {
  Clapperboard,
  Download,
  Languages,
  Scissors,
  Sparkles,
  Subtitles,
} from "lucide-react";
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
  return (
    <section
      className="relative w-full overflow-hidden bg-[#f1f5ef] px-5 py-16 text-[#142219] sm:px-8 lg:py-20"
      aria-labelledby="connected-workflow-title"
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-70"
        aria-hidden="true"
        style={{
          background:
            "radial-gradient(ellipse at 18% 28%, rgba(171,209,174,.27), transparent 48%)",
        }}
      />

      <div className="relative mx-auto grid max-w-[1280px] items-center gap-8 md:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] lg:gap-16">
        <div data-public-reveal="left">
          <h2 id="connected-workflow-title" className="font-[Manrope] text-[clamp(29px,3.4vw,46px)] font-extrabold leading-[1.1] tracking-[-0.04em]">
            Review, refine and export in one workspace.
          </h2>
          <p className="mt-4 max-w-[45ch] text-sm leading-7 text-[#4e6358] sm:text-base">
            Check uncertain words before they become captions, then shape the frame and prepare publishing copy for the clips you select.
          </p>
        </div>
        <Card className="rounded-3xl border-[#315e4626] bg-white/65 shadow-[0_18px_48px_rgba(24,58,40,0.08)] backdrop-blur-xl" data-public-reveal="right">
          <CardContent className="p-4 sm:p-6">
            <ul className="grid gap-2 min-[540px]:grid-cols-2">
              {tasks.map(({ title, subtitle, icon: Icon }) => (
                <li key={title} className="flex min-w-0 items-center gap-3 rounded-xl border border-[#315e461a] bg-white/60 p-3">
                  <Icon size={18} className="shrink-0 text-[#1b6746]" aria-hidden="true" />
                  <div>
                    <p className="text-sm font-bold">{title}</p>
                    <p className="mt-1 text-xs leading-5 text-[#4e6358]">{subtitle}</p>
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
