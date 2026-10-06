"use client";

import {
  CartesianGrid,
  Cell,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import {
  AXIS_PROPS,
  CHART,
  ChartCanvas,
  ChartFrame,
  ChartTooltip,
  EmptyChart,
  GRID_PROPS,
  fmtMultipleTick,
  fmtPercentTick,
} from "@/components/charts/chart-kit";
import { formatCurrency, formatPercent } from "@/lib/format";

interface Point {
  ticker: string;
  x: number;
  y: number;
  size?: number | null;
  is_target?: boolean;
}

/** What you pay against what you get.
 *
 *  Return on invested capital across, EV/EBITDA up, bubble area by market
 *  capitalisation. The useful reading is the diagonal: names below the trend are cheap
 *  for their quality, names above are expensive for it. The target is the only saturated
 *  mark on the plot and the only one always labelled — everything else is the cohort.
 */
export function PeerScatter({
  points,
  excluded = [],
  cap,
}: {
  points: Point[];
  excluded?: string[];
  cap?: number;
}) {
  const usable = (points ?? []).filter(
    (p) => Number.isFinite(p.x) && Number.isFinite(p.y),
  );

  if (usable.length < 3) {
    return (
      <ChartFrame title="Valuation against quality" height={220}>
        <EmptyChart
          reason={
            excluded.length > 0
              ? `Too few comparables have both a meaningful valuation multiple and a positive return on capital to plot. ${excluded.join(", ")} ${excluded.length === 1 ? "was" : "were"} excluded for trading above ${cap ? `${cap.toFixed(0)}x` : "the meaningful range"} EBITDA on a near-zero denominator.`
              : "At least three comparable companies with both a valuation multiple and a return on capital are needed to plot this."
          }
        />
      </ChartFrame>
    );
  }

  const sizes = usable.map((p) => p.size ?? 0).filter((s) => s > 0);
  const maxSize = sizes.length ? Math.max(...sizes) : 1;

  return (
    <ChartFrame
      title="Valuation against quality"
      note={
        <>
          Return on invested capital across, EV/EBITDA up, bubble area by market
          capitalisation. Below the diagonal is cheap for the quality; above it is dear.
          {excluded.length > 0 && (
            <>
              {" "}
              {excluded.join(", ")} {excluded.length === 1 ? "is" : "are"} not plotted:
              {excluded.length === 1 ? " its" : " their"} EV/EBITDA exceeds{" "}
              {cap ? `${cap.toFixed(0)}x` : "the meaningful range"} on near-zero EBITDA,
              which would flatten every other company onto the axis.
            </>
          )}
        </>
      }
      height={300}
    >
      <ChartCanvas>
        <ScatterChart margin={{ top: 12, right: 16, left: 0, bottom: 18 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis
            type="number"
            dataKey="x"
            {...AXIS_PROPS}
            tickFormatter={fmtPercentTick}
            domain={["auto", "auto"]}
            label={{
              value: "Return on invested capital",
              position: "insideBottom",
              offset: -12,
              style: { fill: CHART.muted, fontSize: 11 },
            }}
          />
          <YAxis
            type="number"
            dataKey="y"
            {...AXIS_PROPS}
            width={46}
            tickFormatter={fmtMultipleTick}
            domain={["auto", "auto"]}
            label={{
              value: "EV / EBITDA",
              angle: -90,
              position: "insideLeft",
              style: { fill: CHART.muted, fontSize: 11, textAnchor: "middle" },
            }}
          />
          <ZAxis type="number" dataKey="size" range={[70, 520]} domain={[0, maxSize]} />
          <Tooltip
            cursor={{ stroke: CHART.rule, strokeDasharray: "3 3" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as Point;
              return (
                <ChartTooltip
                  title={p.ticker}
                  rows={[
                    { label: "EV / EBITDA", value: `${p.y.toFixed(1)}x` },
                    { label: "Return on capital", value: formatPercent(p.x) },
                    ...(p.size
                      ? [{ label: "Market cap", value: formatCurrency(p.size) }]
                      : []),
                  ]}
                  footer={p.is_target ? "The company being analyzed" : undefined}
                />
              );
            }}
          />
          <Scatter
            data={usable}
            isAnimationActive={false}
            label={({ index, x, y }) => {
              const p = usable[index as number];
              /* Every mark is labelled: with eight or nine points there is room, and a
                 scatter you cannot name is a scatter you cannot use. */
              return (
                <text
                  key={p.ticker}
                  x={(x as number) + 11}
                  y={(y as number) + 3.5}
                  fontSize={10.5}
                  fontWeight={p.is_target ? 600 : 400}
                  fill={p.is_target ? CHART.accent : CHART.muted}
                >
                  {p.ticker}
                </text>
              );
            }}
          >
            {usable.map((p) => (
              <Cell
                key={p.ticker}
                fill={p.is_target ? CHART.accent : CHART.peer}
                stroke={p.is_target ? CHART.surface : CHART.muted}
                strokeWidth={p.is_target ? 2 : 1}
                fillOpacity={p.is_target ? 1 : 0.75}
              />
            ))}
          </Scatter>
        </ScatterChart>
      </ChartCanvas>
    </ChartFrame>
  );
}
