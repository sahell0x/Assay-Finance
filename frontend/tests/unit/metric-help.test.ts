import { describe, expect, it } from "vitest";

import { METRIC_HELP } from "@/lib/metric-help";

describe("METRIC_HELP", () => {
  const entries = Object.entries(METRIC_HELP);

  it("has entries", () => {
    expect(entries.length).toBeGreaterThan(0);
  });

  it.each(entries)("%s is a non-empty sentence ending in a period", (_key, text) => {
    expect(typeof text).toBe("string");
    expect(text.trim().length).toBeGreaterThan(0);
    expect(text.trim().endsWith(".")).toBe(true);
  });
});
