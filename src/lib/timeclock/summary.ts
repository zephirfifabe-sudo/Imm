import type { TimeEntryType } from "@/types/database";

export type SummaryEntry = {
  type: TimeEntryType;
  occurred_at: string;
};

export type Anomaly =
  | "CLOCK_OUT_WITHOUT_CLOCK_IN"
  | "BREAK_WITHOUT_CLOCK_IN"
  | "BREAK_END_WITHOUT_START"
  | "DOUBLE_CLOCK_IN"
  | "OPEN_DAY";

export type DaySummary = {
  workedMinutes: number;
  breakMinutes: number;
  anomalies: Anomaly[];
};

/**
 * Reconstruit le temps travaillé et les pauses d'une journée à partir de ses
 * pointages, et détecte les anomalies (pointage orphelin, journée non
 * clôturée, etc.). Logique pure — aucune notion de fuseau horaire ni
 * d'entreprise ici, uniquement une séquence d'événements déjà filtrée pour
 * un employé et une journée donnés.
 *
 * Limite connue: une équipe de nuit qui chevauche minuit sera comptée sur
 * deux journées civiles distinctes. Acceptable pour ce MVP, à revoir si des
 * clients horeca/night-shift le demandent explicitement.
 */
export function summarizeDay(
  entries: SummaryEntry[],
  options: { isPastDay: boolean },
): DaySummary {
  const sorted = [...entries].sort(
    (a, b) => new Date(a.occurred_at).getTime() - new Date(b.occurred_at).getTime(),
  );

  let state: "OUT" | "IN" | "BREAK" = "OUT";
  let segmentStart: number | null = null;
  let breakStart: number | null = null;
  let workedMs = 0;
  let breakMs = 0;
  const anomalies: Anomaly[] = [];

  for (const entry of sorted) {
    const timestamp = new Date(entry.occurred_at).getTime();

    switch (entry.type) {
      case "CLOCK_IN": {
        if (state !== "OUT") {
          anomalies.push("DOUBLE_CLOCK_IN");
          break;
        }
        segmentStart = timestamp;
        state = "IN";
        break;
      }
      case "CLOCK_OUT": {
        if (state === "OUT" || segmentStart === null) {
          anomalies.push("CLOCK_OUT_WITHOUT_CLOCK_IN");
          break;
        }
        workedMs += timestamp - segmentStart;
        segmentStart = null;
        state = "OUT";
        break;
      }
      case "BREAK_START": {
        if (state !== "IN" || segmentStart === null) {
          anomalies.push("BREAK_WITHOUT_CLOCK_IN");
          break;
        }
        workedMs += timestamp - segmentStart;
        breakStart = timestamp;
        state = "BREAK";
        break;
      }
      case "BREAK_END": {
        if (state !== "BREAK" || breakStart === null) {
          anomalies.push("BREAK_END_WITHOUT_START");
          break;
        }
        breakMs += timestamp - breakStart;
        segmentStart = timestamp;
        breakStart = null;
        state = "IN";
        break;
      }
    }
  }

  if (options.isPastDay && state !== "OUT") {
    anomalies.push("OPEN_DAY");
  }

  return {
    workedMinutes: Math.round(workedMs / 60000),
    breakMinutes: Math.round(breakMs / 60000),
    anomalies,
  };
}

export type PresenceState = "PRESENT" | "ON_BREAK" | "ABSENT";

/** État de présence courant, dérivé du dernier pointage réel de l'employé. */
export function getPresenceState(
  lastEntryType: TimeEntryType | null,
): PresenceState {
  switch (lastEntryType) {
    case "CLOCK_IN":
    case "BREAK_END":
      return "PRESENT";
    case "BREAK_START":
      return "ON_BREAK";
    case "CLOCK_OUT":
    case null:
      return "ABSENT";
  }
}
