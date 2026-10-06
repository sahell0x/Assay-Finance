"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import * as React from "react";

import { DidYouMean, unknownTickerSuggestions } from "@/components/did-you-mean";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/cn";

/** Ticker input with autocomplete, used on the landing page and the analyze page.
 *
 *  The suggestion list is keyboard-navigable because a search box you have to reach for
 *  the mouse to use is a search box that slows down the person who types fastest.
 */
export function TickerLauncher({
  size = "md",
  autoFocus = false,
  onRunStart,
}: {
  size?: "md" | "lg";
  autoFocus?: boolean;
  onRunStart?: () => void;
}) {
  const router = useRouter();
  const [value, setValue] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const [cursor, setCursor] = React.useState(-1);
  const [error, setError] = React.useState<string | null>(null);
  const [didYouMean, setDidYouMean] = React.useState<{ ticker: string; name: string }[]>([]);
  const boxRef = React.useRef<HTMLDivElement>(null);

  const debounced = useDebounced(value, 180);

  const { data: suggestions = [] } = useQuery({
    queryKey: ["tickers", debounced],
    queryFn: () => api.searchTickers(debounced),
    enabled: open,
    staleTime: 5 * 60_000,
  });

  const run = useMutation({
    mutationFn: (ticker: string) => api.runAnalysis({ ticker }),
    onMutate: () => {
      setError(null);
      setDidYouMean([]);
      onRunStart?.();
    },
    onSuccess: (accepted) => router.push(`/analysis/${accepted.id}`),
    onError: (e) => {
      setDidYouMean(unknownTickerSuggestions(e));
      setError(
        e instanceof ApiError
          ? e.message
          : "The analysis could not be started. Try again in a moment.",
      );
    },
  });

  React.useEffect(() => {
    const onClickAway = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickAway);
    return () => document.removeEventListener("mousedown", onClickAway);
  }, []);

  const submit = (ticker: string) => {
    const clean = ticker.trim().toUpperCase();
    if (!clean) {
      setError("Enter a ticker symbol to analyze.");
      return;
    }
    setOpen(false);
    run.mutate(clean);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, -1));
    } else if (e.key === "Enter" && cursor >= 0) {
      e.preventDefault();
      submit(suggestions[cursor].ticker);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div ref={boxRef} className="relative w-full max-w-[32rem]">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(cursor >= 0 ? suggestions[cursor].ticker : value);
        }}
        className="flex gap-2"
      >
        <div className="relative flex-1">
          <Input
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              setOpen(true);
              setCursor(-1);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={onKeyDown}
            placeholder="Company or ticker"
            aria-label="Ticker symbol"
            aria-autocomplete="list"
            aria-expanded={open}
            autoFocus={autoFocus}
            autoCapitalize="characters"
            autoComplete="off"
            spellCheck={false}
            className={cn(
              "nums uppercase",
              size === "lg" && "h-11 text-lead",
            )}
            disabled={run.isPending}
          />
        </div>
        <Button
          type="submit"
          variant="default"
          size={size === "lg" ? "xl" : "default"}
          disabled={run.isPending}
        >
          {run.isPending ? "Starting" : "Analyze"}
        </Button>
      </form>

      {open && suggestions.length > 0 && (
        <ul
          role="listbox"
          className="absolute left-0 right-0 top-full z-30 mt-1 max-h-72 overflow-auto rounded-md border border-rule bg-surface py-1 shadow-float"
        >
          {suggestions.map((s, i) => (
            <li key={`${s.ticker}-${i}`}>
              <button
                type="button"
                role="option"
                aria-selected={i === cursor}
                onMouseEnter={() => setCursor(i)}
                onClick={() => submit(s.ticker)}
                className={cn(
                  "flex w-full items-baseline gap-3 px-3 py-1.5 text-left",
                  i === cursor && "bg-brand-wash",
                )}
              >
                <span className="nums w-14 shrink-0 text-base font-medium text-ink">
                  {s.ticker}
                </span>
                <span className="truncate text-small text-muted-foreground">
                  {s.name}
                </span>
                {s.exchange && (
                  <span className="ml-auto shrink-0 text-micro text-muted-foreground">
                    {s.exchange}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && (
        <p role="alert" className="mt-2 text-small text-sell">
          {error}
        </p>
      )}
      <DidYouMean
        suggestions={didYouMean}
        onPick={(t) => {
          setValue(t);
          submit(t);
        }}
      />
    </div>
  );
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}
