import { describe, expect, it } from "vitest";
import { isAtOrOverEmployeeLimit } from "./limits";

describe("isAtOrOverEmployeeLimit", () => {
  it("does not block when the limit is unknown (no subscription)", () => {
    expect(isAtOrOverEmployeeLimit(500, null)).toBe(false);
  });

  it("allows adding an employee below the limit", () => {
    expect(isAtOrOverEmployeeLimit(9, 10)).toBe(false);
  });

  it("blocks once the current count reaches the limit", () => {
    expect(isAtOrOverEmployeeLimit(10, 10)).toBe(true);
  });

  it("blocks when already over the limit", () => {
    expect(isAtOrOverEmployeeLimit(11, 10)).toBe(true);
  });

  it("blocks a zero-employee limit immediately", () => {
    expect(isAtOrOverEmployeeLimit(0, 0)).toBe(true);
  });
});
