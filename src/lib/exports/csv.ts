import { EXPORT_COLUMNS, type ExportRow } from "@/lib/exports/rows";

// Séparateur ";" plutôt que "," (hors RFC 4180 mais volontaire): un Excel
// en locale FR/NL/BE — le marché cible de KLOCK — attend ";" comme séparateur
// de liste par défaut à l'ouverture directe d'un .csv, sinon tout finit dans
// une seule colonne malgré le BOM.
const DELIMITER = ";";

/**
 * Échappe un champ CSV: entouré de guillemets dès qu'il contient le
 * séparateur, un guillemet ou un saut de ligne; un guillemet interne est
 * doublé. Un champ "propre" reste tel quel — pas de guillemets inutiles.
 */
function escapeCsvField(value: string): string {
  if (value.includes(DELIMITER) || /["\n\r]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

/**
 * Génère un CSV avec un BOM UTF-8 en tête, pour qu'Excel détecte
 * automatiquement l'encodage et affiche correctement les accents.
 */
export function rowsToCsv(rows: ExportRow[]): string {
  const header = EXPORT_COLUMNS.map((column) => escapeCsvField(column.header)).join(
    DELIMITER,
  );
  const lines = rows.map((row) =>
    EXPORT_COLUMNS.map((column) => escapeCsvField(row[column.key])).join(DELIMITER),
  );
  return ["﻿" + header, ...lines].join("\r\n");
}
