/** Formatting.
 *
 *  One module, because a number formatted two different ways in two places is how a
 *  financial interface loses trust. Everything that renders a figure comes through here,
 *  including chart axes and tooltips.
 */

import type { MetricValue, Unit } from "./types";

export const DASH = "—";

export function formatValue(value: number | null | undefined, unit: Unit): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  switch (unit) {
    case "percent":
      return `${(value * 100).toFixed(1)}%`;
    case "x":
      return `${value.toFixed(2)}x`;
    case "days":
      return `${Math.round(value)}d`;
    case "currency":
      return formatCurrency(value);
    case "score":
      return value.toFixed(1);
    default:
      return value.toFixed(2);
  }
}

export function formatMetric(m: MetricValue): string {
  return formatValue(m.value, m.unit);
}

/** Abbreviated currency. Never a raw float — "$1.2B", not "1234567890.0". */
export function formatCurrency(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(decimals)}T`;
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(decimals)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(2)}`;
}

/** Full precision with thousands separators, for the derivation ledger where the
 *  point is to show the exact input. */
export function formatExact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  if (Number.isInteger(value)) return value.toLocaleString("en-US");
  if (Math.abs(value) < 1) return value.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatSigned(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  const pct = value * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(digits)}%`;
}

/** A score to one decimal, truncated rather than rounded.
 *
 *  The rating cut-offs are 5.0 and 7.5. Rounding put a 4.97 on screen as "5.0" beside a
 *  Sell rating and a scale reading "Hold: 5 to 7.5". Truncating keeps every displayed
 *  score on the same side of each cut-off as the real one. */
export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return (Math.floor(value * 10 + 1e-9) / 10).toFixed(1);
}

export function formatPercentile(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  return `p${Math.round(value * 100)}`;
}

/** UTC, always — for two reasons, both of which produce wrong days rather than
 *  merely surprising ones.
 *
 *  These dates are server-rendered. Left to the runtime's own zone, the server (a
 *  container on UTC) and the browser (wherever the reader is) disagree about which day
 *  a near-midnight timestamp falls on, and React discards the whole server-rendered
 *  subtree with a hydration mismatch.
 *
 *  The second reason outlives any hydration fix: a date-only string such as an SEC
 *  filing's "2025-10-31" parses as UTC midnight, so every reader west of UTC was shown
 *  the filing as a day earlier than it is. The dates here are facts about filings and
 *  analysis runs, not appointments in the reader's day, so pinning the zone is what
 *  they mean in the first place.
 */
const DATE_ZONE = "UTC";

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return DASH;
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: DATE_ZONE,
  });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return DASH;
  return d.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: DATE_ZONE,
    timeZoneName: "short",
  });
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return DASH;
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(iso);
}

/** Human labels for source types. Users read "10-K risk factors", not "sec_10k". */
export const SOURCE_LABELS: Record<string, string> = {
  sec_10k: "Annual report",
  sec_10q: "Quarterly report",
  yf_news: "News",
  rss: "Newswire",
};

export function sourceLabel(t: string): string {
  return SOURCE_LABELS[t] ?? t;
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function sentenceCase(s: string): string {
  const spaced = s.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Rupees from paise, the unit Razorpay works in: 49900 -> "₹499", 333 -> "₹3.33". */
export function formatRupees(paise: number): string {
  const rupees = paise / 100;
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: Number.isInteger(rupees) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(rupees);
}
