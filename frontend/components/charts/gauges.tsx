"use client";

import { CHART } from "@/components/charts/chart-kit";
import { DASH } from "@/lib/format";

interface Band {
  to: number;
  label: string;
  tone: "weak" | "neutral" | "strong";
}

export interface Gauge {
  key: string;
  label: string;
  value: number | null;
  bands: Band[];
  max: number;
}

const TONE: Record<Band["tone"], { fill: string; text: string }> = {
  weak: { fill: "var(--sell-wash)", text: CHART.sell },
  neutral: { fill: "var(--hold-wash)", text: CHART.hold },
  strong: { fill: "var(--buy-wash)", text: CHART.buy },
};

/** Horizontal threshold gauges.
 *
 *  Horizontal rather than radial: a dial makes you read an angle, a bar makes you read a
 *  position against named bands — and the bands are the information here. "2.1x interest
 *  coverage" means nothing without knowing that under 2 is strained.
 */
export function Gauges({ gauges }: { gauges: Gauge[] }) {
  return (
    <div className="panel p-4">
      <h3 className="text-base font-medium text-ink">
        Where these sit against the usual thresholds
      </h3>
      <p className="mb-4 mt-0.5 max-w-[58ch] text-micro leading-relaxed text-muted-foreground">
        The coloured bands show what analysts usually consider healthy. They are a guide only and do not affect the score.
      </p>

      <ul className="space-y-5">
        {gauges.map((g) => {
          const available = g.value !== null && g.value !== undefined;
          const at = available
            ? Math.max(0, Math.min(100, (g.value! / g.max) * 100))
            : 0;
          const band = available
            ? (g.bands.find((b) => g.value! <= b.to) ?? g.bands[g.bands.length - 1])
            : null;

          return (
            <li key={g.key}>
              <div className="mb-1.5 flex items-baseline justify-between gap-3">
                <span className="text-small text-ink-soft">{g.label}</span>
                <span className="flex items-baseline gap-2">
                  {band && (
                    <span
                      className="text-micro"
                      style={{ color: TONE[band.tone].text }}
                    >
                      {band.label}
                    </span>
                  )}
                  <span className="nums text-base font-medium text-ink">
                    {available ? g.value!.toFixed(2) : DASH}
                  </span>
                </span>
              </div>

              <div
                className="relative h-3 w-full overflow-hidden rounded-sm"
                role="img"
                aria-label={
                  available
                    ? `${g.label}: ${g.value!.toFixed(2)}, in the ${band?.label} band`
                    : `${g.label}: not available`
                }
              >
                {g.bands.map((b, i) => {
                  const from = i === 0 ? 0 : (g.bands[i - 1].to / g.max) * 100;
                  const to = Math.min(100, (b.to / g.max) * 100);
                  return (
                    <span
                      key={b.label}
                      className="absolute inset-y-0"
                      style={{
                        left: `${from}%`,
                        width: `${Math.max(0, to - from)}%`,
                        background: TONE[b.tone].fill,
                        /* A 2px surface gap between adjacent fills, so the band
                           boundaries read as boundaries. */
                        borderRight:
                          i < g.bands.length - 1 ? `2px solid ${CHART.surface}` : undefined,
                      }}
                    />
                  );
                })}

                {available && (
                  <span
                    className="absolute inset-y-0 w-[3px] rounded-full"
                    style={{
                      left: `calc(${at}% - 1.5px)`,
                      background: CHART.ink,
                      boxShadow: `0 0 0 1.5px ${CHART.surface}`,
                    }}
                  />
                )}
              </div>

              <div className="mt-1 flex justify-between text-micro text-muted-foreground">
                <span className="nums">0</span>
                {g.bands.slice(0, -1).map((b) => (
                  <span key={b.label} className="nums">
                    {b.to}
                  </span>
                ))}
                <span className="nums">{g.max}</span>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
