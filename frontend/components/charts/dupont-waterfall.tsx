"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
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

interface Dupont {
  net_margin: number | null;
  asset_turnover: number | null;
  equity_multiplier: number | null;
  product: number | null;
  roe_direct: number | null;
  reconciles: boolean | null;
}

/** Return on equity, decomposed.
 *
 *  A waterfall built from a stacked bar with a transparent base: the first series is
 *  the floating offset and is painted with no fill, so only the second series is
 *  visible. This is the standard way to get a waterfall out of a library that has no
 *  waterfall primitive, and it is exact — the bar tops land where the cumulative
 *  product lands.
 *
 *  ROE is multiplicative, not additive, so the steps are drawn on a log-ish cumulative
 *  product: each stage shows what the running product becomes once that factor is
 *  applied. The final bar is the ROE, drawn from zero.
 */
export function DupontWaterfall({ dupont }: { dupont?: Dupont | null }) {
  const nm = dupont?.net_margin ?? null;
  const at = dupont?.asset_turnover ?? null;
  const em = dupont?.equity_multiplier ?? null;
  const roe = dupont?.product ?? dupont?.roe_direct ?? null;

  if (nm === null || at === null || em === null || roe === null) {
    return (
      <ChartFrame
        title="What drives the return to shareholders"
        note="Profit margin, times how hard assets are worked, times how much is borrowed."
        height={252}
      >
        <EmptyChart reason="The DuPont decomposition needs net margin, asset turnover and the equity multiplier. At least one is unavailable for this company." />
      </ChartFrame>
    );
  }

  const afterMargin = nm;
  const afterTurnover = nm * at;
  const afterLeverage = nm * at * em;

  const rows = [
    { stage: "Net margin", base: 0, delta: afterMargin, running: afterMargin, factor: nm, unit: "%" },
    {
      stage: "x Asset turnover",
      base: Math.min(afterMargin, afterTurnover),
      delta: Math.abs(afterTurnover - afterMargin),
      running: afterTurnover,
      factor: at,
      unit: "x",
    },
    {
      stage: "x Leverage",
      base: Math.min(afterTurnover, afterLeverage),
      delta: Math.abs(afterLeverage - afterTurnover),
      running: afterLeverage,
      factor: em,
      unit: "x",
    },
    { stage: "Return on equity", base: 0, delta: afterLeverage, running: afterLeverage, factor: roe, unit: "%", total: true },
  ];

  const fmt = (v: number, unit: string) =>
    unit === "%" ? `${(v * 100).toFixed(1)}%` : `${v.toFixed(2)}x`;

  return (
    <ChartFrame
      title="What drives the return to shareholders"
      note={
        <>
          Return to shareholders is profit margin, times how hard assets are worked,
          times how much is borrowed. Returns built on high margins are safer than
          returns built on debt.
          {dupont?.reconciles === false &&
            " The parts do not multiply back exactly to the total, because the underlying reports cover slightly different periods."}
        </>
      }
      height={252}
    >
      <ChartCanvas>
        <BarChart data={rows} margin={{ top: 22, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis dataKey="stage" {...AXIS_PROPS} interval={0} />
          <YAxis
            {...AXIS_PROPS}
            width={44}
            tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
          />
          <Tooltip
            cursor={{ fill: CHART.ruleSoft }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0].payload as (typeof rows)[number];
              return (
                <ChartTooltip
                  title={row.stage}
                  rows={[
                    { label: "Factor", value: fmt(row.factor, row.unit) },
                    { label: "Running product", value: `${(row.running * 100).toFixed(1)}%` },
                  ]}
                />
              );
            }}
          />
          {/* Connectors between steps, drawn at the level where one step hands off to
              the next. Without them four separate bars do not read as a cascade. */}
          {[
            ["Net margin", "x Asset turnover", afterMargin],
            ["x Asset turnover", "x Leverage", afterTurnover],
            ["x Leverage", "Return on equity", afterLeverage],
          ].map(([from, to, y]) => (
            <ReferenceLine
              key={String(from)}
              segment={[
                { x: from as string, y: y as number },
                { x: to as string, y: y as number },
              ]}
              stroke={CHART.rule}
              strokeDasharray="3 3"
              strokeWidth={1}
              ifOverflow="extendDomain"
            />
          ))}

          {/* The invisible base that makes the bars float. */}
          <Bar dataKey="base" stackId="w" fill="transparent" isAnimationActive={false} />
          <Bar dataKey="delta" stackId="w" isAnimationActive={false} maxBarSize={64}>
            {rows.map((r, i) => (
              <Cell key={i} fill={r.total ? CHART.accent : CHART.series[1]} />
            ))}
            <LabelList
              dataKey="running"
              content={(props) => {
                /* The label belongs at the running value, which for a step that
                   *reduces* the product is the bottom of its bar, not the top.
                   Putting every label above the bar told the reader that asset
                   turnover took the product to 40%, when it took it down to 18%. */
                const { x, y, width, height, index } = props as {
                  x: number; y: number; width: number; height: number; index: number;
                };
                const row = rows[index];
                if (!row) return null;
                const topValue = row.base + row.delta;
                const atTop = Math.abs(row.running - topValue) < 1e-9;
                const ty = atTop ? y - 6 : y + height + 13;
                return (
                  <text
                    x={x + width / 2}
                    y={ty}
                    textAnchor="middle"
                    fontSize={11}
                    fill={row.total ? CHART.ink : CHART.muted}
                    fontWeight={row.total ? 600 : 400}
                    style={{ fontVariantNumeric: "tabular-nums" }}
                  >
                    {`${(row.running * 100).toFixed(1)}%`}
                  </text>
                );
              }}
            />
          </Bar>
        </BarChart>
      </ChartCanvas>
    </ChartFrame>
  );
}
