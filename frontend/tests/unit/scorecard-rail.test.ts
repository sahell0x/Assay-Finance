import { describe, expect, it } from "vitest";

import { THRESHOLDS, grade } from "@/components/scorecard-rail";

describe("grade", () => {
  it("uses the rating cut-offs", () => {
    expect(THRESHOLDS).toEqual({ buy: 7.5, hold: 5 });
  });

  it.each([
    [10, "Strong"],
    [7.5, "Strong"],
    [7.49, "Average"],
    [5, "Average"],
    [4.99, "Weak"],
    [0, "Weak"],
  ])("grades %s as %s", (score, word) => {
    expect(grade(score, THRESHOLDS).word).toBe(word);
  });
});
