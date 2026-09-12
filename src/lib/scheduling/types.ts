/**
 * Types du planificateur d'horaires. Générique par conception: aucun champ
 * ni aucune valeur par défaut ne référence un secteur ou une commission
 * paritaire précise — seulement des recommandations générales de droit du
 * travail belge, que l'entreprise peut ajuster.
 */

export const WORK_CODES = ["M", "A", "S", "N"] as const;
export type WorkCode = (typeof WORK_CODES)[number];

export const ABSENCE_CODES = ["C", "MA", "F", "RC", "JS"] as const;
export type AbsenceCode = (typeof ABSENCE_CODES)[number];

/** Chaîne vide = repos (aucune ligne stockée en base pour ce jour). */
export const REST_CODE = "";

export type ShiftCode = WorkCode | AbsenceCode | typeof REST_CODE;

export const TOTAL_DAYS = 28;
export const NUM_WEEKS = 4;

export type ShiftDefinition = {
  start: number;
  end: number;
  hours: number;
  label: string;
};

/** `end` dépasse 24 pour la nuit: elle se termine le lendemain. */
export const SHIFT_DEFINITIONS: Record<WorkCode, ShiftDefinition> = {
  M: { start: 7, end: 15, hours: 8, label: "Matin (7h-15h)" },
  A: { start: 12, end: 20, hours: 8, label: "Après-midi (12h-20h)" },
  S: { start: 14, end: 22, hours: 8, label: "Soir (14h-22h)" },
  N: { start: 22, end: 31, hours: 9, label: "Nuit (22h-7h)" },
};

export const ABSENCE_LABELS: Record<AbsenceCode, string> = {
  C: "Congé",
  MA: "Maladie",
  F: "Formation",
  RC: "Repos compensatoire",
  JS: "Jour supplémentaire",
};

export type SchedulingSettings = {
  minStaffing: Record<WorkCode, number>;
  maxStaffing: Record<WorkCode, number>;
  minConsecutiveNights: number;
  maxConsecutiveNights: number;
  requireNightChaining: boolean;
  allowIsolatedNightFallback: boolean;
  maxConsecutiveWorkDays: number;
  enforceMaxSixDaysPerWeek: boolean;
  maxWeekendsPerPeriod: number;
  enforceWeekendQuota: boolean;
  minRestHours: number;
};

export const DEFAULT_SCHEDULING_SETTINGS: SchedulingSettings = {
  minStaffing: { M: 1, A: 1, S: 1, N: 1 },
  maxStaffing: { M: 2, A: 2, S: 2, N: 1 },
  minConsecutiveNights: 2,
  maxConsecutiveNights: 5,
  requireNightChaining: true,
  allowIsolatedNightFallback: true,
  maxConsecutiveWorkDays: 5,
  enforceMaxSixDaysPerWeek: true,
  maxWeekendsPerPeriod: 2,
  enforceWeekendQuota: true,
  minRestHours: 11,
};

export type SchedulingEmployee = {
  id: string;
  name: string;
  contractHoursPerWeek: number;
  dayOnly: boolean;
  nightOnly: boolean;
  minNightsPerPeriod: number;
  maxNightsPerPeriod: number;
};

/** Une entrée par employé, 28 cases (index 0 = premier jour de la période). */
export type ScheduleGrid = Record<string, ShiftCode[]>;

export type ComplianceSeverity = "critical" | "warning";

export type ComplianceIssue = {
  employeeId: string;
  employeeName: string;
  severity: ComplianceSeverity;
  message: string;
};
