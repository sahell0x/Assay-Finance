import Link from "next/link";

import { cn } from "@/lib/cn";

/** The Assay mark: an "A" cut out of a solid tile, its crossbar a rising green line.
 *
 *  The tile takes the ink colour and the cut takes the page colour, so the mark inverts
 *  with the theme — black tile on white, white tile on black — and the green line, the
 *  one colour in it, reads as "is this going up" in both. A surface that is neither
 *  (the dark closing panel) can set `--mark-tile` and `--mark-cut` to suit it.
 */
export function AssayMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-6 shrink-0", className)} aria-hidden>
      <rect width="32" height="32" rx="8" style={{ fill: "var(--mark-tile, var(--ink))" }} />
      <path
        d="M9 24.5 L16 7.5 L23 24.5"
        fill="none"
        strokeWidth="3"
        strokeLinejoin="round"
        strokeLinecap="round"
        style={{ stroke: "var(--mark-cut, var(--paper))" }}
      />
      <path
        d="M11.6 19.2 L14.6 16.6 L17 18.4 L20.8 14.8"
        fill="none"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ stroke: "#22c55e" }}
      />
    </svg>
  );
}

export function Brand({
  href = "/",
  className,
  markClassName,
}: {
  href?: string;
  className?: string;
  markClassName?: string;
}) {
  return (
    <Link
      href={href}
      aria-label="Assay home"
      className={cn(
        "flex shrink-0 items-center gap-2 text-[17px] font-semibold tracking-[-0.03em] text-ink",
        className,
      )}
    >
      <AssayMark className={markClassName} />
      Assay
    </Link>
  );
}
