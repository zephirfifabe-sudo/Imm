import { z } from "zod";

export const propertyTypeSchema = z.enum(["maison", "appartement", "studio", "terrain"]);

export const energyClassSchema = z.enum(["A", "B", "C", "D", "E", "F", "G"]);

export const energyRatingSchema = z.object({
  standard: z.enum(["PEB", "DPE"]),
  energyClass: energyClassSchema,
});

export const locationSchema = z.object({
  commune: z.string().min(2, "Indique la commune du bien."),
  postalCode: z
    .string()
    .regex(/^\d{4,5}$/, "Code postal invalide (4 chiffres en Belgique, 5 en France)."),
  countryCode: z.enum(["BE", "FR"]),
});

/**
 * Schéma du formulaire d'analyse, partagé entre l'app mobile (validation avant envoi)
 * et le backend (validation à la réception) — une seule source de vérité.
 */
export const analysisInputSchema = z.object({
  propertyType: propertyTypeSchema,
  askingPrice: z
    .number({ invalid_type_error: "Le prix demandé doit être un nombre." })
    .positive("Le prix demandé doit être supérieur à 0."),
  livingAreaM2: z.number().positive("La surface doit être supérieure à 0.").optional(),
  location: locationSchema,
  energyRating: energyRatingSchema.optional(),
  photoUrls: z
    .array(z.string())
    .min(1, "Ajoute au moins une photo du bien pour lancer l'analyse."),
});

export type AnalysisInputPayload = z.infer<typeof analysisInputSchema>;

export const detectedElementSchema = z.object({
  zone: z.string(),
  etat: z.string(),
  confiance: z.number().min(0).max(1),
});

/**
 * Schéma de la réponse attendue de l'IA vision. Toute réponse qui ne
 * valide pas ce schéma est rejetée — pas de texte libre non structuré.
 */
export const visionAnalysisResultSchema = z.object({
  elements_detectes: z.array(detectedElementSchema),
  estimation_travaux: z.enum(["léger", "modéré", "important"]),
  budget_travaux_estime_min: z.number().nonnegative(),
  budget_travaux_estime_max: z.number().nonnegative(),
});

/** Schéma de la synthèse rédigée par le LLM final — structurée, pas de texte libre non balisé. */
export const synthesisResultSchema = z.object({
  resume: z.string().min(1),
  points_forts: z.array(z.string()),
  points_faibles: z.array(z.string()),
});

export const registerSchema = z.object({
  email: z.string().email("Adresse email invalide."),
  password: z.string().min(8, "Le mot de passe doit contenir au moins 8 caractères."),
  fullName: z.string().min(2, "Indique ton nom complet.").optional(),
});

export const loginSchema = z.object({
  email: z.string().email("Adresse email invalide."),
  password: z.string().min(1, "Mot de passe requis."),
});
