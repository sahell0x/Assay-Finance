"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, FileText, Star } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import * as React from "react";

import { verdictWord, VERDICT_CHIP, VERDICT_TEXT } from "@/components/landing/report-card";
import { RiseText } from "@/components/landing/motion";
import { CONTAINER } from "@/components/landing/shared";
import { grade } from "@/components/scorecard-rail";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  formatCurrency,
  formatDate,
  formatMetric,
  formatPercentile,
  formatScore,
} from "@/lib/format";
import {
  DIMENSIONS,
  DIMENSION_LABELS,
  type AnalysisDetail,
  type MetricValue,
  type ShowcaseCard,
} from "@/lib/types";

const STEP_MS = 4000;

const STEPS = [
  {
    key: "verdict",
    title: "One clear verdict",
    body: "A score out of 10 from fixed rules, and where it sits between sell, hold and buy.",
  },
  {
    key: "working",
    title: "Every number shows its working",
    body: "Open any measure to see the formula and the report lines that fed it.",
  },
  {
    key: "sources",
    title: "Every claim has a source",
    body: "Statements about the business link to the filing or article they came from.",
  },
  {
    key: "track",
    title: "Keep track of your companies",
    body: "Watchlist, side-by-side comparison, and each score over time.",
  },
] as const;

type StepKey = (typeof STEPS)[number]["key"];

const BAR: Record<string, string> = {
  "text-buy": "bg-buy-fill",
  "text-hold": "bg-hold-fill",
  "text-sell": "bg-sell-fill",
};

/** The product, shown rather than dumped. A list of four things a run produces on the
 *  left; on the right a compact panel that plays each one with real data from the chosen
 *  company — the score counting up, a metric opening into its formula, a claim landing on
 *  its source, the watchlist filling in. It keeps advancing while on screen, even under
 *  the pointer, and stays still for anyone who prefers reduced motion. */
