/**
 * Logique pure du planificateur d'horaires: génération automatique, cycle
 * manuel d'une case, contrôle de conformité. Aucune dépendance à la base de
 * données ni au DOM — testable isolément, comme le reste de `src/lib`.
 */

import {
  ABSENCE_CODES,
  DEFAULT_SCHEDULING_SETTINGS,
  REST_CODE,
  SHIFT_DEFINITIONS,
  TOTAL_DAYS,
  WORK_CODES,
  type AbsenceCode,
  type ComplianceIssue,
  type ScheduleGrid,
  type SchedulingEmployee,
  type SchedulingSettings,
  type ShiftCode,
  type WorkCode,
} from "./types";

export function isWorkCode(code: ShiftCode): code is WorkCode {
  return (WORK_CODES as readonly string[]).includes(code);
}

export function isAbsenceCode(code: ShiftCode): code is AbsenceCode {
  return (ABSENCE_CODES as readonly string[]).includes(code);
}

export function shiftHours(code: ShiftCode): number {
  return isWorkCode(code) ? SHIFT_DEFINITIONS[code].hours : 0;
}

function emptySchedule(): ShiftCode[] {
  return new Array<ShiftCode>(TOTAL_DAYS).fill(REST_CODE);
}

export function createEmptyGrid(employees: SchedulingEmployee[]): ScheduleGrid {
  const grid: ScheduleGrid = {};
  for (const employee of employees) {
    grid[employee.id] = emptySchedule();
  }
  return grid;
}

/** Jour de semaine réel, 0 = lundi ... 6 = dimanche, pour un jour de la période. */
export function dayOfWeek(periodStart: Date, dayIndex: number): number {
  const date = new Date(periodStart.getTime() + dayIndex * 86_400_000);
  return (date.getUTCDay() + 6) % 7;
}

export function isWeekendDay(periodStart: Date, dayIndex: number): boolean {
  const dow = dayOfWeek(periodStart, dayIndex);
  return dow === 5 || dow === 6;
}

function absoluteStart(dayIndex: number, code: ShiftCode): number | null {
  if (!isWorkCode(code)) return null;
  return dayIndex * 24 + SHIFT_DEFINITIONS[code].start;
}

function absoluteEnd(dayIndex: number, code: ShiftCode): number | null {
  if (!isWorkCode(code)) return null;
  return dayIndex * 24 + SHIFT_DEFINITIONS[code].end;
}

export function totalHoursAssigned(schedule: ShiftCode[]): number {
  return schedule.reduce((sum, code) => sum + shiftHours(code), 0);
}

export function contractTargetHours(employee: SchedulingEmployee): number {
  return employee.contractHoursPerWeek * 4;
}

export function nightsCount(schedule: ShiftCode[]): number {
  return schedule.filter((code) => code === "N").length;
}

export function weekendShiftsCount(periodStart: Date, schedule: ShiftCode[]): number {
  let count = 0;
  for (let d = 0; d < TOTAL_DAYS; d++) {
    if (isWeekendDay(periodStart, d) && isWorkCode(schedule[d])) count++;
  }
  return count;
}

function weekIndexOf(dayIndex: number): number {
  return Math.floor(dayIndex / 7);
}

export function weekendsWorkedCount(periodStart: Date, schedule: ShiftCode[]): number {
  const weeks = new Set<number>();
  for (let d = 0; d < TOTAL_DAYS; d++) {
    if (isWeekendDay(periodStart, d) && isWorkCode(schedule[d])) {
      weeks.add(weekIndexOf(d));
    }
  }
  return weeks.size;
}

export function consecutiveNightsEndingAt(
  schedule: ShiftCode[],
  dayIndex: number,
  hypotheticalAssignHere: boolean,
): number {
  let count = hypotheticalAssignHere ? 1 : 0;
  for (let d = dayIndex - 1; d >= 0 && schedule[d] === "N"; d--) count++;
  return count;
}

export function consecutiveWorkDaysEndingAt(
  schedule: ShiftCode[],
  dayIndex: number,
  hypotheticalCode: ShiftCode,
): number {
  let count = isWorkCode(hypotheticalCode) ? 1 : 0;
  for (let d = dayIndex - 1; d >= 0 && isWorkCode(schedule[d]); d--) count++;
  return count;
}

