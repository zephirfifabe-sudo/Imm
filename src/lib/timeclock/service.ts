import type { TimeEntryType } from "@/types/database";

/**
 * Détermine les actions de pointage valides à partir du dernier événement
 * enregistré pour un employé. C'est la seule source de vérité sur la
 * validité d'une transition — le terminal ne fait que proposer les boutons
 * correspondants, jamais décider seul (section 28 du cahier des charges).
 */
export function getValidNextActions(
  lastEntryType: TimeEntryType | null,
): TimeEntryType[] {
  switch (lastEntryType) {
    case null:
    case "CLOCK_OUT":
      return ["CLOCK_IN"];
    case "CLOCK_IN":
      return ["BREAK_START", "CLOCK_OUT"];
    case "BREAK_START":
      return ["BREAK_END"];
    case "BREAK_END":
      return ["BREAK_START", "CLOCK_OUT"];
  }
}

export function isValidNextAction(
  lastEntryType: TimeEntryType | null,
  requestedType: TimeEntryType,
): boolean {
  return getValidNextActions(lastEntryType).includes(requestedType);
}
