/** A five-point trend, drawn small enough to live inside a table row.
 *
 *  Inline SVG rather than a chart library: at 56x14 pixels every part of Recharts is
 *  overhead, and this has to render sixty times on a single tab without cost.
 */
export function Sparkline({
  values,
  width = 56,
  height = 14,
}: {
  values: number[];
  width?: number;
  height?: number;
}) {
  if (values.length < 2) return null;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1);

  const points = values.map((v, i) => {
    const x = i * step;
    const y = height - 2 - ((v - min) / span) * (height - 4);
    return [x, y] as const;
  });

  const d = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  const rising = values[values.length - 1] >= values[0];

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="overflow-visible align-middle"
      role="img"
      aria-label={rising ? "Trending up over five periods" : "Trending down over five periods"}
    >
      <path
        d={d}
        fill="none"
        stroke={rising ? "var(--buy)" : "var(--sell)"}
        strokeWidth="1.25"
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity="0.75"
      />
      <circle
        cx={last[0]}
        cy={last[1]}
        r="1.6"
        fill={rising ? "var(--buy)" : "var(--sell)"}
      />
    </svg>
  );
}
