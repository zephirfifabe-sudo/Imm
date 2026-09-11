/**
 * Catalogue des plans affiché avant chargement depuis la base (page marketing,
 * état de secours). La source de vérité pour la facturation reste la table
 * `plans` en base — ces valeurs ne doivent jamais être utilisées pour calculer
 * un prix facturé, uniquement pour l'affichage statique (ex: landing page).
 */
export const PLAN_CATALOG = [
  { code: "STARTER", name: "Starter", priceCents: 2900, maxEmployees: 10 },
  { code: "PME", name: "PME", priceCents: 4900, maxEmployees: 25 },
  { code: "BUSINESS", name: "Business", priceCents: 8900, maxEmployees: 50 },
] as const;

export function formatPriceCents(priceCents: number, locale = "fr-BE") {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "EUR",
  }).format(priceCents / 100);
}
