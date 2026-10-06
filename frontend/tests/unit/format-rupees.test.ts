import { describe, expect, it } from "vitest";

import { formatRupees } from "@/lib/format";

describe("formatRupees", () => {
  it("converts paise and drops .00 on whole rupees", () => {
    expect(formatRupees(19900)).toBe("₹199");
    expect(formatRupees(49900)).toBe("₹499");
  });

  it("groups thousands the Indian way", () => {
    expect(formatRupees(149900)).toBe("₹1,499");
    expect(formatRupees(15000000)).toBe("₹1,50,000");
  });

  it("keeps paise on per-credit prices", () => {
    expect(formatRupees(333)).toBe("₹3.33");
    expect(formatRupees(398)).toBe("₹3.98");
  });
});
