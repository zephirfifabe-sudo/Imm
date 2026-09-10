import type { PropertyType } from "../types/property";
import type {
  EnergyFactorResult,
  PriceFactorResult,
  ScoringResult,
  Verdict,
  VisionAnalysisResult,
  WorkFactorResult,
} from "../types/analysis";
import { lookupMarketPricePerM2 } from "../market/market-data";
import { ENERGY_WEIGHTS } from "./energy-weights";
import { WORK_EXTENT_PENALTY } from "./work-weights";

export interface ScoringInput {
  propertyType: PropertyType;
  askingPrice: number;
  livingAreaM2?: number;
  postalCode: string;
  commune: string;
  energyClass?: string;
  vision: VisionAnalysisResult;
}

const SCORE_MIN = 0;
const SCORE_MAX = 10;

/** Poids maximal (en points sur 10) que l'écart de prix peut faire varier, dans chaque sens. */
const PRICE_POINTS_CAP = 3;
/** Chaque tranche de 10% d'écart au marché vaut 1 point. */
const PRICE_PERCENT_PER_POINT = 10;

const VERDICT_THRESHOLDS: { min: number; verdict: Verdict }[] = [
  { min: 7, verdict: "bonne affaire" },
  { min: 4.5, verdict: "à creuser" },
  { min: SCORE_MIN, verdict: "à éviter" },
];

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

/**
 * Facteur 1 — écart de prix vs marché local.
 *
 * Nécessite la surface habitable pour calculer un prix/m² demandé.
 * Sans surface connue, le facteur est neutre (0 point) : on ne pénalise
 * pas un bien pour une donnée que l'utilisateur n'a pas renseignée.
 */
function computePriceFactor(input: ScoringInput): PriceFactorResult {
  const { pricePerM2: marketPricePerM2 } = lookupMarketPricePerM2(
    input.postalCode,
    input.commune,
    input.propertyType,
  );

  if (!input.livingAreaM2 || input.livingAreaM2 <= 0) {
    return { marketPricePerM2, askingPricePerM2: 0, deviationPercent: 0, points: 0 };
  }

  const askingPricePerM2 = input.askingPrice / input.livingAreaM2;
  const deviationPercent = ((askingPricePerM2 - marketPricePerM2) / marketPricePerM2) * 100;

  // Prix plus cher que le marché (déviation positive) => points négatifs.
  // Prix plus bas que le marché (déviation négative) => points positifs.
  const rawPoints = -deviationPercent / PRICE_PERCENT_PER_POINT;
  const points = clamp(rawPoints, -PRICE_POINTS_CAP, PRICE_POINTS_CAP);

  return {
    marketPricePerM2,
    askingPricePerM2: round1(askingPricePerM2),
    deviationPercent: round1(deviationPercent),
    points: round1(points),
  };
}

/**
 * Facteur 2 — impact de la classe PEB/DPE sur le prix "juste".
 * Grille de pondération explicite dans `energy-weights.ts`.
 */
function computeEnergyFactor(input: ScoringInput): EnergyFactorResult {
  const energyClass = input.energyClass ?? null;
  const weight = energyClass && energyClass in ENERGY_WEIGHTS
    ? ENERGY_WEIGHTS[energyClass as keyof typeof ENERGY_WEIGHTS]
    : null;

  if (!weight) {
    return {
      energyClass,
      estimatedRenovationCostMin: 0,
      estimatedRenovationCostMax: 0,
      points: 0,
    };
  }

  return {
    energyClass,
    estimatedRenovationCostMin: weight.renovationCostMin,
    estimatedRenovationCostMax: weight.renovationCostMax,
    points: round1(-weight.penaltyPoints),
  };
}

/**
 * Facteur 3 — étendue des travaux détectée par l'IA vision.
 * Grille de pondération explicite dans `work-weights.ts`.
 */
function computeWorkFactor(vision: VisionAnalysisResult): WorkFactorResult {
  const penalty = WORK_EXTENT_PENALTY[vision.estimation_travaux];
  return { extent: vision.estimation_travaux, points: round1(-penalty) };
}

function resolveVerdict(score: number): Verdict {
  const match = VERDICT_THRESHOLDS.find((threshold) => score >= threshold.min);
  return match ? match.verdict : "à éviter";
}

/**
 * Formule de scoring — explicite, déterministe, indépendante du LLM.
 *
 *   score = 10 + pointsPrix + pointsEnergie + pointsTravaux   (borné à [0, 10])
 *
 * - pointsPrix ∈ [-3, 3] : ±1 point par tranche de 10% d'écart au prix marché.
 * - pointsEnergie ∈ [-5, 0] : pénalité fixe par classe PEB/DPE (voir energy-weights.ts).
 * - pointsTravaux ∈ [-4, -0.5] : pénalité fixe par étendue de travaux détectée en photo.
 *
 * Voir docs/scoring-formula.md pour la justification produit de ces bornes.
 * Le LLM de synthèse (services/synthesis) reçoit ce résultat déjà calculé :
 * il rédige un texte, il ne décide jamais du score.
 */
export function computeScoring(input: ScoringInput): ScoringResult {
  const priceFactor = computePriceFactor(input);
  const energyFactor = computeEnergyFactor(input);
  const workFactor = computeWorkFactor(input.vision);

  const rawScore = SCORE_MAX + priceFactor.points + energyFactor.points + workFactor.points;
  const score = round1(clamp(rawScore, SCORE_MIN, SCORE_MAX));

  return {
    score,
    verdict: resolveVerdict(score),
    priceFactor,
    energyFactor,
    workFactor,
  };
}
