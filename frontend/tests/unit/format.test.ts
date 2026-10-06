import { describe, expect, it } from "vitest";

import { DASH, formatScore } from "@/lib/format";

describe("formatScore", () => {
  it("truncates to one decimal rather than rounding", () => {
    expect(formatScore(4.97)).toBe("4.9");
    expect(formatScore(7.49)).toBe("7.4");
    expect(formatScore(4.99)).toBe("4.9");
  });

  it("pads whole numbers to one decimal", () => {
    expect(formatScore(5)).toBe("5.0");
    expect(formatScore(0)).toBe("0.0");
    expect(formatScore(10)).toBe("10.0");
  });

  it("keeps exact tenths intact despite float error", () => {
    expect(formatScore(7.5)).toBe("7.5");
    expect(formatScore(0.3)).toBe("0.3");
  });

  it("shows the dash for missing values", () => {
    expect(formatScore(null)).toBe(DASH);
    expect(formatScore(undefined)).toBe(DASH);
    expect(formatScore(Number.NaN)).toBe(DASH);
  });
});
