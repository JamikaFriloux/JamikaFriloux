import * as React from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-lg border border-line bg-panel-2 px-3 text-sm text-fg placeholder:text-muted/60 focus:border-accent/60 focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}
