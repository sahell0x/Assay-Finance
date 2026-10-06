import { cn } from "@/lib/cn";
import { DIMENSIONS, type Rating } from "@/lib/types";

const SHORT: Record<string, string> = {
  profitability: "Profit",
  financial_health: "Health",
  growth: "Growth",
  valuation: "Value",
  sentiment: "Mood",
};

const TONE: Record<Rating, { fill: string; stroke: string }> = {
  BUY: { fill: "var(--buy-fill)", stroke: "var(--buy)" },
  HOLD: { fill: "var(--hold-fill)", stroke: "var(--hold)" },
  SELL: { fill: "var(--sell-fill)", stroke: "var(--sell)" },
};

/** The report card as a shape: five areas on five spokes, each pushed out by its score
 *  out of 10. A strong company is a big, round pentagon; a lopsided one shows at a
 *  glance which area lets it down. The fill takes the verdict's colour.
 *
 *  Drawn straight from the stored dimension scores. An area that could not be scored
 *  sits at the centre and its label is struck through, rather than being guessed. */
export function ReportShape({
  scores,
  rating,
  size = 180,
  labels = true,
  className,
}: {
  scores: Record<string, number | null | undefined>;
  rating?: Rating | null;
  size?: number;
  labels?: boolean;
  className?: string;
}) {
  const pad = labels ? 40 : 4;
  const r = size / 2 - pad;
  const c = size / 2;
  const angle = (i: number) => -Math.PI / 2 + (i * 2 * Math.PI) / DIMENSIONS.length;
  const at = (i: number, k: number) =>
    [c + Math.cos(angle(i)) * r * k, c + Math.sin(angle(i)) * r * k] as const;
  const ring = (k: number) => DIMENSIONS.map((_, i) => at(i, k).join(",")).join(" ");

  const shape = DIMENSIONS.map((d, i) => {
    const v = scores[d];
    const k = typeof v === "number" ? Math.max(0.06, Math.min(1, v / 10)) : 0.04;
    return at(i, k).join(",");
  }).join(" ");

  const tone = rating ? TONE[rating] : { fill: "var(--faint)", stroke: "var(--ink-muted)" };
  const summary = DIMENSIONS.map((d) => {
    const v = scores[d];
    return `${SHORT[d]} ${typeof v === "number" ? v.toFixed(1) : "not scored"}`;
  }).join(", ");

  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      width={size}
      height={size}
      role="img"
      aria-label={`Report card shape: ${summary}`}
      className={cn("shrink-0 overflow-visible", className)}
    >
      <g fill="none" stroke="var(--rule)" strokeWidth={1}>
        <polygon points={ring(1)} />
        <polygon points={ring(0.66)} />
        <polygon points={ring(0.33)} />
        {DIMENSIONS.map((_, i) => {
          const [x, y] = at(i, 1);
          return <line key={i} x1={c} y1={c} x2={x} y2={y} />;
        })}
      </g>
      <polygon
        points={shape}
        fill={tone.fill}
        fillOpacity={0.35}
        stroke={tone.stroke}
        strokeWidth={2}
        strokeLinejoin="round"
      />
      {labels &&
        DIMENSIONS.map((d, i) => {
          const [x, y] = at(i, 1.18);
          // Struck only on a real report with a gap; a blank card has nothing missing yet.
          const missing = Boolean(rating) && typeof scores[d] !== "number";
          return (
            <text
              key={d}
              x={x}
              y={y}
              textAnchor={Math.abs(x - c) < 4 ? "middle" : x > c ? "start" : "end"}
              dominantBaseline="middle"
              fontSize={11}
              fontWeight={700}
              fill="var(--ink-muted)"
              textDecoration={missing ? "line-through" : undefined}
              style={{ fontFamily: "var(--font-sans)" }}
            >
              {SHORT[d]}
            </text>
          );
        })}
    </svg>
  );
}
