import { describe, expect, it } from "vitest";

import { inShort } from "@/components/in-short";
import type { AnalysisDetail, PriceTarget, Scorecard } from "@/lib/types";

function scorecard(overrides: Partial<Scorecard> = {}): Scorecard {
  return {
    dimension_scores: {
      profitability: 8.2,
      financial_health: 6,
      growth: 3.1,
      valuation: 5.5,
      sentiment: 4,
    },
    weights_applied: {},
    dimensions_unavailable: [],
    total: 6.27,
    rating: "HOLD",
    conviction: "medium",
    thresholds: { buy: 7.5, hold: 5 },
    distance_to_edge: 1.2,
    coverage: 1,
    ...overrides,
  };
}

function target(low: number, high: number): PriceTarget {
  return { low, high, mid: (low + high) / 2, method: "peer_multiples", available: true };
}

function analysis(opts: {
  card?: Scorecard | null;
  price?: number | null;
}): AnalysisDetail {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    ticker: "ACME",
    status: "complete",
    scorecard: opts.card === undefined ? scorecard() : opts.card,
    blocks: { market: { name: "Acme Corp", price: opts.price ?? null } },
    evidence: [],
    events: [],
    pipeline: [],
    cached: false,
    owned: true,
  };
}

describe("inShort", () => {
  it("returns null without a scorecard", () => {
    expect(inShort(analysis({ card: null }))).toBeNull();
  });

  it("states the score, verdict and strongest/weakest areas", () => {
    const text = inShort(analysis({ card: scorecard() }))!;
    expect(text).toContain("Acme Corp scores 6.2 out of 10, which makes it a hold.");
    expect(text).toContain("Its strongest area is profitability and its weakest is growth.");
  });

  it("omits the price sentence when there is no price target", () => {
    const text = inShort(analysis({ card: scorecard(), price: 100 }))!;
    expect(text).not.toMatch(/expensive|cheap|fairly priced/);
  });

  it("omits the price sentence when the target is unavailable", () => {
    const card = scorecard({
      price_target: { low: null, high: null, method: "none", available: false },
    });
    const text = inShort(analysis({ card, price: 100 }))!;
    expect(text).not.toMatch(/expensive|cheap|fairly priced/);
  });

  it("says the shares look expensive above the fair value range", () => {
    const card = scorecard({ price_target: target(80, 120) });
    const text = inShort(analysis({ card, price: 150 }))!;
    expect(text).toContain("At $150.00 the shares look expensive");
    expect(text).toContain("worth $80.00 to $120.00");
  });

  it("says the shares look cheap below the fair value range", () => {
    const card = scorecard({ price_target: target(80, 120) });
    const text = inShort(analysis({ card, price: 50 }))!;
    expect(text).toContain("At $50.00 the shares look cheap");
  });

  it("says the shares look fairly priced inside the range", () => {
    const card = scorecard({ price_target: target(80, 120) });
    const text = inShort(analysis({ card, price: 100 }))!;
    expect(text).toContain("the shares look fairly priced");
    expect(text).not.toMatch(/expensive|cheap/);
  });

  it("falls back to the ticker when the company name is missing", () => {
    const a = analysis({ card: scorecard({ rating: "BUY", total: 8 }) });
    a.blocks = null;
    expect(inShort(a)).toMatch(/^ACME scores 8\.0 out of 10, which makes it a buy\./);
  });
});

describe("inShort when the price and the rating disagree", () => {
  it("explains a non-buy on cheap shares by naming the weak areas", () => {
    const card = scorecard({ rating: "SELL", total: 4.99, price_target: target(200, 270) });
    const text = inShort(analysis({ card, price: 128 }))!;
    expect(text).toContain("look cheap");
    expect(text).toContain("Cheap shares alone do not make a buy");
    expect(text).toContain("weak growth and sentiment hold the overall score down");
  });

  it("uses the singular verb for a single weak area", () => {
    const card = scorecard({
      rating: "HOLD",
      price_target: target(200, 270),
      dimension_scores: { profitability: 8, financial_health: 6, growth: 4, valuation: 6, sentiment: 6 },
    });
    expect(inShort(analysis({ card, price: 128 }))).toContain("weak growth holds the overall score down");
  });

  it("adds nothing when price and rating agree", () => {
    const card = scorecard({ rating: "HOLD", price_target: target(100, 150) });
    expect(inShort(analysis({ card, price: 200 }))).not.toContain("Cheap shares alone");
  });
});
