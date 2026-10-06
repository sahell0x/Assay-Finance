"use client";

import { Clock, FileText, Quote } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import * as React from "react";

import { LiveShape, VerdictChip, verdictWord } from "@/components/app/kit";
import { EASE } from "@/components/landing/motion";
import { Pipeline } from "@/components/pipeline";
import { grade, THRESHOLDS } from "@/components/scorecard-rail";
import { cn } from "@/lib/cn";
import { formatScore } from "@/lib/format";
import type { NodeEvent, PipelineStep, Rating } from "@/lib/types";

/** Which pipeline step produces which area of the report card. Sentiment is scored at
 *  the end from the news, so it fills in with the verdict. */
const AREAS: { key: string; label: string; node: string }[] = [
  { key: "profitability", label: "Profitability", node: "profitability" },
  { key: "financial_health", label: "Financial health", node: "liquidity" },
  { key: "growth", label: "Growth", node: "growth" },
  { key: "valuation", label: "Valuation", node: "peers" },
];

const VERDICT_TEXT: Record<Rating, string> = {
  BUY: "text-buy",
  HOLD: "text-hold",
  SELL: "text-sell",
};

function useElapsed(startIso: string | null | undefined, running: boolean) {
  const [start] = React.useState(() => {
    const t = startIso ? Date.parse(startIso) : NaN;
    // A start in the future or far past (clock skew, a replay) falls back to now.
    return Number.isFinite(t) && Date.now() - t < 30 * 60_000 && Date.now() >= t ? t : Date.now();
  });
  const [now, setNow] = React.useState(start);
  React.useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [running]);
  const s = Math.max(0, Math.floor((now - start) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** The screen while an analysis runs (or a saved one replays).
 *
 *  Left: the steps. Right: the report taking shape: each area's score lands as its step
 *  finishes, the report shape grows with it, and the verdict is stamped once the score
 *  is in. Nothing on the right is a placeholder dressed as data; empty rows say they are
 *  waiting. */
export function RunView({
  ticker,
  name,
  intro,
  actions,
  pipeline,
  nodes,
  currentNode,
  status,
  replaying,
  startedAt,
}: {
  ticker: string;
  name?: string | null;
  intro: string;
  actions?: React.ReactNode;
  pipeline: PipelineStep[];
  nodes: Record<string, NodeEvent>;
  currentNode: string | null;
  status: string;
  replaying?: boolean;
  startedAt?: string | null;
}) {
  const reduced = useReducedMotion();
  const total = pipeline.length || 10;
  const done = pipeline.filter((s) => nodes[s.node]?.status === "ok").length;
  const finished = status === "complete" || status === "failed";
  const pct = Math.round((done / total) * 100);
  const elapsed = useElapsed(replaying ? null : startedAt, !finished);
  const currentLabel = pipeline.find((s) => s.node === currentNode)?.label;

  const detail = (node: string) => (nodes[node]?.status === "ok" ? ((nodes[node].detail ?? {}) as Record<string, unknown>) : null);
  const scores: Record<string, number | null> = {};
  for (const a of AREAS) {
    const d = detail(a.node);
    scores[a.key] = d && typeof d.score === "number" ? d.score : null;
  }
  const verdict = detail("scorecard");
  const rating = verdict && typeof verdict.rating === "string" ? (verdict.rating as Rating) : null;
  const overall = verdict && typeof verdict.total === "number" ? verdict.total : null;
  const news = detail("news_rag");
  const sources = news && typeof news.evidence === "number" ? news.evidence : null;
  const ingest = detail("ingest");
  const years = ingest && typeof ingest.periods === "number" ? ingest.periods : null;
  const measures = ["profitability", "liquidity", "growth", "peers"].reduce((n, k) => {
    const d = detail(k);
    return n + (d && typeof d.metrics === "number" ? d.metrics : 0);
  }, 0);

  return (
    <div className="mx-auto max-w-[78rem] px-4 pb-20 pt-10 sm:px-6">
      <motion.div
        initial={reduced ? false : { opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: EASE }}
        className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4"
      >
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-[13px] font-medium text-ink-muted">
            <span className="relative flex size-2">
              {!finished && !reduced && (
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-buy-fill opacity-60" />
              )}
              <span className={cn("relative inline-flex size-2 rounded-full", finished ? "bg-ink-muted" : "bg-buy-fill")} />
            </span>
            {finished ? "Finished" : replaying ? "Replaying a saved analysis" : "Live analysis"}
          </p>
          <h1 className="mt-2 text-[34px] font-semibold leading-[1.05] tracking-[-0.04em] text-ink sm:text-[42px]">
            {name ? name : ticker}
            {name && <span className="ml-3 align-middle text-[18px] font-medium tracking-normal text-ink-muted">{ticker}</span>}
          </h1>
          <p className="mt-3 max-w-[62ch] text-[16px] leading-relaxed text-ink-muted">{intro}</p>
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </motion.div>

      {/* Progress: how far, how long, and what is happening right now. */}
      <motion.div
        initial={reduced ? false : { opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: EASE, delay: 0.08 }}
        className="mt-8 rounded-[14px] border border-rule bg-surface p-5 sm:p-6"
      >
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <div className="flex items-baseline gap-3">
            <span className="nums text-[44px] font-semibold leading-none tracking-[-0.045em] text-ink">{pct}%</span>
            <AnimatePresence mode="wait" initial={false}>
              <motion.span
                key={currentLabel ?? status}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.2 }}
                className="text-[15px] text-ink-muted"
              >
                {finished
                  ? status === "failed"
                    ? "Stopped"
                    : "All steps done"
                  : currentLabel
                    ? `${currentLabel}…`
                    : status === "queued"
                      ? "Waiting to start…"
                      : "Starting…"}
              </motion.span>
            </AnimatePresence>
          </div>
          <div className="flex items-center gap-5 text-[13px] text-ink-muted">
            <span className="nums">{done} of {total} steps</span>
            <span className="flex items-center gap-1.5">
              <Clock className="size-3.5" aria-hidden />
              <span className="nums text-ink">{elapsed}</span>
              {!finished && !replaying && <span>of about 2:00</span>}
            </span>
          </div>
        </div>
        <div
          className="relative mt-4 h-2 overflow-hidden rounded-full bg-surface-sunk"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={done}
          aria-label="Analysis progress"
        >
          <motion.span
            className="absolute inset-y-0 left-0 rounded-full bg-ink"
            initial={false}
            animate={{ width: `${Math.max(2, pct)}%` }}
            transition={{ duration: reduced ? 0 : 0.7, ease: EASE }}
          />
          {!finished && !reduced && (
            <motion.span
              aria-hidden
              className="absolute inset-y-0 w-24 bg-gradient-to-r from-transparent via-white/40 to-transparent dark:via-black/40"
              animate={{ left: ["-10%", "110%"] }}
              transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
            />
          )}
        </div>
      </motion.div>

      <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] lg:gap-14">
        <Pipeline
          pipeline={pipeline}
          nodes={nodes}
          currentNode={currentNode}
          status={status}
          replaying={replaying}
        />

        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="card-soft overflow-hidden">
            <div className="flex items-center justify-between gap-4 border-b border-rule px-5 py-4">
              <h2 className="text-[16px] font-semibold text-ink">The report, taking shape</h2>
              {rating ? <VerdictChip rating={rating} /> : <span className="text-[13px] text-ink-muted">In progress</span>}
            </div>

            <div className="grid items-center gap-6 border-b border-rule px-5 py-6 sm:grid-cols-[auto_minmax(0,1fr)]">
              <LiveShape scores={scores} rating={rating} size={112} className="mx-auto sm:mx-0" />
              <div className="min-w-0">
                <div className="relative h-[52px]">
                  <AnimatePresence mode="wait" initial={false}>
                    {rating ? (
                      <motion.p
                        key="verdict"
                        initial={reduced ? false : { opacity: 0, scale: 1.3, filter: "blur(8px)" }}
                        animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
                        transition={{ duration: 0.5, ease: EASE }}
                        className={cn("origin-left text-[52px] font-semibold leading-none tracking-[-0.045em]", VERDICT_TEXT[rating])}
                      >
                        {verdictWord(rating)}
                      </motion.p>
                    ) : (
                      <motion.p
                        key="wait"
                        exit={{ opacity: 0 }}
                        className="flex h-full items-end pb-1 text-[16px] font-medium text-ink-muted"
                      >
                        The verdict comes once every area is scored
                      </motion.p>
                    )}
                  </AnimatePresence>
                </div>
                <p className="nums mt-2 text-[13px] text-ink-muted">
                  <span className="text-[20px] font-semibold text-ink">{overall !== null ? formatScore(overall) : "—"}</span> / 10 overall
                </p>
              </div>
            </div>

            <ul className="px-5 py-2">
              {AREAS.map((a) => {
                const v = scores[a.key];
                const g = v !== null ? grade(v, THRESHOLDS) : null;
                const working = currentNode === a.node && nodes[a.node]?.status === "start";
                return (
                  <li
                    key={a.key}
                    className="grid grid-cols-[7.5rem_minmax(0,1fr)_2.25rem] items-center gap-3 border-b border-rule py-3 text-[14px] text-ink last:border-0 sm:grid-cols-[8.5rem_minmax(0,1fr)_4rem_2.25rem]"
                  >
                    {a.label}
                    <span className="relative h-1.5 overflow-hidden rounded-full bg-surface-sunk">
                      {g ? (
                        <motion.span
                          className={cn("absolute inset-y-0 left-0 rounded-full", g.bar)}
                          initial={reduced ? false : { width: 0 }}
                          animate={{ width: `${Math.max(3, (v as number) * 10)}%` }}
                          transition={{ duration: 0.9, ease: EASE }}
                        />
                      ) : working && !reduced ? (
                        <motion.span
                          className="absolute inset-y-0 w-1/3 rounded-full bg-ink/25"
                          animate={{ left: ["-33%", "100%"] }}
                          transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
                        />
                      ) : null}
                    </span>
                    <span className={cn("hidden text-[12px] sm:inline", g ? g.text : "text-ink-muted")}>
                      {g ? g.word : working ? "Measuring" : "Waiting"}
                    </span>
                    <span className="nums text-right font-semibold">{v !== null ? formatScore(v) : "—"}</span>
                  </li>
                );
              })}
            </ul>

            <div className="grid grid-cols-2 border-t border-rule">
              <Fact Icon={FileText} label="Measures calculated" value={measures || null} extra={years ? `from ${years} years of reports` : "from the company's reports"} />
              <Fact Icon={Quote} label="Sources found" value={sources} extra="in filings and recent news" border />
            </div>
          </div>

          <p className="mt-4 text-[13px] leading-relaxed text-ink-muted">
            You can close this page. The analysis keeps running and will be in your History
            when it&rsquo;s done.
          </p>
        </aside>
      </div>
    </div>
  );
}

function Fact({
  Icon,
  label,
  value,
  extra,
  border,
}: {
  Icon: typeof FileText;
  label: string;
  value: number | null;
  extra: string;
  border?: boolean;
}) {
  return (
    <div className={cn("px-5 py-4", border && "border-l border-rule")}>
      <p className="flex items-center gap-1.5 text-[12px] text-ink-muted">
        <Icon className="size-3.5" aria-hidden />
        {label}
      </p>
      <AnimatePresence mode="wait" initial={false}>
        <motion.p
          key={value ?? "none"}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="nums mt-1 text-[24px] font-semibold tracking-[-0.03em] text-ink"
        >
          {value ?? "—"}
        </motion.p>
      </AnimatePresence>
      <p className="text-[12px] text-ink-muted">{extra}</p>
    </div>
  );
}
