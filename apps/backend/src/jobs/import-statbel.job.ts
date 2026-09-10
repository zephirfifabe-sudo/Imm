/**
 * Job d'import périodique des données ouvertes Statbel (prix moyen au m²
 * par commune / trimestre).
 *
 * Statbel ne propose pas d'API temps réel simple pour ces statistiques —
 * pour ce MVP, `packages/shared/src/market/statbel-mock-data.ts` sert de
 * cache local en dur pour un échantillon de communes wallonnes.
 *
 * Ce script est le point d'extension prévu pour la suite : télécharger le
 * fichier ouvert Statbel (ex. export CSV des transactions immobilières par
 * commune), le parser, et regénérer `statbel-mock-data.ts` (ou une table
 * `MarketPrice` en base) avec les vraies valeurs — sans changer l'API
 * `lookupMarketPricePerM2()` utilisée par le moteur de scoring.
 *
 * Non branché sur un cron pour l'instant : à exécuter manuellement
 * (`tsx src/jobs/import-statbel.job.ts`) une fois la source de données
 * exacte confirmée.
 */
import { logger } from "../utils/logger";

async function run() {
  logger.warn(
    "Import Statbel non implémenté pour ce MVP : le scoring utilise le cache local " +
      "packages/shared/src/market/statbel-mock-data.ts. Voir le commentaire en tête de ce fichier.",
  );
}

run();
