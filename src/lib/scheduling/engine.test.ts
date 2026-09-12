import { describe, expect, it } from "vitest";
import {
  canAssignDayShift,
  canAssignNight,
  computeCompliance,
  consecutiveNightsEndingAt,
  consecutiveWorkDaysEndingAt,
  createEmptyGrid,
  dayOfWeek,
  generateSchedule,
  isAbsenceCode,
  isWeekendDay,
  isWorkCode,
  nextCycleCode,
  restOkFor,
  shiftHours,
  totalHoursAssigned,
} from "./engine";
import { DEFAULT_SCHEDULING_SETTINGS, TOTAL_DAYS, type SchedulingEmployee } from "./types";

const PERIOD_START = new Date("2026-01-05T00:00:00.000Z"); // un lundi

function makeEmployee(overrides: Partial<SchedulingEmployee> = {}): SchedulingEmployee {
  return {
    id: overrides.id ?? "emp-1",
    name: overrides.name ?? "Employé Test",
    contractHoursPerWeek: overrides.contractHoursPerWeek ?? 38,
    dayOnly: overrides.dayOnly ?? false,
    nightOnly: overrides.nightOnly ?? false,
    minNightsPerPeriod: overrides.minNightsPerPeriod ?? 0,
    maxNightsPerPeriod: overrides.maxNightsPerPeriod ?? 8,
  };
}

describe("isWorkCode / isAbsenceCode", () => {
  it("classe correctement les codes", () => {
    expect(isWorkCode("M")).toBe(true);
    expect(isWorkCode("C")).toBe(false);
    expect(isWorkCode("")).toBe(false);
    expect(isAbsenceCode("MA")).toBe(true);
    expect(isAbsenceCode("N")).toBe(false);
  });
});

describe("shiftHours / totalHoursAssigned", () => {
  it("compte les heures des créneaux de travail uniquement", () => {
    expect(shiftHours("M")).toBe(8);
    expect(shiftHours("N")).toBe(9);
    expect(shiftHours("C")).toBe(0);
    expect(shiftHours("")).toBe(0);

    const schedule = createEmptyGrid([makeEmployee()])["emp-1"];
    schedule[0] = "M";
    schedule[1] = "N";
    schedule[2] = "C";
    expect(totalHoursAssigned(schedule)).toBe(17);
  });
});

describe("dayOfWeek / isWeekendDay", () => {
  it("identifie le lundi de départ comme jour 0", () => {
    expect(dayOfWeek(PERIOD_START, 0)).toBe(0);
    expect(dayOfWeek(PERIOD_START, 5)).toBe(5); // samedi
    expect(dayOfWeek(PERIOD_START, 6)).toBe(6); // dimanche
    expect(isWeekendDay(PERIOD_START, 5)).toBe(true);
    expect(isWeekendDay(PERIOD_START, 0)).toBe(false);
  });
});

describe("consecutiveNightsEndingAt / consecutiveWorkDaysEndingAt", () => {
  it("compte les séries en cours", () => {
    const schedule = createEmptyGrid([makeEmployee()])["emp-1"];
    schedule[0] = "N";
    schedule[1] = "N";
    expect(consecutiveNightsEndingAt(schedule, 2, true)).toBe(3);
    expect(consecutiveNightsEndingAt(schedule, 2, false)).toBe(2);

    schedule[2] = "M";
    expect(consecutiveWorkDaysEndingAt(schedule, 2, "M")).toBe(3);
    // Jour 3 hypothétique enchaîné sur la série de travail des jours 0-2.
    expect(consecutiveWorkDaysEndingAt(schedule, 3, "A")).toBe(4);
  });
});

describe("restOkFor", () => {
  it("refuse un enchaînement sans repos suffisant", () => {
    const schedule = createEmptyGrid([makeEmployee()])["emp-1"];
    schedule[0] = "S"; // 14h-22h
    // Reprendre un Matin (7h-15h) le lendemain ne laisse que 9h de repos.
    expect(restOkFor(schedule, 1, "M", 11)).toBe(false);
    // Reprendre un Soir le lendemain laisse 16h de repos.
    expect(restOkFor(schedule, 1, "S", 11)).toBe(true);
  });
});

describe("canAssignNight / canAssignDayShift", () => {
  it("respecte les contraintes jour/nuit uniquement", () => {
    const dayOnlyEmp = makeEmployee({ dayOnly: true });
    const nightOnlyEmp = makeEmployee({ id: "emp-2", nightOnly: true });
    const schedule = createEmptyGrid([dayOnlyEmp])[dayOnlyEmp.id];

    expect(canAssignNight(dayOnlyEmp, schedule, 0, DEFAULT_SCHEDULING_SETTINGS, PERIOD_START)).toBe(false);
    expect(canAssignDayShift(dayOnlyEmp, schedule, 0, "M", DEFAULT_SCHEDULING_SETTINGS, PERIOD_START)).toBe(true);

    const nightSchedule = createEmptyGrid([nightOnlyEmp])[nightOnlyEmp.id];
    expect(canAssignDayShift(nightOnlyEmp, nightSchedule, 0, "M", DEFAULT_SCHEDULING_SETTINGS, PERIOD_START)).toBe(
      false,
    );
    expect(canAssignNight(nightOnlyEmp, nightSchedule, 0, DEFAULT_SCHEDULING_SETTINGS, PERIOD_START)).toBe(true);
  });
});

describe("nextCycleCode", () => {
  it("boucle sur l'ensemble des codes", () => {
    expect(nextCycleCode("")).toBe("M");
    expect(nextCycleCode("N")).toBe("C");
    expect(nextCycleCode("RC")).toBe("");
  });
});

describe("generateSchedule", () => {
  it("ne dépasse jamais l'effectif maximum configuré par créneau", () => {
    const employees = Array.from({ length: 6 }, (_, i) =>
      makeEmployee({ id: `emp-${i}`, name: `Employé ${i}` }),
    );
    const settings = {
      ...DEFAULT_SCHEDULING_SETTINGS,
      minStaffing: { M: 1, A: 1, S: 1, N: 1 },
      maxStaffing: { M: 2, A: 2, S: 2, N: 1 },
    };
    const grid = generateSchedule(employees, settings, PERIOD_START);

    for (let d = 0; d < TOTAL_DAYS; d++) {
      for (const code of ["M", "A", "S", "N"] as const) {
        const count = Object.values(grid).filter((s) => s[d] === code).length;
        expect(count).toBeLessThanOrEqual(settings.maxStaffing[code]);
      }
    }
  });

  it("n'assigne jamais un travail à un employé sans profil (grille vide sans employés)", () => {
    expect(generateSchedule([], DEFAULT_SCHEDULING_SETTINGS, PERIOD_START)).toEqual({});
  });
});

describe("computeCompliance", () => {
  it("signale une violation dure jour/nuit uniquement", () => {
    const employee = makeEmployee({ dayOnly: true });
    const grid = createEmptyGrid([employee]);
    grid[employee.id][0] = "N";

    const issues = computeCompliance([employee], grid, DEFAULT_SCHEDULING_SETTINGS, PERIOD_START);
    expect(issues.some((i) => i.severity === "critical" && i.employeeId === employee.id)).toBe(true);
  });

  it("ne signale rien sur un planning vide", () => {
    const employee = makeEmployee();
    const grid = createEmptyGrid([employee]);
    const issues = computeCompliance([employee], grid, DEFAULT_SCHEDULING_SETTINGS, PERIOD_START);
    // Un planning entièrement vide génère un écart d'heures (warning), mais aucune violation dure.
    expect(issues.every((i) => i.severity !== "critical")).toBe(true);
  });
});
