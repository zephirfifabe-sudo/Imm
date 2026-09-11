import { describe, expect, it } from "vitest";
import { getTranslator } from "./index";

describe("getTranslator", () => {
  it("resolves a nested key", () => {
    const t = getTranslator("fr");
    expect(t("auth.loginTitle")).toBe("Connexion");
  });

  it("interpolates params", () => {
    const t = getTranslator("fr");
    expect(t("dashboard.greeting", { name: "Jean" })).toBe("Bonjour Jean");
  });

  it("falls back to the default locale for an unsupported locale", () => {
    const t = getTranslator("fr");
    expect(t("common.appName")).toBe("KLOCK");
  });
});
