import "server-only";

/**
 * Correspondance plan KLOCK ↔ Price Stripe. Les Price ID sont créés une
 * seule fois dans le Dashboard Stripe (Produits > Prix) puis renseignés en
 * variables d'environnement — jamais codés en dur ici, pour que changer un
 * prix ne nécessite ni déploiement ni migration.
 */
const STRIPE_PRICE_ENV_BY_PLAN_CODE: Record<string, string | undefined> = {
  STARTER: process.env.STRIPE_PRICE_STARTER,
  PME: process.env.STRIPE_PRICE_PME,
  BUSINESS: process.env.STRIPE_PRICE_BUSINESS,
};

export function getStripePriceIdForPlanCode(planCode: string): string | null {
  return STRIPE_PRICE_ENV_BY_PLAN_CODE[planCode] ?? null;
}

export function getPlanCodeForStripePriceId(priceId: string): string | null {
  for (const [planCode, envPriceId] of Object.entries(STRIPE_PRICE_ENV_BY_PLAN_CODE)) {
    if (envPriceId === priceId) return planCode;
  }
  return null;
}
