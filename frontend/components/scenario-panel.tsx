"use client";

import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { BandRule } from "@/components/band-rule";
import { Badge, ratingTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { DASH, formatValue } from "@/lib/format";
import {
  DIMENSIONS,
  DIMENSION_LABELS,
  type Rating,
  type ScenarioLever,
  type ScenarioPath,
  type ScenarioSetup,
  type Unit,
} from "@/lib/types";

/** What-if over a finished analysis.
 *
 *  The rating comes from a rubric rather than from a model, and the useful consequence
 *  of that — the one this panel exists to expose — is that the rubric runs *backwards*.
 *  It can be asked what would have to be true for the answer to change, and it can
 *  answer exactly, because the answer is arithmetic.
 *
 *  Two halves, and the left one is the point. "What would have to be true" solves each
 *  metric for the smallest move that crosses a band; the sliders on the right then let
 *  the reader disbelieve the answer and check it. Applying a route moves the slider to
 *  the solved value, so the claim and the demonstration are the same control.
 *
 *  Every number here is computed by the same ``scoring.py`` that produced the stored
 *  card — the panel holds no copy of the anchor tables, which is why it cannot drift
 *  from the memo it sits next to. The round trip costs a database read and a fold over
 *  five dimensions; there is no queue, no quota and no model call behind any of it.
 */

const UNIT_MAP: Record<ScenarioLever["unit"], Unit> = {
  pct: "percent",
  x: "x",
  ratio: "ratio",
  score: "score",
  currency: "currency",
};

function formatLever(value: number | null, unit: ScenarioLever["unit"]): string {
  return formatValue(value, UNIT_MAP[unit]);
}

const TARGETS: Rating[] = ["BUY", "HOLD", "SELL"];

/** Two decimals, everywhere in this panel.
 *
 *  The rest of the interface scores to one, which is the right resolution for reading a
 *  result. Here the reader is watching a composite cross a line at 7.50, and at one
 *  decimal a 7.415 and a 7.503 both render as "7.4" and "7.5" while the delta between
 *  them prints as +0.09 — three figures that visibly fail to add up. */
function score2(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return value.toFixed(2);
}

/** Round to the slider's own step, so a dragged value and a solved value are comparable
 *  and a float never renders as 0.30000000000000004. */
function quantise(value: number, step: number): number {
  const decimals = Math.max(0, Math.ceil(-Math.log10(step)) + 1);
  return Number((Math.round(value / step) * step).toFixed(decimals));
}

function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = React.useState(value);
  React.useEffect(() => {
    const id = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return settled;
}

export function ScenarioPanel({ analysisId }: { analysisId: string }) {
  const [target, setTarget] = React.useState<Rating | null>(null);
  const [overrides, setOverrides] = React.useState<Record<string, number>>({});

  // The sliders track the pointer; the request follows a beat behind. Without this a
  // drag posts a request per pixel, and with too much of it the numbers feel detached
  // from the handle.
  const committed = useDebounced(overrides, 120);

  const { data: setup, isLoading } = useQuery({
    queryKey: ["scenario-setup", analysisId, target],
    queryFn: () => api.scenarioSetup(analysisId, target ?? undefined),
    staleTime: Infinity,
  });

  const dirty = Object.keys(committed).length > 0;
  const { data: result } = useQuery({
    queryKey: ["scenario-run", analysisId, committed],
    queryFn: () => api.runScenario(analysisId, { overrides: committed }),
    enabled: dirty,
    // Keep the previous answer on screen while the next one is in flight, so a drag
    // reads as a value changing rather than as a panel emptying and refilling.
    placeholderData: (prev) => prev,
    staleTime: Infinity,
  });

  if (isLoading || !setup) {
    return <div className="py-16 text-center text-sm text-muted-foreground">Loading…</div>;
  }

  const baseline = setup.baseline;
  const live = dirty && result ? result : null;
  const total = live ? live.total : baseline.total;
  const rating = (live ? live.rating : baseline.rating) as Rating;
  const moved = live !== null && live.total !== baseline.total;
  // Taken between the values as *displayed*, not between the values as held. Rounding
  // three figures independently lets 7.42 + 0.09 print next to a total of 7.50, and a
  // panel whose own arithmetic visibly fails to add up has no business asserting that
  // the rest of the product's does.
  const delta =
    moved && total !== null && baseline.total !== null
      ? Number((Number(total.toFixed(2)) - Number(baseline.total.toFixed(2))).toFixed(2))
      : null;
  const deltaWorthShowing = delta !== null && Math.abs(delta) >= 0.005;

  const priceTarget = live?.price_target ?? baseline.price_target ?? null;
  const leversByName = new Map(setup.levers.map((l) => [l.name, l]));

  const apply = (path: ScenarioPath) => {
    if (path.to === null) return;
    const lever = leversByName.get(path.lever);
    // Exactly the one move the route claims, not merged onto whatever was already set —
    // a route is a statement about a single metric and has to be checkable as one.
    setOverrides({ [path.lever]: lever ? quantise(path.to, lever.step) : path.to });
  };

  return (
    <div className="space-y-5 py-5">
      {/* ------------------------------------------------------------ the result */}
      <section className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-baseline gap-3">
              <Badge tone={ratingTone(rating)}>{rating}</Badge>
              <span className="nums text-2xl font-medium text-ink">{score2(total)}</span>
              {deltaWorthShowing && delta !== null && (
                <span
                  className={cn(
                    "nums text-sm",
                    delta > 0 ? "text-[var(--buy)]" : "text-[var(--sell)]",
                  )}
                >
                  {delta > 0 ? "+" : ""}
                  {delta.toFixed(2)}
                </span>
              )}
            </div>
            <p className="mt-1 text-micro text-muted-foreground">
              {moved ? (
                <>
                  The real analysis scored {score2(baseline.total)} ({baseline.rating}). The
                  hollow marker on the scale shows where it actually landed.
                </>
              ) : (
                <>
                  This is the real result. Move the sliders below to see how the score and
                  rating would change if the numbers were different. Nothing is saved.
                </>
              )}
            </p>
          </div>

          {dirty && (
            <Button variant="outline" size="sm" onClick={() => setOverrides({})}>
              Reset
            </Button>
          )}
        </div>

        <div className="mt-5">
          <BandRule
            total={total}
            ghost={moved ? baseline.total : null}
            thresholds={setup.thresholds}
            rating={rating}
          />
        </div>

        <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-rule-soft pt-4 sm:grid-cols-3 lg:grid-cols-5">
          {DIMENSIONS.map((dim) => {
            const before = baseline.dimension_scores?.[dim] ?? null;
            const after = live ? (live.dimension_scores?.[dim] ?? null) : before;
            const changed = after !== null && before !== null && after !== before;
            return (
              <div key={dim}>
                <dt className="text-micro text-muted-foreground">{DIMENSION_LABELS[dim]}</dt>
                <dd className="mt-0.5 flex items-baseline gap-1.5">
                  <span className="nums text-sm text-ink">{score2(after)}</span>
                  {changed && (
                    <span className="nums text-micro text-muted-foreground">
                      was {score2(before)}
                    </span>
                  )}
                </dd>
              </div>
            );
          })}
        </dl>

        {priceTarget?.available && (
          <p className="mt-4 max-w-[68ch] border-t border-rule-soft pt-4 text-micro text-muted-foreground">
            Fair value {formatValue(priceTarget.mid ?? null, "currency")}
            {priceTarget.implied_move !== null && priceTarget.implied_move !== undefined && (
              <>
                , implying {priceTarget.implied_move >= 0 ? "a rise of " : "a fall of "}
                {Math.abs(priceTarget.implied_move * 100).toFixed(1)}%
                {live?.price_scenario ? " against the scenario price" : " against the current price"}
              </>
            )}
            . The fair value comes from how the market values similar companies, so
            changing the share price changes the gap to it, not the fair value itself.
          </p>
        )}
      </section>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <ThresholdRoutes
          setup={setup}
          target={target ?? setup.target_rating}
          onTarget={setTarget}
          onApply={apply}
          applied={Object.keys(committed)}
        />
        <Levers
          levers={setup.levers}
          overrides={overrides}
          onChange={(name, value) => setOverrides((o) => ({ ...o, [name]: value }))}
          onClear={(name) =>
            setOverrides((o) => {
              const next = { ...o };
              delete next[name];
              return next;
            })
          }
        />
      </div>
    </div>
  );
}

/* ------------------------------------------------------- what would have to be true */

function ThresholdRoutes({
  setup,
  target,
  onTarget,
  onApply,
  applied,
}: {
  setup: ScenarioSetup;
  target: Rating;
  onTarget: (r: Rating) => void;
  onApply: (p: ScenarioPath) => void;
  applied: string[];
}) {
  const reachable = setup.paths.filter((p) => p.reachable);
  const blocked = setup.paths.length - reachable.length;

  return (
    <section className="panel self-start p-5 lg:sticky lg:top-6">
      <h3 className="text-base font-medium text-ink">What would have to be true</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        The smallest change to a single number that would turn this into a{" "}
        <span className="text-ink">{target}</span>, if everything else stayed the same.
      </p>

      <div className="mt-3 flex gap-1.5">
        {TARGETS.filter((r) => r !== setup.baseline.rating).map((r) => (
          <Button
            key={r}
            size="sm"
            variant={r === target ? "secondary" : "ghost"}
            onClick={() => onTarget(r)}
          >
            {r}
          </Button>
        ))}
      </div>

      {reachable.length === 0 ? (
        <p className="mt-5 border-t border-rule-soft pt-4 text-sm text-ink">
          No single number can do this on its own. The score is{" "}
          <span className="nums">
            {setup.baseline.distance_to_edge?.toFixed(2) ?? DASH}
          </span>{" "}
          points away from that rating, so several things would have to change together.
        </p>
      ) : (
        <ul className="mt-4 divide-y divide-rule-soft border-t border-rule-soft">
          {reachable.map((p) => {
            const isApplied = applied.length === 1 && applied[0] === p.lever;
            return (
              <li key={p.lever} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm text-ink">{p.label}</p>
                  <p className="nums mt-0.5 text-micro text-muted-foreground">
                    {formatLever(p.from, p.unit)}
                    <span className="mx-1.5 text-muted-foreground">to</span>
                    <span className="text-ink">{formatLever(p.to, p.unit)}</span>
                  </p>
                </div>
                <Button
                  size="sm"
                  variant={isApplied ? "secondary" : "outline"}
                  onClick={() => onApply(p)}
                >
                  {isApplied ? "Applied" : "Show me"}
                </Button>
              </li>
            );
          })}
        </ul>
      )}

      {blocked > 0 && (
        <p className="mt-4 text-micro text-muted-foreground">
          {blocked} other {blocked === 1 ? "number" : "numbers"} could not reach {target}{" "}
          on {blocked === 1 ? "its" : "their"} own, however much {blocked === 1 ? "it changed" : "they changed"}.
        </p>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------------- the levers */

function Levers({
  levers,
  overrides,
  onChange,
  onClear,
}: {
  levers: ScenarioLever[];
  overrides: Record<string, number>;
  onChange: (name: string, value: number) => void;
  onClear: (name: string) => void;
}) {
  // The share price comes first and on its own: it is the one number everybody already
  // has an opinion about, and the easiest way into the rest.
  const grouped = [
    { dimension: "share_price", levers: levers.filter((l) => l.name === "share_price") },
    ...DIMENSIONS.map((dim) => ({
      dimension: dim,
      levers: levers.filter((l) => l.dimension === dim && l.name !== "share_price"),
    })),
  ].filter((g) => g.levers.length > 0);

  return (
    <section className="panel p-5">
      <h3 className="text-base font-medium text-ink">Try different numbers</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        Drag a slider to change one number and watch the score update. Changing the
        share price also changes every valuation measure that depends on it.
      </p>

      <div className="mt-4 space-y-5">
        {grouped.map((group) => (
          <div key={group.dimension}>
            <h4 className="border-b border-rule-soft pb-1.5 text-micro font-medium text-ink-soft">
              {group.dimension === "share_price"
                ? "Share price"
                : DIMENSION_LABELS[group.dimension]}
            </h4>
            <div className="mt-3 grid gap-x-6 gap-y-3.5 xl:grid-cols-2">
              {group.levers.map((lever) => {
                const current = overrides[lever.name] ?? lever.value;
                const changed = lever.name in overrides;
                return (
                  <div key={lever.name}>
                    <div className="flex items-baseline justify-between gap-2">
                      <label
                        htmlFor={`lever-${lever.name}`}
                        className="truncate text-sm text-ink-soft"
                      >
                        {lever.label}
                      </label>
                      <span className="flex shrink-0 items-baseline gap-1.5">
                        {changed && (
                          <button
                            type="button"
                            onClick={() => onClear(lever.name)}
                            className="text-micro text-muted-foreground underline underline-offset-2"
                          >
                            reset
                          </button>
                        )}
                        {changed && (
                          <span className="nums text-micro text-muted-foreground line-through">
                            {formatLever(lever.value, lever.unit)}
                          </span>
                        )}
                        <span
                          className={cn(
                            "nums text-sm",
                            changed ? "text-ink" : "text-muted-foreground",
                          )}
                        >
                          {formatLever(current, lever.unit)}
                        </span>
                      </span>
                    </div>
                    <Slider
                      id={`lever-${lever.name}`}
                      aria-label={lever.label}
                      className="mt-2"
                      min={lever.min}
                      max={lever.max}
                      step={lever.step}
                      value={[current]}
                      onValueChange={([v]) => onChange(lever.name, v)}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
