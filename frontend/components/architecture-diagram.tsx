/** How a run actually works, drawn.
 *
 *  Inline SVG on the same tokens as everything else, so it reads as part of the product
 *  rather than as an image pasted into it. The shape carries the argument: the
 *  quantitative stages feed the retrieval (which is why retrieval can interrogate what
 *  the numbers found), and the rubric — not the model — reaches the rating.
 */
export function ArchitectureDiagram({ className = "" }: { className?: string }) {
  /* Tokens, not hex. SVG presentation attributes are CSS values, so the diagram
     follows the theme with no re-render — which is the rule everywhere else in this
     product and was the one place it had been broken: these were five literals from
     the old cool palette, so the diagram stayed blue-grey on a bone page and did not
     respond to dark mode at all. */
  const ink = "var(--ink)";
  const muted = "var(--ink-muted)";
  const rule = "var(--rule)";
  const accent = "var(--brand)";
  const wash = "var(--brand-wash)";
  const surface = "var(--surface)";

  const box = (
    x: number,
    y: number,
    w: number,
    h: number,
    label: string,
    sub?: string,
    emphasis = false,
  ) => (
    <g key={`${x}-${y}-${label}`}>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx="3"
        fill={emphasis ? wash : surface}
        stroke={emphasis ? accent : rule}
        strokeWidth={emphasis ? 1.5 : 1}
      />
      <text
        x={x + w / 2}
        y={sub ? y + h / 2 - 4 : y + h / 2 + 4}
        textAnchor="middle"
        fontSize="11.5"
        fontWeight={emphasis ? 600 : 500}
        fill={ink}
      >
        {label}
      </text>
      {sub && (
        <text
          x={x + w / 2}
          y={y + h / 2 + 11}
          textAnchor="middle"
          fontSize="9.5"
          fill={muted}
        >
          {sub}
        </text>
      )}
    </g>
  );

  const arrow = (x1: number, y1: number, x2: number, y2: number, dashed = false) => (
    <line
      key={`${x1}-${y1}-${x2}-${y2}`}
      x1={x1}
      y1={y1}
      x2={x2}
      y2={y2}
      stroke={rule}
      strokeWidth="1.25"
      strokeDasharray={dashed ? "3 3" : undefined}
      markerEnd="url(#arrowhead)"
    />
  );

  return (
    <svg
      viewBox="0 0 900 330"
      className={`h-auto w-full ${className}`}
      role="img"
      aria-label="Architecture: the browser posts a ticker to the API, which queues a job; an ARQ worker runs a ten-node LangGraph pipeline whose quantitative stages feed a retrieval stage, then a deterministic rubric sets the rating and a language model writes the memo, which is verified before it is stored; progress streams back over server-sent events."
    >
      <defs>
        <marker
          id="arrowhead"
          markerWidth="7"
          markerHeight="7"
          refX="6"
          refY="2.5"
          orient="auto"
        >
          <path d="M0,0 L6,2.5 L0,5 Z" fill={rule} />
        </marker>
      </defs>

      {/* --- request path --- */}
      {box(8, 20, 120, 42, "Browser", "ticker in")}
      {arrow(132, 41, 176, 41)}
      {box(180, 20, 130, 42, "FastAPI", "202 with a job id")}
      {arrow(314, 41, 358, 41)}
      {box(362, 20, 120, 42, "Redis queue")}
      {arrow(486, 41, 530, 41)}
      {box(534, 20, 130, 42, "ARQ worker", "one job at a time")}

      {/* --- progress path back --- */}
      {arrow(534, 52, 314, 52, true)}
      <text x="400" y="72" fontSize="9.5" fill={muted} textAnchor="middle">
        node events over Redis pub/sub
      </text>
      <line x1="180" y1="55" x2="128" y2="55" stroke={rule} strokeWidth="1.25" strokeDasharray="3 3" markerEnd="url(#arrowhead)" />
      <text x="152" y="74" fontSize="9.5" fill={muted} textAnchor="middle">
        SSE
      </text>

      {/* --- the pipeline --- */}
      <rect x="8" y="100" width="884" height="150" rx="4" fill="none" stroke={rule} strokeDasharray="4 3" />
      <text x="20" y="117" fontSize="10" fontWeight="500" fill={muted}>
        LangGraph pipeline
      </text>

      {box(20, 128, 118, 46, "Ingest", "yfinance, aliases")}
      {arrow(142, 151, 166, 151)}
      {box(170, 128, 190, 46, "Profitability, liquidity, growth", "pure Python ratios")}
      {arrow(364, 151, 388, 151)}
      {box(392, 128, 118, 46, "Peers", "percentile ranks")}
      {arrow(514, 151, 538, 151)}
      {box(542, 128, 150, 46, "Retrieve evidence", "pgvector over filings")}

      {/* the coupling that makes retrieval targeted */}
      <path
        d="M265,178 C265,206 617,206 617,180"
        fill="none"
        stroke={accent}
        strokeWidth="1.25"
        strokeDasharray="3 3"
        markerEnd="url(#arrowhead)"
      />
      <text x="441" y="222" fontSize="10" fill={accent} textAnchor="middle">
        weak ratios add targeted queries
      </text>

      {box(720, 128, 160, 46, "Scorecard", "fixed rubric sets the rating", true)}
      {arrow(800, 178, 800, 200)}
      {box(720, 204, 160, 40, "Memo writer", "argues the given rating")}

      {/* --- output --- */}
      {arrow(720, 224, 676, 224)}
      {box(510, 204, 160, 40, "Verifier", "regex every figure")}
      {arrow(510, 224, 466, 224)}
      {box(300, 204, 160, 40, "Postgres", "result and evidence")}
      {arrow(300, 224, 256, 224)}
      {box(96, 204, 156, 40, "Memo, cited")}

      <text x="8" y="282" fontSize="10" fill={muted}>
        Every figure on the page is computed in the pure-Python stages. The model
        interprets them; it never calculates one.
      </text>
      <text x="8" y="300" fontSize="10" fill={muted}>
        The rating is produced by the scorecard before the memo is written, so the memo
        argues a decision it cannot change.
      </text>
      <text x="8" y="318" fontSize="10" fill={muted}>
        Qualitative sentences without a valid source tag are stripped in Python before
        the memo is stored.
      </text>
    </svg>
  );
}
