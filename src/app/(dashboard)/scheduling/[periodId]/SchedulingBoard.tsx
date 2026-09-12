"use client";

import { useMemo, useState, useTransition } from "react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Badge } from "@/components/ui/Badge";
import { getTranslator } from "@/i18n";
import {
  computeCompliance,
  generateSchedule,
  nextCycleCode,
  totalHoursAssigned,
  contractTargetHours,
} from "@/lib/scheduling/engine";
import {
  ABSENCE_LABELS,
  SHIFT_DEFINITIONS,
  TOTAL_DAYS,
  WORK_CODES,
  type ScheduleGrid,
  type SchedulingEmployee,
  type SchedulingSettings,
} from "@/lib/scheduling/types";
import { saveGridAction, setCellAction, updatePeriodSettingsAction } from "./actions";

const t = getTranslator();

const DAY_NAMES = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

function cellLabel(code: string): string {
  if (code === "") return "";
  if (code in SHIFT_DEFINITIONS) return code;
  return code;
}

function cellTitle(code: string): string {
  if (code === "") return "Repos";
  if (code in SHIFT_DEFINITIONS) return SHIFT_DEFINITIONS[code as keyof typeof SHIFT_DEFINITIONS].label;
  if (code in ABSENCE_LABELS) return ABSENCE_LABELS[code as keyof typeof ABSENCE_LABELS];
  return code;
}

