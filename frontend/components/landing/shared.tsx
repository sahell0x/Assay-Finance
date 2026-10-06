import type * as React from "react";

import { cn } from "@/lib/cn";

/** Landing content width: full-bleed up to 1440px of content, with gutters that open up
 *  on wide screens so the page sits close to the edges without touching them. */
export const CONTAINER =
  "mx-auto w-full max-w-[80rem] px-4 sm:px-6 lg:px-8";

/** A friendly section label: "● The verdict". */
export function Eyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <p className={cn("pill", className)}>
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      {children}
    </p>
  );
}
