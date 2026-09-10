import { describe, expect, it } from "vitest";
import { computeScoring } from "../scoring-engine";
import type { VisionAnalysisResult } from "../../types/analysis";

function makeVision(overrides: Partial<VisionAnalysisResult> = {}): VisionAnalysisResult {
  return {
    elements_detectes: [],
    estimation_travaux: "léger",
    budget_travaux_estime_min: 0,
    budget_travaux_estime_max: 0,
    ...overrides,
  };
}

describe("computeScoring", () => {
  it("donne un score maximal (10) pour un bien au prix marché, bonne classe énergie, aucun travaux", () => {
    const result = computeScoring({
      propertyType: "maison",
      askingPrice: 2100 * 100, // == prix marché Namur pour 100m²
      livingAreaM2: 100,
      postalCode: "5000",
      commune: "Namur",
      energyClass: "A",
      vision: makeVision({ estimation_travaux: "léger" }),
    });

    // léger travaux retire 0.5 point même dans le meilleur des cas
    expect(result.score).toBeCloseTo(9.5, 5);
    expect(result.verdict).toBe("bonne affaire");
  });

  it("pénalise un prix largement au-dessus du marché", () => {
    const result = computeScoring({
      propertyType: "maison",
      askingPrice: 2100 * 100 * 1.5, // +50% vs marché
      livingAreaM2: 100,
      postalCode: "5000",
      commune: "Namur",
      vision: makeVision({ estimation_travaux: "léger" }),
    });

    expect(result.priceFactor.deviationPercent).toBeCloseTo(50, 5);
    // capé à -3 points malgré un écart de 50%
    expect(result.priceFactor.points).toBe(-3);
  });

  it("bonifie un prix nettement sous le marché", () => {
    const result = computeScoring({
      propertyType: "maison",
      askingPrice: 2100 * 100 * 0.8, // -20% vs marché
      livingAreaM2: 100,
      postalCode: "5000",
      commune: "Namur",
      vision: makeVision({ estimation_travaux: "léger" }),
    });

    expect(result.priceFactor.deviationPercent).toBeCloseTo(-20, 5);
    expect(result.priceFactor.points).toBe(2);
  });

  it("applique la pénalité PEB/DPE classe G et son estimation de rénovation", () => {
    const result = computeScoring({
      propertyType: "maison",
      askingPrice: 210000,
      livingAreaM2: 100,
      postalCode: "5000",
      commune: "Namur",
      energyClass: "G",
      vision: makeVision({ estimation_travaux: "léger" }),
    });

    expect(result.energyFactor.points).toBe(-5);
    expect(result.energyFactor.estimatedRenovationCostMin).toBe(30000);
    expect(result.energyFactor.estimatedRenovationCostMax).toBe(50000);
  });

  it("applique la pénalité travaux 'important'", () => {
    const result = computeScoring({
      propertyType: "appartement",
      askingPrice: 260000,
      livingAreaM2: 100,
      postalCode: "5000",
      commune: "Namur",
      vision: makeVision({ estimation_travaux: "important" }),
    });

    expect(result.workFactor.points).toBe(-4);
  });

  it("ne pénalise pas le prix quand la surface n'est pas renseignée", () => {
    const result = computeScoring({
      propertyType: "maison",
      askingPrice: 999999,
      postalCode: "5000",
      commune: "Namur",
      vision: makeVision({ estimation_travaux: "léger" }),
    });

    expect(result.priceFactor.points).toBe(0);
  });

  it("retombe sur le prix national quand la commune est inconnue", () => {
    const result = computeScoring({
      propertyType: "maison",
      askingPrice: 190000,
      livingAreaM2: 100,
      postalCode: "9999",
      commune: "Commune Inconnue",
      vision: makeVision({ estimation_travaux: "léger" }),
    });

    expect(result.priceFactor.marketPricePerM2).toBe(1900);
  });

  it("borne le score final entre 0 et 10 dans le pire des cas", () => {
    const result = computeScoring({
      propertyType: "maison",
      askingPrice: 500000,
      livingAreaM2: 50,
      postalCode: "6000",
      commune: "Charleroi",
      energyClass: "G",
      vision: makeVision({ estimation_travaux: "important" }),
    });

    expect(result.score).toBeGreaterThanOrEqual(0);
    expect(result.verdict).toBe("à éviter");
  });

  it("classe correctement les seuils de verdict", () => {
    // 250000 / 100m² = 2500 €/m², marché Namur maison = 2100 €/m² => +19% (~ -1.9 pt)
    // classe D (-1 pt) + travaux modérés (-2 pt) => score ≈ 5.1 => "à creuser"
    expect(
      computeScoring({
        propertyType: "maison",
        askingPrice: 250000,
        livingAreaM2: 100,
        postalCode: "5000",
        commune: "Namur",
        energyClass: "D",
        vision: makeVision({ estimation_travaux: "modéré" }),
      }).verdict,
    ).toBe("à creuser");
  });
});