const CELL_COLOR_CLASSES: Record<string, string> = {
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

function dateForDay(periodStart: Date, dayIndex: number): Date {
  return new Date(periodStart.getTime() + dayIndex * 86_400_000);
}

export function SchedulingBoard({
  periodId,
  periodStartIso,
  initialSettings,
  employees,
  initialGrid,
}: {
  periodId: string;
  periodStartIso: string;
  initialSettings: SchedulingSettings;
  employees: SchedulingEmployee[];
  initialGrid: ScheduleGrid;
}) {
  const periodStart = useMemo(() => new Date(`${periodStartIso}T00:00:00.000Z`), [periodStartIso]);
  const [settings, setSettings] = useState<SchedulingSettings>(initialSettings);
  const [grid, setGrid] = useState<ScheduleGrid>(initialGrid);
  const [week, setWeek] = useState(0);
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const sortedEmployees = useMemo(
    () => [...employees].sort((a, b) => a.name.localeCompare(b.name)),
    [employees],
  );

  const complianceIssues = useMemo(
    () => computeCompliance(employees, grid, settings, periodStart),
    [employees, grid, settings, periodStart],
  );

  function persistGrid(nextGrid: ScheduleGrid) {
    startTransition(async () => {
      const result = await saveGridAction(periodId, nextGrid);
      if (!result.ok) setError(t("scheduling.saveError"));
    });
  }

  function handleGenerate() {
    setError(null);
    const nextGrid = generateSchedule(employees, settings, periodStart);
    setGrid(nextGrid);
    persistGrid(nextGrid);
  }

  function handleClear() {
    setError(null);
    const nextGrid: ScheduleGrid = {};
    for (const employee of employees) {
      nextGrid[employee.id] = new Array(TOTAL_DAYS).fill("");
    }
    setGrid(nextGrid);
    persistGrid(nextGrid);
  }

  function handleCellClick(employeeId: string, dayIndex: number) {
    setError(null);
    const current = grid[employeeId]?.[dayIndex] ?? "";
    const next = nextCycleCode(current);
    setGrid((previous) => {
      const updated = { ...previous, [employeeId]: [...(previous[employeeId] ?? [])] };
      updated[employeeId][dayIndex] = next;
      return updated;
    });
    startTransition(async () => {
      const result = await setCellAction(periodId, employeeId, dayIndex, next);
      if (!result.ok) setError(t("scheduling.saveError"));
    });
  }

  function handleSaveSettings() {
    setError(null);
    startTransition(async () => {
      const result = await updatePeriodSettingsAction(periodId, settings);
      if (!result.ok) setError(t("scheduling.saveError"));
    });
  }

  function updateStaffing(kind: "minStaffing" | "maxStaffing", code: (typeof WORK_CODES)[number], value: number) {
    setSettings((previous) => ({
      ...previous,
      [kind]: { ...previous[kind], [code]: value },
    }));
  }

  const startDay = week * 7;

  return (
    <div className="space-y-6">
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      <Card>
        <h2 className="mb-4 text-sm font-medium text-foreground">
          {t("scheduling.settingsTitle")}
        </h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {WORK_CODES.map((code) => (
            <div key={code} className="space-y-2">
              <p className="text-xs font-medium text-muted">{SHIFT_DEFINITIONS[code].label}</p>
              <div className="flex items-center gap-2">
                <div>
                  <Label htmlFor={`min-${code}`} className="text-xs">
                    {t("scheduling.minLabel")}
                  </Label>
                  <Input
                    id={`min-${code}`}
                    type="number"
                    min={0}
                    value={settings.minStaffing[code]}
                    onChange={(e) => updateStaffing("minStaffing", code, Number(e.target.value) || 0)}
                  />
                </div>
                <div>
                  <Label htmlFor={`max-${code}`} className="text-xs">
                    {t("scheduling.maxLabel")}
                  </Label>
                  <Input
                    id={`max-${code}`}
                    type="number"
                    min={0}
                    value={settings.maxStaffing[code]}
                    onChange={(e) => updateStaffing("maxStaffing", code, Number(e.target.value) || 0)}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <Label htmlFor="minRestHours">{t("scheduling.minRestHoursLabel")}</Label>
            <Input
              id="minRestHours"
              type="number"
              min={0}
              value={settings.minRestHours}
              onChange={(e) =>
                setSettings((p) => ({ ...p, minRestHours: Number(e.target.value) || 0 }))
              }
            />
          </div>
          <div>
            <Label htmlFor="maxConsecutiveWorkDays">{t("scheduling.maxConsecutiveWorkDaysLabel")}</Label>
            <Input
              id="maxConsecutiveWorkDays"
              type="number"
              min={1}
              value={settings.maxConsecutiveWorkDays}
              onChange={(e) =>
                setSettings((p) => ({ ...p, maxConsecutiveWorkDays: Number(e.target.value) || 1 }))
              }
            />
          </div>
          <div>
            <Label htmlFor="maxWeekendsPerPeriod">{t("scheduling.maxWeekendsLabel")}</Label>
            <Input
              id="maxWeekendsPerPeriod"
              type="number"
              min={0}
              value={settings.maxWeekendsPerPeriod}
              onChange={(e) =>
                setSettings((p) => ({ ...p, maxWeekendsPerPeriod: Number(e.target.value) || 0 }))
              }
            />
          </div>
          <div>
            <Label htmlFor="maxConsecutiveNights">{t("scheduling.maxConsecutiveNightsLabel")}</Label>
            <Input
              id="maxConsecutiveNights"
              type="number"
              min={1}
              value={settings.maxConsecutiveNights}
              onChange={(e) =>
                setSettings((p) => ({ ...p, maxConsecutiveNights: Number(e.target.value) || 1 }))
              }
            />
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-4">
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input
              type="checkbox"
              checked={settings.requireNightChaining}
              onChange={(e) => setSettings((p) => ({ ...p, requireNightChaining: e.target.checked }))}
            />
            {t("scheduling.requireNightChainingLabel")}
          </label>
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input
              type="checkbox"
              checked={settings.enforceWeekendQuota}
              onChange={(e) => setSettings((p) => ({ ...p, enforceWeekendQuota: e.target.checked }))}
            />
            {t("scheduling.enforceWeekendQuotaLabel")}
          </label>
        </div>

        <p className="mt-3 text-xs text-muted">{t("scheduling.rulesDisclaimer")}</p>

        <Button className="mt-4" variant="secondary" disabled={isPending} onClick={handleSaveSettings}>
          {t("common.save")}
        </Button>
      </Card>

      <Card>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-medium text-foreground">{t("scheduling.gridTitle")}</h2>
          <div className="flex gap-2">
            <Button disabled={isPending || employees.length === 0} onClick={handleGenerate}>
              {t("scheduling.generate")}
            </Button>
            <Button variant="secondary" disabled={isPending} onClick={handleClear}>
              {t("scheduling.clear")}
            </Button>
            <a href={`/api/exports/scheduling/${periodId}`}>
              <Button type="button" variant="secondary">
                {t("scheduling.exportCsv")}
              </Button>
            </a>
          </div>
        </div>

        {employees.length === 0 ? (
          <p className="text-sm text-muted">{t("scheduling.noEmployees")}</p>
        ) : (
          <>
            <div className="mb-3 flex gap-2">
              {[0, 1, 2, 3].map((w) => (
                <button
                  key={w}
                  type="button"
                  onClick={() => setWeek(w)}
                  className={
                    "rounded-lg px-3 py-1.5 text-xs font-medium " +
                    (w === week
                      ? "bg-primary text-primary-foreground"
                      : "bg-surface text-muted hover:text-foreground")
                  }
                >
                  {t("scheduling.weekLabel", { number: w + 1 })}
                </button>
              ))}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr>
                    <th className="border border-border bg-surface px-2 py-1.5 text-left text-xs font-medium text-muted">
                      {t("employees.title")}
                    </th>
                    {Array.from({ length: 7 }).map((_, i) => {
                      const dayIndex = startDay + i;
                      const date = dateForDay(periodStart, dayIndex);
                      return (
                        <th
                          key={dayIndex}
                          className="border border-border bg-surface px-2 py-1.5 text-xs font-medium text-muted"
                        >
                          {DAY_NAMES[i]}
                          <br />
                          {date.toLocaleDateString("fr-BE", { day: "2-digit", month: "2-digit", timeZone: "UTC" })}
                        </th>
                      );
                    })}
                    <th className="border border-border bg-surface px-2 py-1.5 text-xs font-medium text-muted">
                      {t("scheduling.totalLabel")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedEmployees.map((employee) => {
                    const schedule = grid[employee.id] ?? new Array(TOTAL_DAYS).fill("");
                    const total = totalHoursAssigned(schedule);
                    const target = contractTargetHours(employee);
                    return (
                      <tr key={employee.id}>
                        <td className="border border-border px-2 py-1.5 text-xs font-medium text-foreground">
                          {employee.name}
                        </td>
                        {Array.from({ length: 7 }).map((_, i) => {
                          const dayIndex = startDay + i;
                          const code = schedule[dayIndex] ?? "";
                          return (
                            <td
                              key={dayIndex}
                              onClick={() => handleCellClick(employee.id, dayIndex)}
                              title={cellTitle(code)}
                              className={
                                "cursor-pointer select-none border border-border px-2 py-1.5 text-center text-xs font-semibold hover:opacity-80 " +
                                (CELL_COLOR_CLASSES[code] ?? "bg-background text-muted")
                              }
                            >
                              {cellLabel(code)}
                            </td>
                          );
                        })}
                        <td className="border border-border px-2 py-1.5 text-center text-xs text-muted">
                          {total}h / {target}h
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Card>

      <Card>
        <h2 className="mb-4 text-sm font-medium text-foreground">
          {t("scheduling.complianceTitle")}
        </h2>
        {complianceIssues.length === 0 ? (
          <p className="text-sm text-primary">{t("scheduling.complianceOk")}</p>
        ) : (
          <ul className="space-y-2">
            {complianceIssues.map((issue, index) => (
              <li key={index} className="flex items-start gap-2 text-sm">
                <Badge tone={issue.severity === "critical" ? "danger" : "warning"}>
                  {issue.severity === "critical"
                    ? t("scheduling.severityCritical")
                    : t("scheduling.severityWarning")}
                </Badge>
                <span className="text-foreground">
                  {issue.employeeName ? `${issue.employeeName} — ` : ""}
                  {issue.message}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
