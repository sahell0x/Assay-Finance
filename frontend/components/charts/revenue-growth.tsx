"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
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
  fmtCurrencyTick,
  fmtPercentTick,
} from "@/components/charts/chart-kit";
import { formatCurrency, formatPercent } from "@/lib/format";

interface Row {
  period: string;
  revenue: number | null;
  yoy: number | null;
}

/** Revenue, and the growth rate underneath it.
 *
 *  This was one chart with two y-scales. That is the commonest serious mistake in
 *  financial charting: a second axis can be slid up or down until the two series appear
 *  to confirm each other, and the reader has no way to see it has been. The defence used
 *  to be that growth is the derivative of revenue rather than an unrelated measure —
 *  true, and still not enough, because the crossings a reader sees remain artefacts of
 *  where the axes were pinned.
 *
 *  Two stacked panels on one shared x-axis say the same thing and cannot mislead: the
 *  eye reads down a period rather than across a scale. Growth also gains something it
 *  could not have before — a real zero line with negative bars below it, so a contraction
 *  looks like a contraction.
 */
export function RevenueGrowth({ data }: { data: Row[] }) {
  const usable = (data ?? []).filter((d) => d.revenue !== null);

  if (usable.length < 2) {
    return (
      <ChartFrame title="Revenue and growth" height={252}>
        <EmptyChart reason="Fewer than two annual periods of revenue are available." />
      </ChartFrame>
    );
  }

  const hasGrowth = usable.some((d) => d.yoy !== null && d.yoy !== undefined);

  const REVENUE_H = 176;
  const GROWTH_H = 116;

  return (
    <ChartFrame
      title="Sales, and how fast they are growing"
      note="Top: total sales each year. Bottom: how much sales grew or shrank compared with the year before."
      height={hasGrowth ? REVENUE_H + GROWTH_H : REVENUE_H}
    >
      <div className="flex flex-col">
        <div style={{ height: REVENUE_H }}>
          <ChartCanvas height={REVENUE_H}>
            <BarChart
              data={usable}
              margin={{ top: 6, right: 8, left: 0, bottom: 0 }}
              syncId="revenue"
            >
              <CartesianGrid {...GRID_PROPS} />
              <XAxis dataKey="period" {...AXIS_PROPS} hide={hasGrowth} />
              <YAxis {...AXIS_PROPS} width={56} tickFormatter={fmtCurrencyTick} />
              <Tooltip
                cursor={{ fill: CHART.ruleSoft }}
                content={({ active, payload, label }) =>
                  active && payload?.length ? (
                    <ChartTooltip
                      title={label as string}
                      rows={[
                        {
                          label: "Revenue",
                          value: formatCurrency(payload[0]?.value as number),
                          color: CHART.series[0],
                        },
                      ]}
                    />
                  ) : null
                }
              />
              <Bar
                dataKey="revenue"
                fill={CHART.series[0]}
                radius={[4, 4, 0, 0]}
                maxBarSize={44}
                isAnimationActive={false}
              />
            </BarChart>
          </ChartCanvas>
        </div>

        {hasGrowth && (
          <div style={{ height: GROWTH_H }}>
            <ChartCanvas height={GROWTH_H}>
              <BarChart
                data={usable}
                margin={{ top: 0, right: 8, left: 0, bottom: 4 }}
                syncId="revenue"
              >
                <CartesianGrid {...GRID_PROPS} />
                <XAxis dataKey="period" {...AXIS_PROPS} />
                <YAxis {...AXIS_PROPS} width={56} tickFormatter={fmtPercentTick} />
                {/* The zero line is the point of this panel, so it is ink, not rule. */}
                <ReferenceLine y={0} stroke={CHART.ink} strokeWidth={1} />
                <Tooltip
                  cursor={{ fill: CHART.ruleSoft }}
                  content={({ active, payload, label }) =>
                    active && payload?.length ? (
                      <ChartTooltip
                        title={label as string}
                        rows={[
                          {
                            label: "Year-over-year",
                            value: formatPercent(payload[0]?.value as number),
                            color:
                              ((payload[0]?.value as number) ?? 0) < 0
                                ? CHART.sell
                                : CHART.buy,
                          },
                        ]}
                      />
                    ) : null
                  }
                />
                <Bar dataKey="yoy" maxBarSize={44} isAnimationActive={false}>
                  {/* Growth is polarity, not identity: two hues either side of zero,
                      which is the one place a rating colour is also the right encoding. */}
                  {usable.map((d, i) => (
                    <Cell
                      key={i}
                      fill={(d.yoy ?? 0) < 0 ? CHART.sell : CHART.buy}
                      radius={
                        ((d.yoy ?? 0) < 0 ? [0, 0, 4, 4] : [4, 4, 0, 0]) as never
                      }
                    />
                  ))}
                </Bar>
              </BarChart>
            </ChartCanvas>
          </div>
        )}
      </div>
    </ChartFrame>
  );
}
