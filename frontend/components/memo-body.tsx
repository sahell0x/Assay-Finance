"use client";

import * as React from "react";

import type { Evidence } from "@/lib/types";

/** Memo prose, with citation markers that go somewhere.
 *
 *  This is the only serif in the product. Everything else is scanned; this is read, and
 *  at 17px on a 66-character measure it reads like a document rather than like an
 *  interface. A `[S3]` marker is a reference, so it scrolls to the source and highlights
 *  it — a citation you cannot follow is decoration.
 */
export function CitedText({
  text,
  evidence,
  onCite,
}: {
  text: string;
  evidence?: Evidence[];
  onCite?: (label: string) => void;
}) {
  const known = React.useMemo(
    () => new Set((evidence ?? []).map((e) => e.label)),
    [evidence],
  );

  const parts = React.useMemo(() => splitCitations(text), [text]);

  return (
    <>
      {parts.map((part, i) =>
        part.type === "cite" ? (
          known.has(part.label) ? (
            <a
              key={i}
              href={`#source-${part.label}`}
              className="cite"
              onClick={(e) => {
                if (onCite) {
                  e.preventDefault();
                  onCite(part.label);
                }
              }}
              title={`Source ${part.label.slice(1)}`}
            >
              [{part.label.slice(1)}]
            </a>
          ) : (
            // A tag with no matching source is shown plainly rather than as a link
            // that goes nowhere.
            <span key={i} className="cite" style={{ color: "var(--ink-muted)" }}>
              [{part.label.slice(1)}]
            </span>
          )
        ) : (
          <React.Fragment key={i}>{part.text}</React.Fragment>
        ),
      )}
    </>
  );
}

type Part = { type: "text"; text: string } | { type: "cite"; label: string };

function splitCitations(text: string): Part[] {
  const parts: Part[] = [];
  const pattern = /\[S(\d{1,2})\]/g;
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) {
      parts.push({ type: "text", text: text.slice(last, match.index) });
    }
    parts.push({ type: "cite", label: `S${match[1]}` });
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push({ type: "text", text: text.slice(last) });
  return parts;
}

export function MemoProse({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`memo-prose ${className}`}>{children}</div>;
}

/** A titled list of claims. Used for drivers, risks, and what would change the view. */
export function ClaimList({
  title,
  items,
  evidence,
  onCite,
  tone,
}: {
  title: string;
  items: string[];
  evidence?: Evidence[];
  onCite?: (label: string) => void;
  tone?: "buy" | "sell";
}) {
  /* The citation enforcer runs in Python and strips sentences it cannot tie to a
     source. When it strips the whole sentence, the markers survive as their own array
     entry, and the list renders a bullet whose entire content is "[S6][S7]" — a rule,
     an indent and two reference numbers attached to nothing. Drop those here: an item
     with no prose left in it is not an item. */
  const visible = (items ?? []).filter((t) => t.replace(/\[S\d{1,2}\]/g, "").trim().length > 0);
  if (!visible.length) return null;

  const markColor =
    tone === "buy"
      ? "var(--buy)"
      : tone === "sell"
        ? "var(--sell)"
        : "var(--rule)";

  return (
    <section className="mt-8">
      <h3 className="mb-3 text-section">{title}</h3>
      <ul className="space-y-3">
        {visible.map((item, i) => (
          <li
            key={i}
            className="memo-prose border-l-2 pl-4"
            style={{ borderColor: markColor, fontSize: "var(--text-lead)", lineHeight: 1.6 }}
          >
            <CitedText text={item} evidence={evidence} onCite={onCite} />
          </li>
        ))}
      </ul>
    </section>
  );
}
