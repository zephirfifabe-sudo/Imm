export const VISION_SYSTEM_PROMPT = `Tu es un assistant technique qui aide à préparer une visite immobilière en Belgique.
Tu analyses des photos d'un bien (extérieur, cuisine, salle de bain, pièces principales, toiture si visible)
et tu évalues UNIQUEMENT l'état général visible : cuisine/salle de bain datées, sols, peintures, fenêtres,
toiture visible. Tu ne fais AUCUN diagnostic d'humidité, de structure, ou de désordre caché — ce n'est pas
ton rôle et tu n'as pas l'information pour ça.

Tu dois répondre EXCLUSIVEMENT en appelant l'outil "report_visual_condition" fourni, avec un JSON structuré.
Ne réponds jamais en texte libre. Si une photo est ambiguë ou de mauvaise qualité, indique une confiance basse
plutôt que d'inventer un état.`;

export function buildVisionUserPrompt(photoCount: number): string {
  return `Voici ${photoCount} photo(s) d'un bien immobilier. Identifie les zones visibles (cuisine, salle de bain,
sols, peinture, fenêtres, toiture, façade, etc.), évalue leur état ("bon état apparent", "à rafraîchir",
"à rénover"), indique ta confiance (0 à 1) pour chaque zone, puis donne une estimation globale de l'étendue
des travaux ("léger", "modéré", "important") et une fourchette de budget travaux en euros, cohérente avec le
marché belge de la rénovation.`;
}

export const REPORT_VISUAL_CONDITION_TOOL = {
  name: "report_visual_condition",
  description:
    "Enregistre l'analyse structurée de l'état visuel du bien à partir des photos fournies.",
  input_schema: {
    type: "object" as const,
    properties: {
      elements_detectes: {
        type: "array",
        items: {
          type: "object",
          properties: {
            zone: { type: "string", description: "Ex: cuisine, salle de bain, toiture, façade, sols" },
            etat: {
              type: "string",
              description: "Ex: bon état apparent, à rafraîchir, à rénover",
            },
            confiance: { type: "number", minimum: 0, maximum: 1 },
          },
          required: ["zone", "etat", "confiance"],
        },
      },
      estimation_travaux: {
        type: "string",
        enum: ["léger", "modéré", "important"],
      },
      budget_travaux_estime_min: { type: "number", minimum: 0 },
      budget_travaux_estime_max: { type: "number", minimum: 0 },
    },
    required: [
      "elements_detectes",
      "estimation_travaux",
      "budget_travaux_estime_min",
      "budget_travaux_estime_max",
    ],
  },
};