export function restOkFor(
  schedule: ShiftCode[],
  dayIndex: number,
  code: ShiftCode,
  minRestHours: number,
): boolean {
  const start = absoluteStart(dayIndex, code);
  const end = absoluteEnd(dayIndex, code);
  if (start === null || end === null) return true;

  if (dayIndex > 0) {
    const prevEnd = absoluteEnd(dayIndex - 1, schedule[dayIndex - 1]);
    if (prevEnd !== null && start - prevEnd < minRestHours) return false;
  }
  if (dayIndex < TOTAL_DAYS - 1) {
    const nextStart = absoluteStart(dayIndex + 1, schedule[dayIndex + 1]);
    if (nextStart !== null && nextStart - end < minRestHours) return false;
  }
  return true;
}

function maxWorkedInAnyRollingWeek(
  schedule: ShiftCode[],
  dayIndex: number,
  hypotheticalCode: ShiftCode,
): number {
  let worst = 0;
  for (
    let start = Math.max(0, dayIndex - 6);
    start <= Math.min(dayIndex, TOTAL_DAYS - 7);
    start++
  ) {
    let worked = 0;
    for (let d = start; d < start + 7; d++) {
      const code = d === dayIndex ? hypotheticalCode : schedule[d];
      if (isWorkCode(code)) worked++;
    }
    worst = Math.max(worst, worked);
  }
  return worst;
}

function weekendQuotaOk(
  periodStart: Date,
  schedule: ShiftCode[],
  dayIndex: number,
  settings: SchedulingSettings,
): boolean {
  if (!settings.enforceWeekendQuota) return true;
  if (!isWeekendDay(periodStart, dayIndex)) return true;
  const weeks = new Set<number>();
  for (let d = 0; d < TOTAL_DAYS; d++) {
    if (isWeekendDay(periodStart, d) && isWorkCode(schedule[d])) weeks.add(weekIndexOf(d));
  }
  if (weeks.has(weekIndexOf(dayIndex))) return true;
  return weeks.size < settings.maxWeekendsPerPeriod;
}

export function canAssignNight(
  employee: SchedulingEmployee,
  schedule: ShiftCode[],
  dayIndex: number,
  settings: SchedulingSettings,
  periodStart: Date,
): boolean {
  if (employee.dayOnly) return false;
  if (schedule[dayIndex] !== REST_CODE) return false;
  if (nightsCount(schedule) >= employee.maxNightsPerPeriod) return false;
  if (consecutiveNightsEndingAt(schedule, dayIndex, true) > settings.maxConsecutiveNights) return false;
  if (consecutiveWorkDaysEndingAt(schedule, dayIndex, "N") > settings.maxConsecutiveWorkDays) return false;
  if (settings.enforceMaxSixDaysPerWeek && maxWorkedInAnyRollingWeek(schedule, dayIndex, "N") > 6) return false;
  if (!weekendQuotaOk(periodStart, schedule, dayIndex, settings)) return false;
  if (!restOkFor(schedule, dayIndex, "N", settings.minRestHours)) return false;
  return true;
}

export function canAssignDayShift(
  employee: SchedulingEmployee,
  schedule: ShiftCode[],
  dayIndex: number,
  code: WorkCode,
  settings: SchedulingSettings,
  periodStart: Date,
): boolean {
  if (employee.nightOnly) return false;
  if (schedule[dayIndex] !== REST_CODE) return false;
  if (consecutiveWorkDaysEndingAt(schedule, dayIndex, code) > settings.maxConsecutiveWorkDays) return false;
  if (settings.enforceMaxSixDaysPerWeek && maxWorkedInAnyRollingWeek(schedule, dayIndex, code) > 6) return false;
  if (!weekendQuotaOk(periodStart, schedule, dayIndex, settings)) return false;
  if (!restOkFor(schedule, dayIndex, code, settings.minRestHours)) return false;
  return true;
}

function staffCountFor(grid: ScheduleGrid, dayIndex: number, code: WorkCode): number {
  let count = 0;
  for (const schedule of Object.values(grid)) {
    if (schedule[dayIndex] === code) count++;
  }
  return count;
}

function scoreCandidate(
  employee: SchedulingEmployee,
  grid: ScheduleGrid,
  dayIndex: number,
  code: WorkCode,
  periodStart: Date,
): number {
  const schedule = grid[employee.id];
  let score = contractTargetHours(employee) - totalHoursAssigned(schedule);

  if (code === "N") {
    const overOwnMin = nightsCount(schedule) - employee.minNightsPerPeriod;
    if (overOwnMin > 0) score -= overOwnMin * 6;
    if (dayIndex > 0 && schedule[dayIndex - 1] === "N") score += 60;
  } else {
    const sameCodeCount = schedule.filter((c) => c === code).length;
    score -= sameCodeCount * 9;
  }

  if (isWeekendDay(periodStart, dayIndex)) {
    score -= weekendsWorkedCount(periodStart, schedule) * 200;
  }

  score += Math.random() * 4;
  return score;
}

