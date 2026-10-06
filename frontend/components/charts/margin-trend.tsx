"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  AXIS_PROPS,
  CASCADE,
  CHART,
  ChartCanvas,
  ChartFrame,
  ChartTooltip,
  EmptyChart,
  GRID_PROPS,
  fmtPercentTick,
} from "@/components/charts/chart-kit";
import { formatPercent } from "@/lib/format";

interface Row {
  period: string;
  gross_margin: number | null;
  operating_margin: number | null;
  net_margin: number | null;
  fcf_margin: number | null;
}

const SERIES = [
  { key: "gross_margin", label: "Gross", color: CASCADE[0], dash: undefined },
  { key: "operating_margin", label: "Operating", color: CASCADE[1], dash: undefined },
  { key: "net_margin", label: "Net", color: CASCADE[2], dash: undefined },
  { key: "fcf_margin", label: "Free cash flow", color: CASCADE[3], dash: "4 3" },
] as const;

export function MarginTrend({ data }: { data: Row[] }) {
  const usable = (data ?? []).filter((d) =>
    SERIES.some((s) => d[s.key] !== null && d[s.key] !== undefined),
  );

  const present = SERIES.filter((s) =>
    usable.some((d) => d[s.key] !== null && d[s.key] !== undefined),
  );

  return (
    <ChartFrame
      title="Margins over five years"
      note={
        <>
          How much of each sales dollar is left at each stage: after making the product
          (gross), after running the business (operating), as final profit (net), and as
          spare cash (dashed line). Rising lines are good.
        </>
      }
      height={252}
    >
      {usable.length < 2 || present.length === 0 ? (
        <EmptyChart reason="Fewer than two annual periods of margin data are available." />
      ) : (
        <ChartCanvas>
          <LineChart data={usable} margin={{ top: 8, right: 84, left: 0, bottom: 4 }}>
            <CartesianGrid {...GRID_PROPS} />
            <XAxis dataKey="period" {...AXIS_PROPS} />
            <YAxis
              {...AXIS_PROPS}
              tickFormatter={fmtPercentTick}
              width={44}
              domain={["auto", "auto"]}
            />
            <Tooltip
              cursor={{ stroke: CHART.rule, strokeWidth: 1 }}
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <ChartTooltip
                    title={label as string}
                    rows={payload.map((p) => ({
                      label:
                        SERIES.find((s) => s.key === p.dataKey)?.label ??
                        String(p.dataKey),
                      value: formatPercent(p.value as number),
                      color: p.color,
                    }))}
                  />
                ) : null
              }
            />
            {present.map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                strokeWidth={s.key === "net_margin" ? 2.25 : 2}
                strokeDasharray={s.dash}
                dot={false}
                activeDot={{ r: 3.5, strokeWidth: 2, stroke: CHART.surface }}
                connectNulls
                isAnimationActive={false}
                label={({ index, x, y, value }) =>
                  /* Direct labels at the end of each line, so no legend is needed
                     and identity never rests on colour alone. */
                  index === usable.length - 1 && value !== null ? (
                    <text
                      key={`${s.key}-label`}
                      x={(x as number) + 8}
                      y={(y as number) + 3.5}
                      fill={s.color}
                      fontSize={11}
                      fontWeight={500}
                    >
                      {s.label}
                    </text>
                  ) : (
                    <g key={`${s.key}-${index}`} />
                  )
                }
              />
            ))}
          </LineChart>
        </ChartCanvas>
      )}
    </ChartFrame>
  );
}
