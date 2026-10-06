"use client";

import { useReducedMotion } from "motion/react";
import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";

import {
  AXIS_PROPS,
  CHART,
  ChartCanvas,
  ChartFrame,
  ChartTooltip,
  EmptyChart,
  GRID_PROPS,
} from "@/components/charts/chart-kit";
import { CountUp } from "@/components/app/kit";
import { formatRupees } from "@/lib/format";
import type { BillingSummary } from "@/lib/types";

const FREE = CHART.series[0];
const BOUGHT = CHART.series[1];

/** The four numbers a bank statement leads with: what you used, what you bought, what
 *  it cost, and what came back. */
export function SpendTiles({ summary, testMode }: { summary: BillingSummary; testMode: boolean }) {
  return (
    <div className="grid gap-px overflow-hidden rounded-[14px] border border-rule bg-rule sm:grid-cols-2 lg:grid-cols-4">
      <Tile
        label="Analyses run"
        value={summary.credits_used}
        note={`${summary.free_used} on free credits, ${summary.bought_used} on bought`}
      />
      <Tile
        label="Credits bought"
        value={summary.credits_bought}
        note={
          summary.purchases === 0
            ? "No purchases yet"
            : `${summary.purchases} ${summary.purchases === 1 ? "purchase" : "purchases"}, ${summary.paid_balance} left`
        }
      />
      <Tile
        label={testMode ? "Total paid (test money)" : "Total paid"}
        value={summary.amount_spent_paise}
        format={(v) => formatRupees(Math.round(v))}
        note={testMode ? "Nothing real was charged" : "Across all purchases"}
      />
      <Tile
        label="Credits given back"
        value={summary.refunds}
        note="Analyses that did not finish are never charged"
      />
    </div>
  );
}

function Tile({
  label,
  value,
  note,
  format,
}: {
  label: string;
  value: number;
  note: string;
  format?: (v: number) => string;
}) {
  return (
    <div className="bg-surface p-5">
      <div className="text-[13px] font-medium text-ink-muted">{label}</div>
      <div className="mt-2 text-[28px] font-semibold leading-none tracking-[-0.035em] text-ink">
        <CountUp value={value} format={format} />
      </div>
      <div className="mt-2 text-[13px] leading-relaxed text-ink-muted">{note}</div>
    </div>
  );
}

function shortDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

/** Credits used per day for the last 30 days, free and bought stacked.
 *
 *  A stack rather than two series side by side: the question is "how much did I use",
 *  and the split is the detail. Days with nothing are kept, so a quiet week looks quiet.
 */
export function UsageChart({ summary }: { summary: BillingSummary }) {
  const reduced = useReducedMotion();
  const data = summary.daily.map((d) => ({ ...d, label: shortDate(d.date) }));
  const empty = data.every((d) => d.free + d.bought === 0);

  return (
    <ChartFrame
      title="Credits used, last 30 days"
      note="Each bar is one day. A refunded analysis is taken off the day it was refunded."
      height={200}
      action={
        <div className="flex shrink-0 items-center gap-3 text-micro text-muted-foreground">
          <Key color={FREE} label="Free" />
          <Key color={BOUGHT} label="Bought" />
        </div>
      }
    >
      {empty ? (
        <EmptyChart reason="No credits used in the last 30 days. Run an analysis and it will show up here." />
      ) : (
        <ChartCanvas>
          <BarChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...GRID_PROPS} />
            <XAxis dataKey="label" {...AXIS_PROPS} interval="preserveStartEnd" minTickGap={24} />
            <YAxis {...AXIS_PROPS} width={28} allowDecimals={false} />
            <Tooltip
              cursor={{ fill: CHART.ruleSoft }}
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <ChartTooltip
                    title={label as string}
                    rows={[
                      { label: "Free", value: String(payload[0]?.payload.free ?? 0), color: FREE },
                      {
                        label: "Bought",
                        value: String(payload[0]?.payload.bought ?? 0),
                        color: BOUGHT,
                      },
                    ]}
                  />
                ) : null
              }
            />
            <Bar
              dataKey="free"
              stackId="c"
              fill={FREE}
              maxBarSize={18}
              isAnimationActive={!reduced}
              animationDuration={900}
              animationEasing="ease-out"
            />
            <Bar
              dataKey="bought"
              stackId="c"
              fill={BOUGHT}
              radius={[3, 3, 0, 0]}
              maxBarSize={18}
              isAnimationActive={!reduced}
              animationBegin={250}
              animationDuration={900}
              animationEasing="ease-out"
            />
          </BarChart>
        </ChartCanvas>
      )}
    </ChartFrame>
  );
}

function Key({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span aria-hidden className="inline-block size-2.5 rounded-sm" style={{ background: color }} />
      {label}
    </span>
  );
}
