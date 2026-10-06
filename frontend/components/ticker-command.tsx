"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Clock, Loader2, Search, TrendingUp } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Command,
  CommandDialog,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { ApiError, api } from "@/lib/api";
import { formatScore, relativeTime } from "@/lib/format";
import type { AnalysisSummary } from "@/lib/types";

/** Companies offered before anything is typed.
 *
 *  An empty command palette is a dead end, and "start typing" is not a suggestion.
 *  These are the names a visitor is most likely to want, so the first keystroke is
 *  optional rather than required.
 */
const STARTERS = [
  { ticker: "AAPL", name: "Apple" },
  { ticker: "MSFT", name: "Microsoft" },
  { ticker: "NVDA", name: "NVIDIA" },
  { ticker: "AMZN", name: "Amazon" },
  { ticker: "GOOGL", name: "Alphabet" },
  { ticker: "TSLA", name: "Tesla" },
];

export interface TickerCommandController {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  setOpen: (open: boolean) => void;
}

const TickerCommandContext = React.createContext<TickerCommandController | null>(null);

/** The one search in the product.
 *
 *  Any component can call `useTickerCommand().open()` — the header button, the hero
 *  field, an empty state — and they all raise the same dialog. Rendering a palette per
 *  call site would put several dialogs and several ⌘K listeners in one document, and
 *  the shortcut would then toggle whichever one happened to mount last.
 */
export function TickerCommandProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setOpen] = React.useState(false);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const controller = React.useMemo<TickerCommandController>(
    () => ({
      isOpen,
      open: () => setOpen(true),
      close: () => setOpen(false),
      setOpen,
    }),
    [isOpen],
  );

  return (
    <TickerCommandContext.Provider value={controller}>
      {children}
      <TickerCommand controller={controller} />
    </TickerCommandContext.Provider>
  );
}

export function useTickerCommand(): TickerCommandController {
  const ctx = React.useContext(TickerCommandContext);
  if (!ctx) {
    throw new Error("useTickerCommand must be used inside TickerCommandProvider");
  }
  return ctx;
}

