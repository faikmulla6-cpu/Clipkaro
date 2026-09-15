import * as React from "react";
import { cn } from "@/lib/utils";

type BadgeProps = React.HTMLAttributes<HTMLSpanElement> & {
  variant?: "default" | "secondary" | "outline";
};

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  const variants = {
    default: "border-transparent bg-[#dfff57] text-[#163e2d]",
    secondary: "border-[#dce8d9] bg-[#f2f8ee] text-[#2f6b46]",
    outline: "border-[#dce8d9] bg-transparent text-[#4d5c52]",
  } as const;

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border font-semibold transition-colors",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
