/** Nombre d'analyses gratuites offertes à vie par compte (pas par jour). */
export const FREE_ANALYSES_PER_ACCOUNT = 3;

/** Packs de crédits proposés à l'achat (id Stripe Price à configurer côté backend). */
export const CREDIT_PACKS = [
  { id: "pack-5", label: "5 analyses", credits: 5, priceCents: 990 },
  { id: "pack-15", label: "15 analyses", credits: 15, priceCents: 2490 },
] as const;

export const DISCLAIMER_TEXT =
  "PréVisite donne une première indication objective pour t'aider à filtrer les biens qui ne valent clairement pas le déplacement. Cet outil ne remplace pas l'avis d'un expert immobilier : avant tout achat, fais réaliser les expertises et diagnostics nécessaires.";
