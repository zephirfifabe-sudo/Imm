import type { EnergyRating, Location, PropertyType } from "./property";

/** Étendue des travaux estimée à partir de l'analyse photo. */
export type WorkExtent = "léger" | "modéré" | "important";

/** Verdict final présenté à l'utilisateur. */
export type Verdict = "bonne affaire" | "à creuser" | "à éviter";

/** Données soumises par l'utilisateur dans le formulaire d'analyse. */
export interface AnalysisInput {
  propertyType: PropertyType;
  askingPrice: number;
  livingAreaM2?: number;
  location: Location;
  energyRating?: EnergyRating;
  photoUrls: string[];
}

/** Élément détecté par l'IA vision sur une zone du bien. */
export interface DetectedElement {
  zone: string;
  etat: string;
  confiance: number;
}

/** Sortie structurée attendue de l'appel Claude Vision — jamais de texte libre. */
export interface VisionAnalysisResult {
  elements_detectes: DetectedElement[];
  estimation_travaux: WorkExtent;
  budget_travaux_estime_min: number;
  budget_travaux_estime_max: number;
}

/** Résultat du sous-facteur "écart de prix vs marché local". */
export interface PriceFactorResult {
  marketPricePerM2: number;
  askingPricePerM2: number;
  deviationPercent: number;
  points: number;
}

/** Résultat du sous-facteur "impact PEB/DPE". */
export interface EnergyFactorResult {
  energyClass: string | null;
  estimatedRenovationCostMin: number;
  estimatedRenovationCostMax: number;
  points: number;
}

/** Résultat du sous-facteur "étendue des travaux visibles en photo". */
export interface WorkFactorResult {
  extent: WorkExtent;
  points: number;
}

/** Résultat complet, explicite et traçable, du moteur de scoring. */
export interface ScoringResult {
  score: number;
  verdict: Verdict;
  priceFactor: PriceFactorResult;
  energyFactor: EnergyFactorResult;
  workFactor: WorkFactorResult;
}

/** Synthèse textuelle rédigée par le LLM à partir des données déjà calculées (pas des photos). */
export interface SynthesisResult {
  resume: string;
  points_forts: string[];
  points_faibles: string[];
}

/** Enregistrement complet d'une analyse (persistée et affichée en historique). */
export interface AnalysisRecord {
  id: string;
  createdAt: string;
  input: AnalysisInput;
  vision: VisionAnalysisResult;
  scoring: ScoringResult;
  synthesis: SynthesisResult;
}
