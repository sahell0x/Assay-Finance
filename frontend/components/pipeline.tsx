"use client";

import { Check, X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { EASE } from "@/components/landing/motion";
import { cn } from "@/lib/cn";
import { formatScore } from "@/lib/format";
import type { NodeEvent, PipelineStep } from "@/lib/types";

/** The analysis running.
 *
 *  Steps light up in order as events arrive. A rail joins them because they are a
 *  genuine sequence, and it fills down to the step being worked on, so progress reads at
 *  a glance. Finished steps check off with a small spring and keep a one-line result,
 *  so the finished list is a record of what happened rather than a spinner that was.
 */
export function Pipeline({
  pipeline,
  nodes,
  currentNode,
  status,
  replaying,
  compact = false,
}: {
  pipeline: PipelineStep[];
  nodes: Record<string, NodeEvent>;
  currentNode: string | null;
  status: string;
  replaying?: boolean;
  compact?: boolean;
}) {
  const reduced = useReducedMotion();
  const done = pipeline.filter((s) => nodes[s.node]?.status === "ok").length;
  // How far down the list the rail is filled: through the last step that has started.
  const reached = pipeline.reduce((n, s, i) => (nodes[s.node] ? i + 1 : n), 0);
  const fill = pipeline.length > 1 ? Math.max(0, reached - 1) / (pipeline.length - 1) : 0;

  return (
    <section aria-label="Analysis steps">
      {!compact && (
        <header className="mb-5 flex items-baseline justify-between gap-4">
          <h2 className="text-[19px] font-semibold tracking-[-0.02em] text-ink">
            {status === "complete"
              ? "Analysis complete"
              : status === "failed"
                ? "Analysis stopped"
                : replaying
                  ? "Replaying the analysis"
                  : "Running the analysis"}
          </h2>
          <span className="nums text-[13px] text-ink-muted">
            {done} of {pipeline.length} steps
          </span>
        </header>
      )}

      <ol className="relative">
        {/* The rail behind the markers, and the part of it already travelled. */}
        <span aria-hidden className="absolute bottom-5 left-[11px] top-5 w-px bg-rule" />
        <motion.span
          aria-hidden
          className="absolute left-[11px] top-5 w-px origin-top bg-ink"
          style={{ height: "calc(100% - 2.5rem)" }}
          initial={false}
          animate={{ scaleY: fill }}
          transition={{ duration: reduced ? 0 : 0.6, ease: EASE }}
        />

        {pipeline.map((step) => {
          const event = nodes[step.node];
          const state = event?.status ?? "pending";
          const isActive = currentNode === step.node && state === "start";
          const result = state === "ok" ? summarise(step.node, event) : "";

          return (
            <li key={step.node} className="relative flex gap-4 py-2.5">
              <span className="relative z-10 mt-0.5 grid size-6 shrink-0 place-items-center">
                <AnimatePresence mode="popLayout" initial={false}>
                  {state === "ok" ? (
                    <motion.span
                      key="ok"
                      initial={reduced ? false : { scale: 0.4, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={{ type: "spring", stiffness: 520, damping: 24 }}
                      className="grid size-6 place-items-center rounded-full bg-ink text-paper"
                    >
                      <Check className="size-3.5" strokeWidth={3} aria-hidden />
                    </motion.span>
                  ) : state === "error" ? (
                    <motion.span
                      key="err"
                      initial={reduced ? false : { scale: 0.4 }}
                      animate={{ scale: 1 }}
                      className="grid size-6 place-items-center rounded-full bg-sell text-paper"
                    >
                      <X className="size-3.5" strokeWidth={3} aria-hidden />
                    </motion.span>
                  ) : isActive ? (
                    <motion.span key="active" className="relative grid size-6 place-items-center">
                      {!reduced && (
                        <motion.span
                          aria-hidden
                          className="absolute inset-0 rounded-full bg-ink/15"
                          animate={{ scale: [1, 1.7], opacity: [0.8, 0] }}
                          transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
                        />
                      )}
                      <span className="grid size-6 place-items-center rounded-full border-2 border-ink bg-paper">
                        <motion.span
                          className="size-2 rounded-full bg-ink"
                          animate={reduced ? undefined : { scale: [1, 0.6, 1] }}
                          transition={{ duration: 1, repeat: Infinity }}
                        />
                      </span>
                    </motion.span>
                  ) : (
                    <motion.span
                      key="pending"
                      className={cn(
                        "size-6 rounded-full border-2 bg-paper",
                        state === "skipped" ? "border-rule bg-surface-sunk" : "border-rule",
                      )}
                    />
                  )}
                </AnimatePresence>
              </span>

              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
                  <span
                    className={cn(
                      "text-[15px] font-medium transition-colors",
                      state === "pending" ? "text-ink-muted" : "text-ink",
                    )}
                  >
                    {step.label}
                  </span>
                  {isActive && (
                    <span className="text-[12px] font-medium text-ink-muted">Working on it</span>
                  )}
                  {state === "ok" && event?.duration_ms != null && event.duration_ms >= 1000 && (
                    <span className="nums text-[12px] text-ink-muted">
                      {(event.duration_ms / 1000).toFixed(event.duration_ms < 10_000 ? 1 : 0)}s
                    </span>
                  )}
                  {state === "error" && (
                    <span className="text-[12px] text-sell">Skipped after an error</span>
                  )}
                </div>
                <AnimatePresence mode="wait" initial={false}>
                  <motion.p
                    key={result ? "result" : "detail"}
                    initial={reduced ? false : { opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.25 }}
                    className={cn("mt-0.5 text-[13px]", result ? "text-ink-soft" : "text-ink-muted")}
                  >
                    {result ? sentenceStart(result) : step.detail}
                  </motion.p>
                </AnimatePresence>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function sentenceStart(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** One line about what a node actually found. "score 9.2, 10 measures" is worth more
 *  than "done", and it is already in the event payload. */
export function summarise(node: string, event?: NodeEvent): string {
  const d = (event?.detail ?? {}) as Record<string, unknown>;
  const parts: string[] = [];

  if (typeof d.score === "number") parts.push(`score ${formatScore(d.score)}`);
  if (typeof d.metrics === "number") parts.push(`${d.metrics} measures calculated`);
  if (typeof d.coverage === "number")
    parts.push(`${Math.round(d.coverage * 100)}% of the data found`);
  if (typeof d.periods === "number") parts.push(`${d.periods} years of reports`);
  if (typeof d.evidence === "number") parts.push(`${d.evidence} sources found`);
  if (typeof d.rating === "string") parts.push(`rated ${d.rating.toLowerCase()}`);
  if (typeof d.total === "number") parts.push(`overall ${formatScore(d.total)} out of 10`);
  if (typeof d.verdict === "string")
    parts.push(d.verdict === "pass" ? "all checks passed" : "revised after checks");
  if (typeof d.warnings === "number" && d.warnings > 0)
    parts.push(`${d.warnings} note${d.warnings === 1 ? "" : "s"}`);

  return parts.join(", ");
}
