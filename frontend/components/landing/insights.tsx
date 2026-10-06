"use client";

import { useReducedMotion } from "motion/react";

import { Appear, RiseText } from "@/components/landing/motion";
import { CONTAINER } from "@/components/landing/shared";
import { NumberTicker } from "@/components/ui/number-ticker";
import type { AnalysisDetail } from "@/lib/types";

type Stat = { value: number; decimals?: number; suffix?: string; label: string; body: string };

/** Counts taken from one stored analysis. Every figure here is read off the run itself,
 *  so the section is a receipt for a real report rather than a marketing claim. A count
 *  the run did not record is left out instead of being estimated. */
export function reportStats(a: AnalysisDetail): Stat[] {
  const b = a.blocks ?? {};
  const measures = (["profitability", "liquidity", "growth", "peers"] as const).reduce(
    (n, k) => n + Object.keys(b[k]?.metrics ?? {}).length,
    0,
  );
  const years = a.data_quality?.annual_periods ?? 0;
  const read = b.retrieval?.corpus_size ?? 0;
  const cited = a.evidence.length;
  const checked = b.critic?.figures_checked ?? 0;
  const seconds =
    a.created_at && a.completed_at
      ? (Date.parse(a.completed_at) - Date.parse(a.created_at)) / 1000
      : 0;

  const out: Stat[] = [];
  if (years) out.push({ value: years, label: "years of annual reports", body: "Read line by line, not summarised by a model." });
  if (measures) out.push({ value: measures, label: "measures calculated", body: "Profit, debt, growth and value, each with its formula." });
  if (read) out.push({ value: read, label: "passages searched", body: "From filings and recent news, to explain the numbers." });
  if (cited) out.push({ value: cited, label: "sources cited", body: "Every claim in the write-up links to one of them." });
  if (checked) out.push({ value: checked, label: "figures double-checked", body: "Numbers in the write-up are matched against the maths." });
  if (seconds > 0) out.push({ value: seconds / 60, decimals: 1, suffix: " min", label: "from start to verdict", body: "You can watch each step while it runs." });
  return out.slice(0, 6);
}

export function Insights({ analysis }: { analysis: AnalysisDetail }) {
  const reduced = useReducedMotion();
  const stats = reportStats(analysis);
  if (stats.length < 3) return null;
  // "PepsiCo's report", not "PepsiCo, Inc.'s report".
  const name = (analysis.blocks?.market?.name ?? analysis.ticker).replace(
    /,?\s+(Inc\.?|Corporation|Corp\.?|Company|Co\.|plc|Ltd\.?)$/i,
    "",
  );

  return (
    <section aria-labelledby="insights-heading" className="py-24 sm:py-32">
      <div className={CONTAINER}>
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] lg:items-end">
          <h2
            id="insights-heading"
            className="max-w-[18ch] text-[36px] font-semibold leading-[1.05] tracking-[-0.04em] text-ink sm:text-[52px]"
          >
            <RiseText inView text={`What went into ${name}'s report.`} />
          </h2>
          <Appear delay={0.2}>
            <p className="text-[17px] leading-relaxed text-ink-muted">
              A verdict is only worth the work behind it. These are the counts from that one
              run, straight from its record.
            </p>
          </Appear>
        </div>

        <div className="mt-14 grid grid-cols-1 border-t border-rule sm:grid-cols-2 lg:grid-cols-3">
          {stats.map((s, i) => (
            <Appear
              key={s.label}
              delay={(i % 3) * 0.08}
              className="border-b border-rule py-8 sm:px-6 sm:[&:nth-child(2n+1)]:pl-0 lg:[&:nth-child(2n+1)]:pl-6 lg:[&:nth-child(3n+1)]:pl-0 sm:[&:not(:nth-child(2n))]:border-r lg:[&:not(:nth-child(2n))]:border-r-0 lg:[&:not(:nth-child(3n))]:border-r"
            >
              <p className="nums text-[56px] font-semibold leading-none tracking-[-0.045em] text-ink sm:text-[68px]">
                <NumberTicker
                  value={s.value}
                  startValue={reduced ? s.value : 0}
                  decimalPlaces={s.decimals ?? 0}
                  className="tracking-[-0.045em] text-ink dark:text-ink"
                />
                {s.suffix && <span className="text-[0.5em] tracking-[-0.02em] text-ink-muted">{s.suffix}</span>}
              </p>
              <p className="mt-4 text-[16px] font-semibold text-ink">{s.label}</p>
              <p className="mt-1 text-[14px] leading-relaxed text-ink-muted">{s.body}</p>
            </Appear>
          ))}
        </div>
      </div>
    </section>
  );
}
