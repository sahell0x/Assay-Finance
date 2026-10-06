import { ApiError } from "@/lib/api";

type Suggestion = { ticker: string; name: string };

/** The tickers the API offered when it refused a name typed as a ticker ("APPLE"). */
export function unknownTickerSuggestions(e: unknown): Suggestion[] {
  if (!(e instanceof ApiError) || e.code !== "unknown_ticker") return [];
  const payload = e.payload as { suggestions?: Suggestion[] } | undefined;
  return payload?.suggestions ?? [];
}

/** One click from a refused name to the company the person meant. */
export function DidYouMean({
  suggestions,
  onPick,
}: {
  suggestions: Suggestion[];
  onPick: (ticker: string) => void;
}) {
  if (suggestions.length === 0) return null;
  return (
    <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Did you mean">
      {suggestions.map((s) => (
        <li key={s.ticker}>
          <button
            type="button"
            onClick={() => onPick(s.ticker)}
            className="rounded-full border border-rule bg-surface px-3 py-1 text-small text-muted-foreground transition-colors hover:border-brand hover:text-ink"
          >
            <span className="nums font-medium text-ink">{s.ticker}</span>
            <span className="ml-1.5 text-micro">{s.name}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
