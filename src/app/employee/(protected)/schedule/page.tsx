import { requireCurrentEmployee } from "@/lib/auth/current-employee";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { Card } from "@/components/ui/Card";
import { cellTitle, dateForDay } from "@/lib/scheduling/presentation";
import { totalHoursAssigned } from "@/lib/scheduling/engine";
import { TOTAL_DAYS, NUM_WEEKS, type ShiftCode } from "@/lib/scheduling/types";
import type { SchedulePeriod } from "@/types/database";
import { getTranslator } from "@/i18n";
import { PeriodSelect } from "./PeriodSelect";

const t = getTranslator();

function pickDefaultPeriod(periods: SchedulePeriod[]): SchedulePeriod | undefined {
  const todayIso = new Date().toISOString().slice(0, 10);
  const sorted = [...periods].sort((a, b) => a.period_start.localeCompare(b.period_start));
  const currentOrNext = sorted.find((p) => p.period_end >= todayIso);
  return currentOrNext ?? sorted.at(-1);
}

export default async function EmployeeSchedulePage({
  searchParams,
}: {
  searchParams: Promise<{ period?: string }>;
}) {
  const { period: periodIdParam } = await searchParams;
  const { employee } = await requireCurrentEmployee();
  const supabase = await createSupabaseServerClient();

  const { data: periods } = await supabase
    .from("schedule_periods")
    .select("*")
    .eq("company_id", employee.company_id)
    .order("period_start", { ascending: false });

  const allPeriods = periods ?? [];
  const selectedPeriod =
    (periodIdParam && allPeriods.find((p) => p.id === periodIdParam)) ??
    pickDefaultPeriod(allPeriods);

  const { data: shifts } = selectedPeriod
    ? await supabase
        .from("schedule_shifts")
        .select("day_index, code")
        .eq("employee_id", employee.id)
        .eq("schedule_period_id", selectedPeriod.id)
    : { data: [] };

  const schedule: ShiftCode[] = new Array(TOTAL_DAYS).fill("");
  for (const shift of shifts ?? []) {
    schedule[shift.day_index] = shift.code as ShiftCode;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">
          {t("employee.scheduleTitle", { name: employee.first_name })}
        </h1>
      </div>

      {allPeriods.length === 0 || !selectedPeriod ? (
        <Card>
          <p className="text-sm text-muted">{t("employee.scheduleEmpty")}</p>
        </Card>
      ) : (
        <>
          {allPeriods.length > 1 && (
            <PeriodSelect periods={allPeriods} selectedId={selectedPeriod.id} />
          )}

          <Card>
            <p className="mb-4 text-sm text-muted">
              {new Date(`${selectedPeriod.period_start}T00:00:00.000Z`).toLocaleDateString("fr-BE", {
                timeZone: "UTC",
              })}{" "}
              –{" "}
              {new Date(`${selectedPeriod.period_end}T00:00:00.000Z`).toLocaleDateString("fr-BE", {
                timeZone: "UTC",
              })}
            </p>

            <div className="space-y-4">
              {Array.from({ length: NUM_WEEKS }).map((_, week) => (
                <div key={week}>
                  <p className="mb-1 text-xs font-medium text-muted">
                    {t("scheduling.weekLabel", { number: week + 1 })}
                  </p>
                  <div className="grid grid-cols-7 gap-1.5">
                    {Array.from({ length: 7 }).map((_, day) => {
                      const dayIndex = week * 7 + day;
                      const code = schedule[dayIndex];
                      const date = dateForDay(
                        new Date(`${selectedPeriod.period_start}T00:00:00.000Z`),
                        dayIndex,
                      );
                      return (
                        <div
                          key={dayIndex}
                          className="rounded-lg border border-border p-2 text-center"
                          title={cellTitle(code)}
                        >
                          <p className="text-[11px] text-muted">
                            {date.toLocaleDateString("fr-BE", {
                              day: "2-digit",
                              month: "2-digit",
                              timeZone: "UTC",
                            })}
                          </p>
                          <p className="mt-1 text-sm font-semibold text-foreground">
                            {code === "" ? "–" : code}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            <p className="mt-4 text-sm text-muted">
              {t("employee.totalHours", { hours: String(totalHoursAssigned(schedule)) })}
            </p>
          </Card>
        </>
      )}
    </div>
  );
}