function TickerCommand({ controller }: { controller: TickerCommandController }) {
  const router = useRouter();
  const [query, setQuery] = React.useState("");
  const debounced = useDebounced(query, 180);

  const { data: resolution, isFetching } = useQuery({
    queryKey: ["tickers", "resolve", debounced],
    queryFn: () => api.resolveTickers(debounced),
    enabled: controller.isOpen && debounced.trim().length > 0,
    staleTime: 5 * 60_000,
  });
  const suggestions = resolution?.matches ?? [];
  const privateCompany = resolution?.private_company ?? null;

  /** Recent runs belong in the palette: re-opening something already analyzed is the
   *  commonest reason to search, and it costs nothing from the quota. */
  const { data: recent = [] } = useQuery({
    queryKey: ["analyses", { limit: 5 }],
    queryFn: () => api.listAnalyses({ limit: 5 }),
    enabled: controller.isOpen,
    staleTime: 30_000,
  });

  const run = useMutation({
    mutationFn: (ticker: string) => api.runAnalysis({ ticker }),
    onSuccess: (accepted) => {
      controller.close();
      setQuery("");
      router.push(`/analysis/${accepted.id}`);
    },
    onError: (e) =>
      toast.error(
        e instanceof ApiError
          ? e.message
          : "The analysis could not be started. Try again in a moment.",
      ),
  });

  const openAnalysis = (id: string) => {
    controller.close();
    setQuery("");
    router.push(`/analysis/${id}`);
  };

  const typed = query.trim().toUpperCase();
  /** With a query, only recent runs that match it belong in the list: either the
   *  ticker itself was typed, or the company search resolved the name to that ticker
   *  (typing "apple" should still surface a past AAPL run). */
  const matchedTickers = new Set(suggestions.map((s) => s.ticker.toUpperCase()));
  const completedRecent = recent.filter(
    (a: AnalysisSummary) =>
      a.status === "complete" &&
      (typed.length === 0 ||
        a.ticker.toUpperCase().startsWith(typed) ||
        matchedTickers.has(a.ticker.toUpperCase())),
  );

  return (
    <CommandDialog
      open={controller.isOpen}
      onOpenChange={(open) => {
        controller.setOpen(open);
        if (!open) setQuery("");
      }}
      title="Search companies"
      description="Find a company to analyze, or reopen one you have already run."
    >
      {/* shouldFilter={false}: the ticker list is already filtered by the API, and
          cmdk's own fuzzy pass would then hide exact matches the backend returned. */}
      <Command shouldFilter={false}>
      <CommandInput
        placeholder="Company name or ticker, for example Apple or AAPL"
        value={query}
        onValueChange={setQuery}
      />
      <CommandList className="max-h-[22rem]">
        {run.isPending && (
          <div className="flex items-center gap-2 px-4 py-6 text-base text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Starting the analysis
          </div>
        )}

        {!run.isPending && (
          <>
            {/* A plain block, not CommandEmpty: cmdk only shows its empty slot when the
                list has no items at all, so a matching recent run would hide this. */}
            {typed.length > 0 && privateCompany && !isFetching && (
              <div className="px-4 py-6 text-base text-muted-foreground">
                <p className="font-medium text-ink">
                  {privateCompany} is a private company.
                </p>
                <p className="mt-1">
                  It isn&rsquo;t on the stock market and doesn&rsquo;t publish the
                  financial reports we use, so it can&rsquo;t be analyzed.
                </p>
              </div>
            )}

            {typed.length > 0 && !privateCompany && suggestions.length === 0 && !isFetching && (
              <div className="px-4 py-6 text-base text-muted-foreground">
                No company on the stock market matches &ldquo;{query.trim()}&rdquo;.
                It may be private, or spelled differently. Ticker symbols work too.
              </div>
            )}

            {suggestions.length > 0 && (
              <CommandGroup heading="Companies">
                {suggestions.map((s, i) => (
                  <CommandItem
                    key={`${s.ticker}-${i}`}
                    value={`${s.ticker}-${i}`}
                    onSelect={() => run.mutate(s.ticker)}
                  >
                    <Search className="size-3.5 text-muted-foreground" />
                    <span className="nums w-16 shrink-0 font-medium text-ink">
                      {s.ticker}
                    </span>
                    <span className="truncate text-muted-foreground">{s.name}</span>
                    {s.exchange && (
                      <span className="ml-auto shrink-0 text-micro text-muted-foreground">
                        {s.exchange}
                      </span>
                    )}
                  </CommandItem>
                ))}
              </CommandGroup>
            )}

            {typed.length === 0 && (
              <CommandGroup heading="Popular">
                {STARTERS.map((s) => (
                  <CommandItem
                    key={s.ticker}
                    value={s.ticker}
                    onSelect={() => run.mutate(s.ticker)}
                  >
                    <TrendingUp className="size-3.5 text-muted-foreground" />
                    <span className="nums w-16 shrink-0 font-medium text-ink">
                      {s.ticker}
                    </span>
                    <span className="text-muted-foreground">{s.name}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}

            {completedRecent.length > 0 && (
              <>
                <CommandSeparator />
                <CommandGroup heading="Your recent analyses">
                  {completedRecent.map((a) => (
                    <CommandItem
                      key={a.id}
                      value={`recent-${a.id}`}
                      onSelect={() => openAnalysis(a.id)}
                    >
                      <Clock className="size-3.5 text-muted-foreground" />
                      <span className="nums w-16 shrink-0 font-medium text-ink">
                        {a.ticker}
                      </span>
                      <span className="text-muted-foreground">
                        {a.rating ?? "—"} {formatScore(a.total_score)}
                      </span>
                      <span className="ml-auto shrink-0 text-micro text-muted-foreground">
                        {relativeTime(a.completed_at ?? a.created_at)}
                      </span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}
          </>
        )}
      </CommandList>
      </Command>
    </CommandDialog>
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
