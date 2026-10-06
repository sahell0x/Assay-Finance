"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { X } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import {
  DidYouMean,
  unknownTickerSuggestions,
} from "@/components/did-you-mean";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { ApiError, api } from "@/lib/api";
import { DIMENSIONS, DIMENSION_LABELS } from "@/lib/types";

const DEFAULT_WEIGHTS: Record<string, number> = {
  profitability: 0.25,
  financial_health: 0.2,
  growth: 0.25,
  valuation: 0.2,
  sentiment: 0.1,
};

export function AnalyzeForm() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [ticker, setTicker] = React.useState("");
  const [peerInput, setPeerInput] = React.useState("");
  const [peers, setPeers] = React.useState<string[]>([]);
  const [peerError, setPeerError] = React.useState<string | null>(null);
  const [weights, setWeights] = React.useState(DEFAULT_WEIGHTS);
  const [customWeights, setCustomWeights] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [didYouMean, setDidYouMean] = React.useState<
    { ticker: string; name: string }[]
  >([]);

  const { data: usage } = useQuery({
    queryKey: ["usage"],
    queryFn: api.usage,
    retry: false,
  });
  const outOfCredits = Boolean(usage?.exhausted || usage?.budget?.exhausted);

  const { data: suggestions = [] } = useQuery({
    queryKey: ["tickers", ticker],
    queryFn: () => api.searchTickers(ticker),
    enabled: ticker.length > 0,
    staleTime: 5 * 60_000,
  });

  const peerQuery = peerInput.trim();
  const { data: peerSuggestions = [] } = useQuery({
    queryKey: ["tickers", peerQuery],
    queryFn: () => api.searchTickers(peerQuery),
    enabled: peerQuery.length > 0,
    staleTime: 5 * 60_000,
  });

  const run = useMutation({
    mutationFn: (symbol: string) =>
      api.runAnalysis({
        ticker: symbol,
        peer_tickers: peers,
        weights: customWeights ? weights : undefined,
      }),
    onSuccess: (res) => router.push(`/analysis/${res.id}`),
    onError: (e) => {
      setDidYouMean(unknownTickerSuggestions(e));
      // Out of credits or paused for the day: the notice above the button says so
      // with a way forward, so a second red line saying the same thing is dropped.
      if (
        e instanceof ApiError &&
        (e.code === "quota_exhausted" || e.code === "budget_exhausted")
      ) {
        queryClient.invalidateQueries({ queryKey: ["usage"] });
        setError(null);
        return;
      }
      setError(
        e instanceof ApiError
          ? e.message
          : "The analysis could not be started. Try again in a moment.",
      );
    },
  });

  /** Only real tickers become peers. A name like "GOOGLE" is not one, and a peer that
   *  cannot be found leaves the valuation with nothing to compare against. */
  const addPeer = async (value: string) => {
    const clean = value.trim().toUpperCase();
    if (!clean || peers.includes(clean) || peers.length >= 8) return;
    let matches: { ticker: string; name: string }[] = [];
    try {
      matches = await queryClient.fetchQuery({
        queryKey: ["tickers", clean],
        queryFn: () => api.searchTickers(clean),
        staleTime: 5 * 60_000,
      });
    } catch {
      setPeerError("Could not check that ticker. Try again in a moment.");
      return;
    }
    if (!matches.some((m) => m.ticker === clean)) {
      setPeerError(
        matches.length
          ? `${clean} is not a ticker. Pick one of the suggestions below.`
          : `No company found for ${clean}. Try its ticker symbol, like GOOGL for Alphabet.`,
      );
      return;
    }
    setPeerError(null);
    setPeers([...peers, clean]);
    setPeerInput("");
  };

  const total = Object.values(weights).reduce((a, b) => a + b, 0);

  return (
    <form
      className="grid max-w-[62rem] gap-10 lg:grid-cols-[minmax(0,1fr)_20rem]"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        if (!ticker.trim()) {
          setError("Enter a ticker symbol to analyze.");
          return;
        }
        setDidYouMean([]);
        run.mutate(ticker.trim().toUpperCase());
      }}
    >
      <div className="space-y-8">
        <section>
          <label htmlFor="ticker" className="text-base font-medium">
            Company
          </label>
          <p className="mb-2 mt-0.5 text-small text-muted-foreground">
            Type a company name or its stock ticker, then pick it from the list.
            Any company listed on a US stock exchange works.
          </p>
          <Input
            id="ticker"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="e.g. Apple or AAPL"
            className="nums max-w-[18rem] uppercase placeholder:normal-case"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
          />
          {ticker.length > 0 && suggestions.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {suggestions.slice(0, 5).map((s) => (
                <li key={s.ticker}>
                  <button
                    type="button"
                    onClick={() => setTicker(s.ticker)}
                    className="rounded-full border border-rule bg-surface px-3 py-1 text-small text-muted-foreground transition-colors hover:border-brand hover:text-ink"
                  >
                    <span className="nums">{s.ticker}</span>
                    <span className="ml-1.5 text-micro">{s.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <label htmlFor="peers" className="text-base font-medium">
            Companies to compare against{" "}
            <span className="font-normal text-muted-foreground">
              (optional)
            </span>
          </label>
          <p className="mb-2 mt-0.5 max-w-[54ch] text-small leading-relaxed text-muted-foreground">
            Up to eight competitors. Leave this empty and we pick similar
            companies from the same industry for you.
          </p>
          <div className="flex max-w-[22rem] gap-2">
            <Input
              id="peers"
              value={peerInput}
              onChange={(e) => {
                setPeerInput(e.target.value.toUpperCase());
                setPeerError(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === ",") {
                  e.preventDefault();
                  addPeer(peerInput);
                }
              }}
              placeholder="e.g. Microsoft or MSFT"
              className="nums uppercase placeholder:normal-case"
              autoComplete="off"
              disabled={peers.length >= 8}
            />
            <Button
              type="button"
              variant="outline"
              onClick={() => addPeer(peerInput)}
              disabled={peers.length >= 8}
            >
              Add
            </Button>
          </div>

          {peerError && (
            <p role="alert" className="mt-2 text-small text-sell">
              {peerError}
            </p>
          )}

          {peerQuery.length > 0 && peerSuggestions.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {peerSuggestions
                .filter((sug) => !peers.includes(sug.ticker))
                .slice(0, 5)
                .map((sug) => (
                  <li key={sug.ticker}>
                    <button
                      type="button"
                      onClick={() => addPeer(sug.ticker)}
                      className="rounded-full border border-rule bg-surface px-3 py-1 text-small text-muted-foreground transition-colors hover:border-brand hover:text-ink"
                    >
                      <span className="nums">{sug.ticker}</span>
                      <span className="ml-1.5 text-micro">{sug.name}</span>
                    </button>
                  </li>
                ))}
            </ul>
          )}

          {peers.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {peers.map((p) => (
                <li key={p}>
                  <button
                    type="button"
                    onClick={() => setPeers(peers.filter((x) => x !== p))}
                    className="flex items-center gap-1.5 rounded-full border border-rule bg-surface py-1 pl-2 pr-1.5 text-small"
                    aria-label={`Remove ${p}`}
                  >
                    <span className="nums">{p}</span>
                    <X
                      size={11}
                      className="text-muted-foreground"
                      aria-hidden
                    />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <div className="flex items-baseline justify-between gap-4">
            <span className="text-base font-medium">
              What matters most to you{" "}
              <span className="font-normal text-muted-foreground">
                (optional)
              </span>
            </span>
            <button
              type="button"
              className="text-small text-primary hover:underline"
              onClick={() => {
                setCustomWeights(!customWeights);
                if (customWeights) setWeights(DEFAULT_WEIGHTS);
              }}
            >
              {customWeights ? "Use the standard mix" : "Adjust"}
            </button>
          </div>
          <p className="mb-4 mt-0.5 max-w-[54ch] text-small leading-relaxed text-muted-foreground">
            How much each area counts toward the overall score and the buy, hold
            or sell rating. The defaults suit most people.
          </p>

          {!customWeights ? (
            <p className="text-small text-ink-soft">
              {DIMENSIONS.map(
                (d) =>
                  `${DIMENSION_LABELS[d]} ${Math.round(DEFAULT_WEIGHTS[d] * 100)}%`,
              ).join(", ")}
            </p>
          ) : (
            <div className="space-y-4">
              {DIMENSIONS.map((dim) => (
                <div
                  key={dim}
                  className="grid grid-cols-[9.5rem_1fr_3rem] items-center gap-4"
                >
                  <label
                    htmlFor={`w-${dim}`}
                    className="text-small text-ink-soft"
                  >
                    {DIMENSION_LABELS[dim]}
                  </label>
                  <Slider
                    id={`w-${dim}`}
                    value={[weights[dim] * 100]}
                    min={0}
                    max={60}
                    step={5}
                    disabled={!customWeights}
                    onValueChange={([v]) =>
                      setWeights({ ...weights, [dim]: v / 100 })
                    }
                    aria-label={`${DIMENSION_LABELS[dim]} weight`}
                  />
                  <span className="nums text-right text-small text-muted-foreground">
                    {Math.round((weights[dim] / (total || 1)) * 100)}%
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        {error && (
          <div>
            <p role="alert" className="text-base text-sell">
              {error}
            </p>
            <DidYouMean
              suggestions={didYouMean}
              onPick={(t) => {
                setTicker(t);
                setError(null);
                setDidYouMean([]);
              }}
            />
          </div>
        )}

        {outOfCredits && (
          <div
            role="status"
            className="rounded-xl border border-hold/30 bg-hold-wash p-4"
          >
            <p className="text-base font-semibold text-ink">
              {usage?.budget?.exhausted
                ? "New analyses are paused for today"
                : "You have no credits left"}
            </p>
            <p className="mt-1 text-base leading-relaxed text-ink-soft">
              {usage?.budget?.exhausted
                ? "Today's limit has been reached. It resets at midnight UTC. Anything already analyzed still opens, and recently analyzed companies are free."
                : usage?.authenticated
                  ? usage.can_buy
                    ? "You have used the free credits that came with your account. Buy a credit pack to keep going. Companies analyzed recently by anyone are still free to open."
                    : "You have used all the credits available on this account, including the test-mode purchase limit. Companies analyzed recently by anyone are still free to open, and everything you have analyzed still opens."
                  : `Create a free account to get ${usage?.account_free_credits ?? 10} more free credits. Everything you have analyzed comes with you.`}
            </p>
            {!usage?.authenticated && !usage?.budget?.exhausted && (
              <Button asChild className="mt-3">
                <a href="/signup">Create a free account</a>
              </Button>
            )}
            {usage?.authenticated && !usage.budget?.exhausted && (
              <Button asChild className="mt-3" variant={usage.can_buy ? "default" : "outline"}>
                <Link href="/credits">{usage.can_buy ? "Buy credits" : "See your usage"}</Link>
              </Button>
            )}
          </div>
        )}

        <div className="flex items-center gap-3">
          <Button
            type="submit"
            variant="default"
            size="lg"
            disabled={run.isPending}
          >
            {run.isPending ? "Starting the analysis" : "Run the analysis"}
          </Button>
          <span className="text-small text-muted-foreground">
            Takes about two minutes and uses 1 credit.
          </span>
        </div>
      </div>

      <aside className="panel h-fit p-5">
        <h2 className="text-base font-medium">What happens next</h2>
        <ol className="mt-3 list-decimal space-y-2.5 pl-4 text-small leading-relaxed text-muted-foreground marker:text-muted-foreground">
          <li>
            We read the company&rsquo;s latest official financial reports.
          </li>
          <li>
            We calculate around forty measures of profit, debt, growth and
            value.
          </li>
          <li>We compare them with similar companies in the same industry.</li>
          <li>
            We read recent filings and news for what the numbers point to.
          </li>
          <li>
            The company gets a score out of 10 and a buy, hold or sell rating,
            using the same fixed rules for every company.
          </li>
          <li>
            You get a written summary where every claim links to its source, so
            you can check it yourself.
          </li>
        </ol>
      </aside>
    </form>
  );
}