export function Stage({
  cards,
  initialAnalysis,
}: {
  cards: ShowcaseCard[];
  initialAnalysis: AnalysisDetail | null;
}) {
  const reduced = useReducedMotion();
  const [selectedId, setSelectedId] = React.useState(
    initialAnalysis?.id ?? cards[0]?.id ?? null,
  );
  // Step and progress move together in one state, so the timer's updater stays pure:
  // React may run an updater twice, and a nested setStep inside one skipped a step.
  const [play, setPlay] = React.useState({ step: 0, progress: 0 });
  const { step, progress } = play;
  const [inView, setInView] = React.useState(false);
  const ref = React.useRef<HTMLElement | null>(null);

  const { data: analysis } = useQuery({
    queryKey: ["analysis", selectedId],
    queryFn: () => api.getAnalysis(selectedId as string),
    enabled: Boolean(selectedId),
    initialData:
      selectedId && selectedId === initialAnalysis?.id ? initialAnalysis : undefined,
    staleTime: 5 * 60_000,
  });

  const selected = cards.find((c) => c.id === selectedId) ?? cards[0];

  React.useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver((e) => setInView(e.some((x) => x.isIntersecting)), {
      threshold: 0.3,
    });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // Advance while visible and motion is welcome.
  const playing = inView && !reduced;
  React.useEffect(() => {
    if (!playing) return;
    const tick = 100;
    const id = setInterval(() => {
      setPlay((st) => {
        const next = st.progress + tick / STEP_MS;
        return next >= 1
          ? { step: (st.step + 1) % STEPS.length, progress: 0 }
          : { step: st.step, progress: next };
      });
    }, tick);
    return () => clearInterval(id);
  }, [playing]);

  const choose = (i: number) => {
    setPlay({ step: i, progress: 0 });
  };

  const current = STEPS[step].key;

  return (
    <section
      ref={ref}
      id="showcase"
      aria-labelledby="showcase-heading"
      className="scroll-mt-20 border-t border-rule py-24 sm:py-32"
    >
      <div className={CONTAINER}>
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-[40rem]">
            <h2
              id="showcase-heading"
              className="text-[36px] font-semibold leading-[1.05] tracking-[-0.04em] text-ink sm:text-[52px]"
            >
              <RiseText inView text="A full research report, in two minutes." />
            </h2>
            <p className="mt-3 text-[17px] leading-relaxed text-ink-muted">
              Real analyses, not mock-ups. Pick a company and watch what a run produces.
            </p>
          </div>
          {selected && (
            <Button asChild variant="outline" size="lg">
              <Link href={`/analysis/${selected.id}`}>
                Open {selected.ticker}&rsquo;s full report <ArrowUpRight aria-hidden />
              </Link>
            </Button>
          )}
        </div>

        {/* Company picker. */}
        <div role="tablist" aria-label="Choose a company" className="mt-8 flex flex-wrap gap-2">
          {cards.map((card) => {
            const active = card.id === selectedId;
            return (
              <button
                key={card.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => {
                  setSelectedId(card.id);
                  setPlay((st) => ({ step: st.step, progress: 0 }));
                }}
                className={cn(
                  "flex items-center gap-2.5 rounded-lg border px-3 py-2 text-left transition-colors",
                  active ? "border-ink bg-paper" : "border-rule bg-paper hover:border-brand-edge",
                )}
              >
                <span className="text-[14px] font-semibold text-ink">{card.ticker}</span>
                <span className="hidden text-[13px] text-ink-muted sm:inline">
                  {card.name ?? ""}
                </span>
                {card.rating && (
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[11px] font-semibold",
                      VERDICT_CHIP[card.rating],
                    )}
                  >
                    {verdictWord(card.rating)}{" "}
                    <span className="nums">{formatScore(card.total_score)}</span>
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div
          className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.3fr)] lg:gap-10"
        >
          {/* Step list with a progress line on the active one. */}
          <ol className="flex flex-col gap-1.5">
            {STEPS.map((s, i) => {
              const active = i === step;
              return (
                <li key={s.key}>
                  <button
                    type="button"
                    onClick={() => choose(i)}
                    aria-current={active ? "step" : undefined}
                    className={cn(
                      "relative w-full overflow-hidden rounded-xl border p-4 text-left transition-colors",
                      active ? "border-rule bg-paper" : "border-transparent hover:bg-paper/60",
                    )}
                  >
                    <span className="flex items-center gap-3">
                      <span
                        className={cn(
                          "nums grid size-6 shrink-0 place-items-center rounded-full border text-[12px] font-medium",
                          active ? "border-ink bg-ink text-paper" : "border-rule text-ink-muted",
                        )}
                      >
                        {i + 1}
                      </span>
                      <span
                        className={cn(
                          "text-[16px] font-medium",
                          active ? "text-ink" : "text-ink-muted",
                        )}
                      >
                        {s.title}
                      </span>
                    </span>
                    <AnimatePresence initial={false}>
                      {active && (
                        <motion.span
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.25 }}
                          className="block overflow-hidden pl-9 text-[14px] leading-relaxed text-ink-muted"
                        >
                          <span className="block pt-1.5">{s.body}</span>
                        </motion.span>
                      )}
                    </AnimatePresence>
                    {active && !reduced && (
                      <span
                        aria-hidden
                        className="absolute bottom-0 left-0 h-[2px] bg-ink/80"
                        style={{ width: `${progress * 100}%` }}
                      />
                    )}
                  </button>
                </li>
              );
            })}
          </ol>

          {/* The panel. */}
          <div className="card-soft relative min-h-[460px] overflow-hidden bg-paper">
            <div className="flex items-center gap-2 border-b border-rule px-5 py-3 text-[13px]">
              <span className="font-semibold text-ink">{selected?.ticker}</span>
              <span className="text-ink-muted">· {STEPS[step].title}</span>
              <span className="ml-auto flex gap-1" aria-hidden>
                {STEPS.map((s, i) => (
                  <span
                    key={s.key}
                    className={cn("h-1.5 w-1.5 rounded-full", i === step ? "bg-ink" : "bg-rule")}
                  />
                ))}
              </span>
            </div>

            <div className="p-5 sm:p-6">
              {analysis?.scorecard ? (
                <AnimatePresence mode="wait">
                  <motion.div
                    key={`${current}-${analysis.id}`}
                    initial={reduced ? false : { opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={reduced ? undefined : { opacity: 0, y: -6 }}
                    transition={{ duration: 0.25 }}
                  >
                    <View step={current} analysis={analysis} cards={cards} reduced={!!reduced} />
                  </motion.div>
                </AnimatePresence>
              ) : (
                <div className="space-y-4" aria-hidden>
                  <Skeleton className="h-12 w-40" />
                  <Skeleton className="h-3 w-full" />
                  <Skeleton className="h-40 w-full" />
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function View({
  step,
  analysis,
  cards,
  reduced,
}: {
  step: StepKey;
  analysis: AnalysisDetail;
  cards: ShowcaseCard[];
  reduced: boolean;
}) {
  if (step === "verdict") return <VerdictView analysis={analysis} reduced={reduced} />;
  if (step === "working") return <WorkingView analysis={analysis} reduced={reduced} />;
  if (step === "sources") return <SourcesView analysis={analysis} reduced={reduced} />;
  return <TrackView cards={cards} reduced={reduced} />;
}

/* ------------------------------------------------------------------ verdict */

function CountUp({ to, reduced }: { to: number; reduced: boolean }) {
  const [v, setV] = React.useState(reduced ? to : 0);
  React.useEffect(() => {
    if (reduced) return;
    let raf = 0;
    const start = performance.now();
    const run = (now: number) => {
      const t = Math.min(1, (now - start) / 900);
      setV(to * (1 - Math.pow(1 - t, 3)));
      if (t < 1) raf = requestAnimationFrame(run);
    };
    raf = requestAnimationFrame(run);
    return () => cancelAnimationFrame(raf);
  }, [to, reduced]);
  // formatScore truncates rather than rounds, so a 4.99 never flashes "5.0" beside Sell.
  return <>{formatScore(v)}</>;
}

function VerdictView({ analysis, reduced }: { analysis: AnalysisDetail; reduced: boolean }) {
  const card = analysis.scorecard!;
  const total = card.total ?? 0;
  const t = card.thresholds;
  const holdAt = t.hold * 10;
  const buyAt = t.buy * 10;
  const name = analysis.blocks?.market?.name ?? analysis.ticker;

  return (
    <div>
      <p className="text-[13px] text-ink-muted">Our view on {name}</p>
      <div className="mt-2 flex items-end gap-4">
        <motion.p
          initial={reduced ? false : { opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4, delay: 0.1 }}
          className={cn(
            "origin-bottom-left text-[64px] font-semibold leading-[0.85] tracking-[-0.045em]",
            VERDICT_TEXT[card.rating],
          )}
        >
          {verdictWord(card.rating)}
        </motion.p>
        <p className="nums pb-1 text-[14px] text-ink-muted">
          <span className="text-[26px] font-semibold text-ink">
            <CountUp to={total} reduced={reduced} />
          </span>{" "}
          / 10
        </p>
      </div>

      {/* The scale, with the marker travelling to the score. */}
      <div className="relative mt-7">
        <div className="flex h-2 gap-[3px]">
          <span className="rounded-l-full bg-sell-fill/25" style={{ width: `${holdAt}%` }} />
          <span className="bg-hold-fill/25" style={{ width: `${buyAt - holdAt}%` }} />
          <span className="rounded-r-full bg-buy-fill/25" style={{ width: `${100 - buyAt}%` }} />
        </div>
        <motion.span
          aria-hidden
          initial={reduced ? false : { left: "0%" }}
          animate={{ left: `${Math.min(100, Math.max(0, total * 10))}%` }}
          transition={{ duration: 0.9, ease: [0.2, 0.8, 0.2, 1] }}
          className="absolute top-1 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-paper bg-ink shadow"
        />
        <div className="nums mt-2 flex text-[11px] text-ink-muted">
          <span style={{ width: `${holdAt}%` }}>Sell · below {t.hold}</span>
          <span style={{ width: `${buyAt - holdAt}%` }}>Hold</span>
          <span>Buy · {t.buy}+</span>
        </div>
      </div>

      <ul className="mt-6 flex flex-col">
        {DIMENSIONS.map((d, i) => {
          const v = card.dimension_scores?.[d];
          const g = typeof v === "number" ? grade(v, t) : null;
          return (
            <li
              key={d}
              className="grid grid-cols-[8.5rem_minmax(0,1fr)_4rem_2rem] items-center gap-3 border-b border-rule py-2.5 text-[13px] text-ink last:border-0"
            >
              {DIMENSION_LABELS[d]}
              <span className="h-1 overflow-hidden rounded-full bg-surface-sunk">
                {g && (
                  <motion.span
                    initial={reduced ? false : { width: 0 }}
                    animate={{ width: `${(v as number) * 10}%` }}
                    transition={{ duration: 0.6, delay: 0.3 + i * 0.12, ease: "easeOut" }}
                    className={cn("block h-full rounded-full", BAR[g.text])}
                  />
                )}
              </span>
              <span className="text-[12px] text-ink-muted">{g?.word ?? "—"}</span>
              <span className="nums text-right font-semibold">
                {typeof v === "number" ? formatScore(v) : "—"}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ working */

function humanize(key: string) {
  const s = key.replace(/^avg_/, "average_").replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function WorkingView({ analysis, reduced }: { analysis: AnalysisDetail; reduced: boolean }) {
  const block = analysis.blocks?.profitability;
  const metrics = block?.metrics ?? {};
  const order = (block?.order ?? Object.keys(metrics)).filter((k) => metrics[k]).slice(0, 5);
  // Open the first row that has inputs to show; return on equity reads best when present.
  const hasInputs = (k: string) => Object.keys(metrics[k]?.inputs ?? {}).length > 0;
  const openKey = order.includes("roe") && hasInputs("roe") ? "roe" : order.find(hasInputs);
  const [open, setOpen] = React.useState<string | null>(reduced ? (openKey ?? null) : null);

  React.useEffect(() => {
    if (reduced || !openKey) return;
    const id = setTimeout(() => setOpen(openKey), 900);
    return () => clearTimeout(id);
  }, [openKey, reduced]);

  if (!order.length) return <p className="text-ink-muted">No measures for this company.</p>;

  return (
    <div className="nums">
      <div className="grid grid-cols-[minmax(0,1fr)_5rem_6.5rem] border-b border-rule pb-2 text-[12px] text-ink-muted">
        <span>Profitability measure</span>
        <span className="text-right">Value</span>
        <span className="text-right">vs competitors</span>
      </div>
      {order.map((k) => {
        const m = metrics[k];
        const isOpen = open === k;
        return (
          <div key={k} className="border-b border-rule last:border-0">
            <button
              type="button"
              onClick={() => setOpen(isOpen ? null : k)}
              className={cn(
                "grid w-full grid-cols-[minmax(0,1fr)_5rem_6.5rem] items-center py-2.5 text-left text-[13px] transition-colors",
                isOpen ? "text-ink" : "text-ink-soft hover:text-ink",
              )}
            >
              <span className="truncate font-medium">{m.label ?? humanize(m.name)}</span>
              <span className="text-right font-semibold text-ink">{formatMetric(m)}</span>
              <span className="text-right text-ink-muted">
                {m.peer_percentile == null ? "—" : formatPercentile(m.peer_percentile)}
              </span>
            </button>
            <AnimatePresence initial={false}>
              {isOpen && <Derivation metric={m} />}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}

function Derivation({ metric }: { metric: MetricValue }) {
  const inputs = Object.entries(metric.inputs ?? {});
  return (
    <motion.div
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: "auto", opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="overflow-hidden"
    >
      <div className="mb-3 rounded-lg border border-rule bg-surface p-3.5">
        <p className="text-[11px] font-medium text-ink-muted">How it was worked out</p>
        <code className="mt-1.5 block font-mono text-[12px] text-ink">{metric.formula}</code>
        <dl className="mt-3 grid grid-cols-[minmax(0,1fr)_auto] gap-x-6 gap-y-1 text-[12px]">
          {inputs.map(([k, v], i) => (
            <motion.div
              key={k}
              className="contents"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.2 + i * 0.1 }}
            >
              <dt className="text-ink-muted">{humanize(k)}</dt>
              <dd className="text-right font-medium text-ink">
                {v == null ? "—" : formatCurrency(v, 1)}
              </dd>
            </motion.div>
          ))}
        </dl>
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ sources */

/** The first claim in the thesis that carries citation markers, with its labels. */
function firstCitedClaim(thesis: string): { text: string; labels: string[] } | null {
  const re = /([^[\]]+?)\s*((?:\[[A-Z]?\d+\])+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(thesis))) {
    const sentences = m[1].trim().split(/(?<=[.!?])\s+/);
    const text = sentences[sentences.length - 1]?.trim();
    const labels = [...m[2].matchAll(/\[([A-Z]?\d+)\]/g)].map((x) => x[1]);
    if (text && text.length > 20) return { text, labels };
  }
  return null;
}

function SourcesView({ analysis, reduced }: { analysis: AnalysisDetail; reduced: boolean }) {
  const claim = analysis.memo ? firstCitedClaim(analysis.memo.thesis) : null;
  const sources = claim
    ? claim.labels
        .map((l) => analysis.evidence.find((e) => e.label === l))
        .filter((e): e is NonNullable<typeof e> => Boolean(e))
        .slice(0, 2)
    : [];

  if (!claim || !sources.length) {
    return (
      <p className="text-[14px] text-ink-muted">
        This report was written from the computed figures alone, so it cites no articles.
      </p>
    );
  }

  return (
    <div>
      <p className="text-[13px] text-ink-muted">From the written summary</p>
      <motion.blockquote
        initial={reduced ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4 }}
        className="mt-3 border-l-2 border-ink pl-4 font-serif text-[19px] leading-[1.55] text-ink"
      >
        {claim.text}{" "}
        {claim.labels.map((l, i) => (
          <motion.span
            key={l}
            animate={reduced ? undefined : { scale: [1, 1.25, 1] }}
            transition={{ delay: 0.7 + i * 0.15, duration: 0.5 }}
            className="ml-0.5 inline-block rounded bg-surface-sunk px-1.5 align-[0.2em] font-sans text-[11px] font-semibold text-ink"
          >
            {l}
          </motion.span>
        ))}
      </motion.blockquote>

      <p className="mt-7 text-[12px] font-medium text-ink-muted">Linked sources</p>
      <ul className="mt-2.5 flex flex-col gap-2.5">
        {sources.map((e, i) => (
          <motion.li
            key={e.label}
            initial={reduced ? false : { opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 1 + i * 0.2, duration: 0.4, ease: "easeOut" }}
            className="flex items-start gap-3 rounded-lg border border-rule bg-surface p-3.5"
          >
            <span className="grid size-8 shrink-0 place-items-center rounded-md bg-surface-sunk">
              <FileText className="size-4 text-ink-muted" aria-hidden />
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2 text-[12px] text-ink-muted">
                <span className="rounded bg-surface-sunk px-1.5 font-semibold text-ink">
                  {e.label}
                </span>
                {e.section ?? "Source"}
                {e.published && <span>· {formatDate(e.published)}</span>}
              </span>
              <span className="mt-1 block truncate text-[14px] font-medium text-ink">
                {e.title ?? "Untitled passage"}
              </span>
            </span>
          </motion.li>
        ))}
      </ul>
    </div>
  );
}

/* -------------------------------------------------------------------- track */

function TrackView({ cards, reduced }: { cards: ShowcaseCard[]; reduced: boolean }) {
  const cols = "grid grid-cols-[1.25rem_minmax(0,1fr)_4rem_minmax(0,7rem)_4.5rem] items-center gap-3";
  return (
    <div className="nums">
      <div className={cn(cols, "border-b border-rule pb-2 text-[12px] text-ink-muted")}>
        <span />
        <span>Watchlist</span>
        <span>Rating</span>
        <span>Score</span>
        <span className="text-right">Price</span>
      </div>
      {cards.map((c, i) => (
        <motion.div
          key={c.id}
          initial={reduced ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 + i * 0.12, duration: 0.35 }}
          className={cn(cols, "border-b border-rule py-3 text-[13px] last:border-0")}
        >
          <Star
            className={cn("size-4", i < 2 ? "fill-gold text-gold" : "text-faint")}
            aria-hidden
          />
          <span className="min-w-0 truncate">
            <span className="font-semibold text-ink">{c.ticker}</span>{" "}
            <span className="text-ink-muted">{c.name}</span>
          </span>
          <span>
            {c.rating && (
              <span
                className={cn(
                  "rounded px-1.5 py-0.5 text-[11px] font-semibold",
                  VERDICT_CHIP[c.rating],
                )}
              >
                {verdictWord(c.rating)}
              </span>
            )}
          </span>
          <span className="flex items-center gap-2">
            <span className="h-1 flex-1 overflow-hidden rounded-full bg-surface-sunk">
              <motion.span
                initial={reduced ? false : { width: 0 }}
                animate={{ width: `${(c.total_score ?? 0) * 10}%` }}
                transition={{ delay: 0.3 + i * 0.12, duration: 0.6 }}
                className={cn(
                  "block h-full rounded-full",
                  c.rating === "BUY"
                    ? "bg-buy-fill"
                    : c.rating === "SELL"
                      ? "bg-sell-fill"
                      : "bg-hold-fill",
                )}
              />
            </span>
            <span className="w-7 text-right font-semibold text-ink">
              {formatScore(c.total_score)}
            </span>
          </span>
          <span className="text-right text-ink">{formatCurrency(c.price)}</span>
        </motion.div>
      ))}
    </div>
  );
}
