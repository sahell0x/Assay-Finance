import { describe, expect, it } from "vitest";

import { unknownTickerSuggestions } from "@/components/did-you-mean";
import { ApiError } from "@/lib/api";

const suggestions = [{ ticker: "AAPL", name: "Apple Inc." }];

describe("unknownTickerSuggestions", () => {
  it("returns the suggestions for an unknown_ticker ApiError", () => {
    const e = new ApiError(422, "APPLE is not a stock ticker", "unknown_ticker", {
      suggestions,
    });
    expect(unknownTickerSuggestions(e)).toEqual(suggestions);
  });

  it("returns an empty list when the payload has none", () => {
    expect(unknownTickerSuggestions(new ApiError(422, "x", "unknown_ticker"))).toEqual([]);
  });

  it("ignores other ApiError codes", () => {
    const e = new ApiError(429, "out", "quota_exhausted", { suggestions });
    expect(unknownTickerSuggestions(e)).toEqual([]);
  });

  it("ignores plain errors and non-errors", () => {
    expect(unknownTickerSuggestions(new Error("boom"))).toEqual([]);
    expect(unknownTickerSuggestions({ code: "unknown_ticker", payload: { suggestions } })).toEqual([]);
    expect(unknownTickerSuggestions(undefined)).toEqual([]);
  });
});
