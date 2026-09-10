import type { PropertyType } from "../types/property";
import { STATBEL_MOCK_PRICES, STATBEL_NATIONAL_FALLBACK } from "./statbel-mock-data";

export interface MarketPriceLookupResult {
  pricePerM2: number;
  /** false si on est retombé sur la moyenne nationale faute de donnée locale. */
  isLocalMatch: boolean;
}

/**
 * Recherche le prix moyen au m² pour une commune et un type de bien donnés.
 * Recherche par code postal en priorité (plus fiable qu'un nom saisi
 * librement), puis par nom de commune en repli, puis moyenne nationale.
 */
export function lookupMarketPricePerM2(
  postalCode: string,
  commune: string,
  propertyType: PropertyType,
): MarketPriceLookupResult {
  const byPostalCode = STATBEL_MOCK_PRICES.find((entry) => entry.postalCode === postalCode);
  if (byPostalCode) {
    return { pricePerM2: byPostalCode.pricePerM2[propertyType], isLocalMatch: true };
  }

  const normalizedCommune = commune.trim().toLowerCase();
  const byCommune = STATBEL_MOCK_PRICES.find(
    (entry) => entry.commune.toLowerCase() === normalizedCommune,
  );
  if (byCommune) {
    return { pricePerM2: byCommune.pricePerM2[propertyType], isLocalMatch: true };
  }

  return { pricePerM2: STATBEL_NATIONAL_FALLBACK[propertyType], isLocalMatch: false };
}
