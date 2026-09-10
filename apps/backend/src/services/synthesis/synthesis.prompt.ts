import type { AnalysisInput, ScoringResult, VisionAnalysisResult } from "@previsite/shared";

export const SYNTHESIS_SYSTEM_PROMPT = `Tu es un rédacteur qui explique en français, de façon claire, neutre et
professionnelle, le résultat d'une pré-analyse immobilière destinée à un particulier en Belgique. Le score et le
verdict te sont déjà donnés et calculés par des règles explicites : tu ne dois JAMAIS les recalculer, les
contredire, ni inventer de nouvelles données chiffrées. Tu expliques pourquoi, en t'appuyant uniquement sur les
données fournies. Rappelle en une phrase que cet outil ne remplace pas l'avis d'un expert immobilier.
Réponds EXCLUSIVEMENT en appelant l'outil "write_synthesis" fourni.`;

export function buildSynthesisUserPrompt(
  input: AnalysisInput,
  vision: VisionAnalysisResult,
  scoring: ScoringResult,
): string {
  return `Données de l'analyse (déjà calculées, ne pas recalculer) :

Bien : ${input.propertyType} à ${input.location.commune} (${input.location.postalCode}), ${input.livingAreaM2 ?? "surface non renseignée"} m².
Prix demandé : ${input.askingPrice.toLocaleString("fr-BE")} €.
Score final : ${scoring.score}/10 — verdict : "${scoring.verdict}".

Facteur prix : prix marché estimé ${scoring.priceFactor.marketPricePerM2} €/m², écart de ${scoring.priceFactor.deviationPercent}% (${scoring.priceFactor.points} points).
Facteur énergie : classe ${scoring.energyFactor.energyClass ?? "non renseignée"}, coût de rénovation énergétique estimé entre ${scoring.energyFactor.estimatedRenovationCostMin} et ${scoring.energyFactor.estimatedRenovationCostMax} € (${scoring.energyFactor.points} points).
Facteur travaux visibles en photo : étendue "${scoring.workFactor.extent}" (${scoring.workFactor.points} points), budget travaux estimé entre ${vision.budget_travaux_estime_min} et ${vision.budget_travaux_estime_max} €.
Éléments détectés en photo : ${vision.elements_detectes.map((e) => `${e.zone} (${e.etat})`).join(", ") || "aucun détail spécifique"}.

Rédige un résumé de 3 à 5 phrases expliquant ce verdict, puis liste les points forts et les points faibles (2 à 4 chacun).`;
}

export const WRITE_SYNTHESIS_TOOL = {
  name: "write_synthesis",
  description: "Enregistre la synthèse textuelle structurée de l'analyse.",
  input_schema: {
    type: "object" as const,
    properties: {
      resume: { type: "string", description: "3 à 5 phrases expliquant le verdict." },
      points_forts: { type: "array", items: { type: "string" } },
      points_faibles: { type: "array", items: { type: "string" } },
    },
    required: ["resume", "points_forts", "points_faibles"],
  },
};
