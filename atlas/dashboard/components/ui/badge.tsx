import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium tracking-wide",
  {
    variants: {
      tone: {
        neutral: "border-line bg-panel-2 text-muted",
        gain: "border-gain/30 bg-gain/10 text-gain",
        loss: "border-loss/30 bg-loss/10 text-loss",
        warn: "border-warn/30 bg-warn/10 text-warn",
        accent: "border-accent/30 bg-accent/10 text-accent",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({
  className,
  tone,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
