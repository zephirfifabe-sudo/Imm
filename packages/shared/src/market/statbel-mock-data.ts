import type { PropertyType } from "../types/property";

/**
 * Jeu de données de démarrage pour le MVP : prix moyen au m² par commune,
 * estimé à partir des statistiques trimestrielles Statbel (transactions
 * immobilières) pour un échantillon de communes wallonnes.
 *
 * Ceci N'EST PAS un appel temps réel à Statbel : c'est un cache local,
 * volontairement réduit pour ce sprint. Le format est conçu pour être
 * remplacé, sans changer l'API du `MarketDataProvider`, par un import
 * périodique du jeu de données ouvertes complet (voir
 * apps/backend/src/jobs/import-statbel.job.ts).
 *
 * Prix indicatifs (EUR/m²), ordre de grandeur 2024, à réactualiser lors du
 * branchement des vraies données.
 */
export interface CommunePriceEntry {
  commune: string;
  postalCode: string;
  pricePerM2: Record<PropertyType, number>;
}

export const STATBEL_MOCK_PRICES: CommunePriceEntry[] = [
  {
    commune: "Namur",
    postalCode: "5000",
    pricePerM2: { maison: 2100, appartement: 2600, studio: 2800, terrain: 180 },
  },
  {
    commune: "Liège",
    postalCode: "4000",
    pricePerM2: { maison: 1850, appartement: 2300, studio: 2500, terrain: 150 },
  },
  {
    commune: "Charleroi",
    postalCode: "6000",
    pricePerM2: { maison: 1300, appartement: 1700, studio: 1850, terrain: 90 },
  },
  {
    commune: "Mons",
    postalCode: "7000",
    pricePerM2: { maison: 1600, appartement: 1950, studio: 2100, terrain: 110 },
  },
  {
    commune: "Tournai",
    postalCode: "7500",
    pricePerM2: { maison: 1700, appartement: 2000, studio: 2150, terrain: 120 },
  },
  {
    commune: "Wavre",
    postalCode: "1300",
    pricePerM2: { maison: 2700, appartement: 3100, studio: 3300, terrain: 260 },
  },
  {
    commune: "Arlon",
    postalCode: "6700",
    pricePerM2: { maison: 2300, appartement: 2650, studio: 2800, terrain: 190 },
  },
  {
    commune: "Verviers",
    postalCode: "4800",
    pricePerM2: { maison: 1250, appartement: 1600, studio: 1750, terrain: 85 },
  },
];

/** Prix moyen national utilisé en repli lorsque la commune n'est pas encore couverte. */
export const STATBEL_NATIONAL_FALLBACK: Record<PropertyType, number> = {
  maison: 1900,
  appartement: 2350,
  studio: 2500,
  terrain: 160,
};