function tryBuildNightBlock(
  employee: SchedulingEmployee,
  grid: ScheduleGrid,
  startDay: number,
  settings: SchedulingSettings,
  periodStart: Date,
): number[] {
  const schedule = grid[employee.id];
  const assigned: number[] = [];
  let d = startDay;
  while (d < TOTAL_DAYS && assigned.length < settings.maxConsecutiveNights) {
    if (staffCountFor(grid, d, "N") >= settings.minStaffing.N) break;
    if (!canAssignNight(employee, schedule, d, settings, periodStart)) break;
    schedule[d] = "N";
    assigned.push(d);
    d++;
  }
  if (assigned.length < settings.minConsecutiveNights) {
    for (const day of assigned) schedule[day] = REST_CODE;
    return [];
  }
  return assigned;
}

/**
 * Génère un planning de 28 jours. Ne dépasse jamais l'effectif max configuré
 * par créneau, et respecte toujours les contraintes dures (repos, quotas,
 * enchaînements). Peut laisser un créneau en sous-effectif si aucun candidat
 * éligible ne reste — c'est signalé par `computeCompliance`, jamais masqué.
 */
export function generateSchedule(
  employees: SchedulingEmployee[],
  settings: SchedulingSettings = DEFAULT_SCHEDULING_SETTINGS,
  periodStart: Date,
): ScheduleGrid {
  const grid = createEmptyGrid(employees);
  if (employees.length === 0) return grid;

  // Phase 1: nuits, par blocs enchaînés quand la règle est active.
  for (let day = 0; day < TOTAL_DAYS; day++) {
    let safety = 0;
    while (staffCountFor(grid, day, "N") < settings.minStaffing.N && safety < employees.length + 1) {
      safety++;
      const candidates = employees.filter(
        (e) => grid[e.id][day] === REST_CODE && canAssignNight(e, grid[e.id], day, settings, periodStart),
      );
      if (candidates.length === 0) break;
      candidates.sort(
        (a, b) => scoreCandidate(b, grid, day, "N", periodStart) - scoreCandidate(a, grid, day, "N", periodStart),
      );

      if (!settings.requireNightChaining) {
        grid[candidates[0].id][day] = "N";
        continue;
      }

      let placedBlock = false;
      for (const candidate of candidates) {
        const block = tryBuildNightBlock(candidate, grid, day, settings, periodStart);
        if (block.length > 0) {
          placedBlock = true;
          break;
        }
      }
      if (!placedBlock) {
        if (settings.allowIsolatedNightFallback) {
          grid[candidates[0].id][day] = "N";
        } else {
          break;
        }
      }
    }
  }

  // Phase 2: créneaux de jour.
  for (let day = 0; day < TOTAL_DAYS; day++) {
    for (const code of ["M", "A", "S"] as const) {
      let safety = 0;
      while (staffCountFor(grid, day, code) < settings.minStaffing[code] && safety < employees.length + 1) {
        safety++;
        const candidates = employees.filter((e) =>
          canAssignDayShift(e, grid[e.id], day, code, settings, periodStart),
        );
        if (candidates.length === 0) break;
        candidates.sort(
          (a, b) =>
            scoreCandidate(b, grid, day, code, periodStart) - scoreCandidate(a, grid, day, code, periodStart),
        );
        grid[candidates[0].id][day] = code;
      }
    }
  }

  // Phase 3: complète les minimums de nuits par employé, sans dépasser l'effectif max.
  for (const employee of employees) {
    const schedule = grid[employee.id];
    let safety = 0;
    while (nightsCount(schedule) < employee.minNightsPerPeriod && safety < TOTAL_DAYS) {
      safety++;
      let placed = false;
      for (let d = 0; d < TOTAL_DAYS && !placed; d++) {
        if (schedule[d] !== REST_CODE) continue;
        if (staffCountFor(grid, d, "N") >= settings.maxStaffing.N) continue;
        if (!canAssignNight(employee, schedule, d, settings, periodStart)) continue;
        schedule[d] = "N";
        placed = true;
      }
      if (!placed) break;
    }
  }

  return grid;
}

/** Ordre de cycle pour l'édition manuelle d'une case (clic répété). */
const CYCLE_ORDER: ShiftCode[] = [REST_CODE, "M", "A", "S", "N", "C", "JS", "MA", "F", "RC"];

export function nextCycleCode(current: ShiftCode): ShiftCode {
  const index = CYCLE_ORDER.indexOf(current);
  return CYCLE_ORDER[(index + 1 + CYCLE_ORDER.length) % CYCLE_ORDER.length];
}

