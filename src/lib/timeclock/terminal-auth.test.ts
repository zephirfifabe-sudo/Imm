import { describe, expect, it } from "vitest";
import { generateActivationCode } from "./terminal-auth";

describe("generateActivationCode", () => {
  it("produces a 6-digit numeric code", () => {
    for (let i = 0; i < 20; i++) {
      expect(generateActivationCode()).toMatch(/^\d{6}$/);
    }
  });
});
