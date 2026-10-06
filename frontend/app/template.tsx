"use client";

import { motion, useReducedMotion } from "motion/react";
import { usePathname } from "next/navigation";
import type * as React from "react";

/** A short fade as you move between pages of the app, so a click reads as going
 *  somewhere. The landing page is left out: it orchestrates its own opening, and a
 *  fade over it would only delay the first thing a visitor sees. */
export default function Template({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const reduced = useReducedMotion();
  if (pathname === "/" || reduced) return <>{children}</>;
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }}>
      {children}
    </motion.div>
  );
}
