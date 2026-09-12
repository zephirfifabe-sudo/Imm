/**
 * Aides d'affichage pures (aucune dépendance DOM/React), partagées entre la
 * grille d'édition ADMIN et la vue lecture seule employé.
 */

import { ABSENCE_LABELS, SHIFT_DEFINITIONS, type ShiftCode } from "./types";

export const DAY_NAMES = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

export function cellLabel(code: ShiftCode): string {
  return code;
}

export function cellTitle(code: ShiftCode): string {
  if (code === "") return "Repos";
  if (code in SHIFT_DEFINITIONS) return SHIFT_DEFINITIONS[code as keyof typeof SHIFT_DEFINITIONS].label;
  if (code in ABSENCE_LABELS) return ABSENCE_LABELS[code as keyof typeof ABSENCE_LABELS];
  return code;
}

export const CELL_COLOR_CLASSES: Record<string, string> = {
  M: "bg-blue-50 text-blue-800",
  A: "bg-amber-50 text-amber-800",
  S: "bg-orange-50 text-orange-800",
  N: "bg-slate-800 text-white",
  C: "bg-emerald-50 text-emerald-800",
  MA: "bg-red-50 text-red-800",
  F: "bg-purple-50 text-purple-800",
  RC: "bg-teal-50 text-teal-800",
  JS: "bg-lime-50 text-lime-800",
};

export function dateForDay(periodStart: Date, dayIndex: number): Date {
  return new Date(periodStart.getTime() + dayIndex * 86_400_000);
}