/**
 * Contrôle de conformité: relit un planning déjà posé (généré ou modifié à
 * la main) et signale les écarts par rapport aux règles configurées. Ne
 * bloque jamais rien — sert uniquement à guider une correction manuelle.
 */
export function computeCompliance(
  employees: SchedulingEmployee[],
  grid: ScheduleGrid,
  settings: SchedulingSettings,
  periodStart: Date,
): ComplianceIssue[] {
  const issues: ComplianceIssue[] = [];

  for (const code of WORK_CODES) {
    for (let d = 0; d < TOTAL_DAYS; d++) {
      const count = staffCountFor(grid, d, code);
      if (count > settings.maxStaffing[code]) {
        issues.push({
          employeeId: "",
          employeeName: `Effectif ${SHIFT_DEFINITIONS[code].label}`,
          severity: "warning",
          message: `Jour ${d + 1} : ${count} personnes sur ce créneau (maximum configuré : ${settings.maxStaffing[code]}).`,
        });
      }
    }
  }

  for (const employee of employees) {
    const schedule = grid[employee.id];

    for (let d = 0; d < TOTAL_DAYS; d++) {
      const code = schedule[d];
      if (!isWorkCode(code)) continue;
      if (code === "N" && employee.dayOnly) {
        issues.push({
          employeeId: employee.id,
          employeeName: employee.name,
          severity: "critical",
          message: `Jour ${d + 1} : nuit attribuée alors qu'il/elle est enregistré(e) "journée uniquement".`,
        });
      }
      if (code !== "N" && employee.nightOnly) {
        issues.push({
          employeeId: employee.id,
          employeeName: employee.name,
          severity: "critical",
          message: `Jour ${d + 1} : créneau de jour attribué alors qu'il/elle est enregistré(e) "nuit uniquement".`,
        });
      }
      if (!restOkFor(schedule, d, code, settings.minRestHours)) {
        issues.push({
          employeeId: employee.id,
          employeeName: employee.name,
          severity: "critical",
          message: `Jour ${d + 1} : repos de moins de ${settings.minRestHours}h avant/après cette vacation.`,
        });
      }
    }

    let maxConsecNights = 0;
    let running = 0;
    for (let d = 0; d < TOTAL_DAYS; d++) {
      running = schedule[d] === "N" ? running + 1 : 0;
      maxConsecNights = Math.max(maxConsecNights, running);
    }
    if (maxConsecNights > settings.maxConsecutiveNights) {
      issues.push({
        employeeId: employee.id,
        employeeName: employee.name,
        severity: "critical",
        message: `Série de ${maxConsecNights} nuits consécutives (maximum configuré : ${settings.maxConsecutiveNights}).`,
      });
    }

    let maxConsecWork = 0;
    running = 0;
    for (let d = 0; d < TOTAL_DAYS; d++) {
      running = isWorkCode(schedule[d]) ? running + 1 : 0;
      maxConsecWork = Math.max(maxConsecWork, running);
    }
    if (maxConsecWork > settings.maxConsecutiveWorkDays) {
      issues.push({
        employeeId: employee.id,
        employeeName: employee.name,
        severity: "critical",
        message: `Série de ${maxConsecWork} jours de travail consécutifs (maximum configuré : ${settings.maxConsecutiveWorkDays}).`,
      });
    }

    const weekends = weekendsWorkedCount(periodStart, schedule);
    if (settings.enforceWeekendQuota && weekends > settings.maxWeekendsPerPeriod) {
      issues.push({
        employeeId: employee.id,
        employeeName: employee.name,
        severity: "critical",
        message: `${weekends} week-ends travaillés sur la période (maximum configuré : ${settings.maxWeekendsPerPeriod}).`,
      });
    }

    const nights = nightsCount(schedule);
    if (nights < employee.minNightsPerPeriod) {
      issues.push({
        employeeId: employee.id,
        employeeName: employee.name,
        severity: "warning",
        message: `Nombre de nuits (${nights}) inférieur au minimum (${employee.minNightsPerPeriod}).`,
      });
    }
    if (nights > employee.maxNightsPerPeriod) {
      issues.push({
        employeeId: employee.id,
        employeeName: employee.name,
        severity: "warning",
        message: `Nombre de nuits (${nights}) supérieur au maximum (${employee.maxNightsPerPeriod}).`,
      });
    }

    const variance = totalHoursAssigned(schedule) - contractTargetHours(employee);
    if (Math.abs(variance) > 8) {
      issues.push({
        employeeId: employee.id,
        employeeName: employee.name,
        severity: "warning",
        message: `Écart d'heures important par rapport à l'objectif : ${variance > 0 ? "+" : ""}${variance}h sur la période.`,
      });
    }
  }

  return issues;
}
