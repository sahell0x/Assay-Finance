"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  AXIS_PROPS,
  CHART,
  ChartCanvas,
  ChartFrame,
  ChartTooltip,
  EmptyChart,
  GRID_PROPS,
} from "@/components/charts/chart-kit";
import { formatDate, formatScore } from "@/lib/format";
import type { HistoryPoint } from "@/lib/types";

/** Composite score over time, with the rating bands behind it.
 *
 *  The bands are the point: a score drifting toward 7.5 is a rating about to change, and
 *  that is invisible on a bare line. Washes rather than saturated fills, so the line
 *  stays the figure and the bands stay the ground.
 */
export function ScoreHistory({
  points,
  thresholds = { buy: 7.5, hold: 5.0 },
  ticker,
}: {
  points: HistoryPoint[];
  thresholds?: { buy: number; hold: number };
  ticker?: string;
}) {
  const usable = (points ?? [])
    .filter((p) => p.total !== null)
    .map((p) => ({ ...p, ts: new Date(p.date).getTime() }));

  if (usable.length < 2) {
    return (
      <ChartFrame title={ticker ? `${ticker} overall score over time` : "Score over time"} height={240}>
        <EmptyChart reason="Run this ticker at least twice to see how its score moves." />
      </ChartFrame>
    );
  }

  return (
    <ChartFrame
      title={ticker ? `${ticker} overall score over time` : "Overall score over time"}
      note="Shaded bands are the rating thresholds. A line drifting toward a boundary is a rating about to change."
      height={240}
    >
      <ChartCanvas>
        <LineChart data={usable} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
          <CartesianGrid {...GRID_PROPS} />
          <ReferenceArea y1={thresholds.buy} y2={10} fill={CHART.buy} fillOpacity={0.06} />
          <ReferenceArea
            y1={thresholds.hold}
            y2={thresholds.buy}
            fill={CHART.hold}
            fillOpacity={0.05}
          />
          <ReferenceArea y1={0} y2={thresholds.hold} fill={CHART.sell} fillOpacity={0.05} />
          <ReferenceLine y={thresholds.buy} stroke={CHART.rule} />
          <ReferenceLine y={thresholds.hold} stroke={CHART.rule} />
          <XAxis
            dataKey="ts"
            type="number"
            domain={["dataMin", "dataMax"]}
            {...AXIS_PROPS}
            tickFormatter={(v: number) =>
              new Date(v).toLocaleDateString("en-GB", { day: "numeric", month: "short" })
            }
          />
          <YAxis {...AXIS_PROPS} width={30} domain={[0, 10]} ticks={[0, 2.5, 5, 7.5, 10]} />
          <Tooltip
            cursor={{ stroke: CHART.rule }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as HistoryPoint;
              return (
                <ChartTooltip
                  title={formatDate(p.date)}
                  rows={[
                    { label: "Overall score", value: formatScore(p.total ?? 0) },
                    { label: "Rating", value: p.rating ?? "—" },
                  ]}
                />
              );
            }}
          />
          <Line
            type="monotone"
            dataKey="total"
            stroke={CHART.accent}
            strokeWidth={2}
            dot={{ r: 2.5, fill: CHART.accent, strokeWidth: 0 }}
            activeDot={{ r: 4, strokeWidth: 2, stroke: CHART.surface }}
            isAnimationActive={false}
          />
        </LineChart>
      </ChartCanvas>
    </ChartFrame>
  );
}
