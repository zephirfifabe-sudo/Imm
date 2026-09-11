import { describe, expect, it } from "vitest";
import { formatPriceCents } from "./plans";

describe("formatPriceCents", () => {
  it("formats cents as EUR currency", () => {
    expect(formatPriceCents(2900)).toBe("29,00 €");
  });

  it("handles zero", () => {
    expect(formatPriceCents(0)).toBe("0,00 €");
  });
});
