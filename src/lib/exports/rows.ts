import type { HistoryDayGroup } from "@/lib/history/queries";
import { getTranslator } from "@/i18n";

export type ExportRow = {
  employee: string;
  date: string;
  workedHm: string;
  workedDecimal: string;
  breakHm: string;
  anomalies: string;
};

function formatHm(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}h${m.toString().padStart(2, "0")}`;
}

function formatDecimalHours(minutes: number): string {
  return (minutes / 60).toFixed(2);
}

/**
 * Transforme les groupes jour/employé (déjà calculés par `getHistory`) en
 * lignes de rapport prêtes à exporter — une ligne par employé et par jour,
 * avec les heures en HH:MM (lisible) et en décimal (utilisable tel quel
 * pour un calcul de paie).
 */
export function buildExportRows(groups: HistoryDayGroup[]): ExportRow[] {
  const t = getTranslator();

  return groups.map((group) => ({
    employee: group.employeeName,
    date: group.dateKey,
    workedHm: formatHm(group.workedMinutes),
    workedDecimal: formatDecimalHours(group.workedMinutes),
    breakHm: formatHm(group.breakMinutes),
    anomalies: group.anomalies.map((a) => t(`history.anomaly.${a}`)).join("; "),
  }));
}

export const EXPORT_COLUMNS: { key: keyof ExportRow; header: string }[] = [
  { key: "employee", header: "Employé" },
  { key: "date", header: "Date" },
  { key: "workedHm", header: "Temps travaillé (h:min)" },
  { key: "workedDecimal", header: "Temps travaillé (décimal)" },
  { key: "breakHm", header: "Pause" },
  { key: "anomalies", header: "Anomalies" },
];
