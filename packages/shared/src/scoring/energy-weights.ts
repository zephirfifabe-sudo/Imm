import type { EnergyClass } from "../types/property";

export interface EnergyWeight {
  /** Points retirés du score sur 10 pour cette classe énergétique. */
  penaltyPoints: number;
  /** Fourchette de coût de rénovation énergétique à anticiper (EUR). */
  renovationCostMin: number;
  renovationCostMax: number;
}

/**
 * Grille de pondération PEB/DPE (échelle A→G commune aux deux standards
 * pour ce MVP). Les montants sont des ordres de grandeur pour une maison
 * 3 façades de taille moyenne en Wallonie — à affiner par surface dans une
 * itération future, mais explicites et documentés dès maintenant.
 */
export const ENERGY_WEIGHTS: Record<EnergyClass, EnergyWeight> = {
  A: { penaltyPoints: 0, renovationCostMin: 0, renovationCostMax: 0 },
  B: { penaltyPoints: 0, renovationCostMin: 0, renovationCostMax: 0 },
  C: { penaltyPoints: 0.5, renovationCostMin: 0, renovationCostMax: 3000 },
  D: { penaltyPoints: 1, renovationCostMin: 3000, renovationCostMax: 8000 },
  E: { penaltyPoints: 2, renovationCostMin: 8000, renovationCostMax: 15000 },
  F: { penaltyPoints: 3.5, renovationCostMin: 15000, renovationCostMax: 30000 },
  G: { penaltyPoints: 5, renovationCostMin: 30000, renovationCostMax: 50000 },
};
