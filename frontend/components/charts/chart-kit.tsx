"use client";

import * as React from "react";
import { ResponsiveContainer } from "recharts";

/** Shared chart furniture.
 *
 *  Recharts' defaults are instantly recognizable, so every one of them is replaced here
 *  rather than fought chart by chart: the series colours, the grid (horizontal only, in
 *  `rule`), the axes (ticks without lines), and the tooltip (rebuilt from scratch,
 *  because the built-in one carries its own border, shadow and font stack).
 */

/** Every colour is a custom property rather than a hex literal.
 *
 *  SVG presentation attributes are CSS values, so `stroke={"var(--ink)"}` resolves the
 *  same way a stylesheet would — which means the charts follow the theme without a
 *  single re-render, and a palette change lands in one file instead of nine. Hex
 *  literals here were invisible against the dark ground. */
export const CHART = {
  ink: "var(--ink)",
  inkSoft: "var(--ink-soft)",
  muted: "var(--ink-muted)",
  rule: "var(--rule)",
  ruleSoft: "var(--rule-soft)",
  surface: "var(--surface)",
  // "This company" in a chart: blue, because green, amber and red mean a verdict and
  // ink is for things you can click.
  accent: "var(--chart-1)",
  peer: "var(--chart-peer)",
  buy: "var(--buy)",
  hold: "var(--hold)",
  sell: "var(--sell)",
  series: [
    "var(--chart-1)",
    "var(--chart-2)",
    "var(--chart-3)",
    "var(--chart-4)",
    "var(--chart-5)",
  ],
} as const;

/** The margin cascade.
 *
 *  Not a categorical palette: gross, operating and net are one quantity at successive
 *  deductions, so a single hue running light to dark is the honest encoding. The only
 *  pair that can actually cross is net and free cash flow, and that one is separated by
 *  a dash rather than by hue — every series is also labelled directly at its end, so
 *  identity never rests on colour alone.
 */
export const CASCADE = [
  "var(--cascade-1)",
  "var(--cascade-2)",
  "var(--cascade-3)",
  "var(--cascade-4)",
] as const;

export const AXIS_PROPS = {
  tickLine: false,
  axisLine: false,
  tick: { fill: CHART.muted, fontSize: 11 },
  style: { fontVariantNumeric: "tabular-nums" as const },
};

export const GRID_PROPS = {
  stroke: CHART.rule,
  strokeDasharray: "0",
  vertical: false,
} as const;

/** Tooltips are rebuilt rather than restyled: matching the surface, rule and ink tokens
 *  exactly matters more than reusing the default shell. */
export function ChartTooltip({
  title,
  rows,
  footer,
}: {
  title?: React.ReactNode;
  rows: { label: string; value: string; color?: string }[];
  footer?: React.ReactNode;
}) {
  return (
    <div
      className="rounded-md border border-rule bg-surface-raised px-2.5 py-2 shadow-float"
      style={{ minWidth: "9rem" }}
    >
      {title !== undefined && (
        <div className="mb-1.5 text-micro font-medium text-muted-foreground">
          {title}
        </div>
      )}
      <dl className="space-y-1">
        {rows.map((r) => (
          <div key={r.label} className="flex items-baseline justify-between gap-4">
            <dt className="flex items-center gap-1.5 text-small text-ink-soft">
              {r.color && (
                <span
                  aria-hidden
                  className="inline-block h-[2px] w-3 rounded-full"
                  style={{ background: r.color }}
                />
              )}
              {r.label}
            </dt>
            <dd className="nums text-small text-ink">{r.value}</dd>
          </div>
        ))}
      </dl>
      {footer && (
        <div className="mt-1.5 border-t border-rule-soft pt-1.5 text-micro text-muted-foreground">
          {footer}
        </div>
      )}
    </div>
  );
}

/** A titled chart frame. The title names the series when there is only one, which is
 *  why most of these charts need no legend at all. */
/** The height the enclosing ChartFrame reserved, so a canvas inside it need not repeat
 *  the number. A chart that subdivides that space passes its own instead. */
const FrameHeight = React.createContext(240);

/** Recharts' responsive wrapper, told what it is about to be measured as.
 *
 *  ResponsiveContainer sizes itself from a ResizeObserver, which cannot report until
 *  after the first paint, so until then it falls back to `initialDimension` — and that
 *  default is `{width: -1, height: -1}`. Rendering a chart at a negative size trips its
 *  own sanity check, which is where "The width(-1) and height(-1) of chart should be
 *  greater than 0" comes from: not a broken container, just the frame before the
 *  measurement lands. It is worth passing rather than ignoring because recharts hard-
 *  codes `isDev = true` in the build we ship, so the warning reaches production
 *  consoles too, once per chart per mount.
 *
 *  The height is the half we genuinely know — ChartFrame reserved it — and one real
 *  dimension is enough, both to satisfy the check and to make that first frame the
 *  right shape instead of a degenerate one. The width stays unknown until measured.
 */
export function ChartCanvas({
  children,
  height,
}: {
  children: React.ReactElement;
  height?: number;
}) {
  const framed = React.useContext(FrameHeight);
  return (
    <ResponsiveContainer
      width="100%"
      height="100%"
      initialDimension={{ width: 0, height: height ?? framed }}
    >
      {children}
    </ResponsiveContainer>
  );
}

export function ChartFrame({
  title,
  note,
  children,
  height = 240,
  action,
}: {
  title: string;
  note?: React.ReactNode;
  children: React.ReactNode;
  height?: number;
  action?: React.ReactNode;
}) {
  return (
    <figure className="panel p-4">
      <figcaption className="mb-3 flex items-baseline justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-base font-medium text-ink">{title}</h3>
          {note && (
            <p className="mt-0.5 max-w-[58ch] text-micro leading-relaxed text-muted-foreground">
              {note}
            </p>
          )}
        </div>
        {action}
      </figcaption>
      <div style={{ height, minWidth: 0 }}>
        <FrameHeight.Provider value={height}>{children}</FrameHeight.Provider>
      </div>
    </figure>
  );
}

export function EmptyChart({ reason }: { reason: string }) {
  return (
    <div className="flex h-full items-center justify-center rounded-md border border-dashed border-rule px-6">
      <p className="max-w-[36ch] text-center text-small text-muted-foreground">
        {reason}
      </p>
    </div>
  );
}

/** Axis tick formatters. Percentages are formatted as percentages and currency is
 *  abbreviated; a raw float on an axis is a bug. */
export const fmtPercentTick = (v: number) => `${(v * 100).toFixed(0)}%`;
export const fmtCurrencyTick = (v: number) => {
  const abs = Math.abs(v);
  if (abs >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(0)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
};
export const fmtMultipleTick = (v: number) => `${v.toFixed(0)}x`;
export const fmtDaysTick = (v: number) => `${v.toFixed(0)}d`;
