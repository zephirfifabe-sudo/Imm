import "server-only";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { REST_CODE, TOTAL_DAYS, type ScheduleGrid, type SchedulingEmployee, type SchedulingSettings } from "./types";
import type { EmployeeSchedulingProfileInput } from "./profile-schema";

export async function upsertEmployeeSchedulingProfile(
  companyId: string,
  employeeId: string,
  input: EmployeeSchedulingProfileInput,
): Promise<{ ok: true } | { ok: false; error: "generic_error" }> {
  // Pas d'heures contractuelles renseignées: l'employé reste hors du
  // planificateur plutôt que de créer un profil avec des valeurs inventées.
  if (input.contractHoursPerWeek === undefined) {
    return { ok: true };
  }

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.from("employee_scheduling_profiles").upsert(
    {
      employee_id: employeeId,
      company_id: companyId,
      contract_hours_per_week: input.contractHoursPerWeek,
      contract_type: input.contractType ?? "CDI",
      day_only: input.dayOnly ?? false,
      night_only: input.nightOnly ?? false,
      min_nights_per_period: input.minNightsPerPeriod ?? 0,
      max_nights_per_period: input.maxNightsPerPeriod ?? 8,
      color: null,
    },
    { onConflict: "employee_id" },
  );

  return error ? { ok: false, error: "generic_error" } : { ok: true };
}

export async function getEmployeeSchedulingProfile(companyId: string, employeeId: string) {
  const supabase = await createSupabaseServerClient();
  const { data } = await supabase
    .from("employee_scheduling_profiles")
    .select("*")
    .eq("company_id", companyId)
    .eq("employee_id", employeeId)
    .maybeSingle();
  return data;
}

/** Employés éligibles au planificateur: actifs et dotés d'un profil de planification. */
export async function listSchedulingEmployees(companyId: string): Promise<SchedulingEmployee[]> {
  const supabase = await createSupabaseServerClient();
  const [{ data: profiles }, { data: employees }] = await Promise.all([
    supabase.from("employee_scheduling_profiles").select("*").eq("company_id", companyId),
    supabase
      .from("employees")
      .select("id, first_name, last_name")
      .eq("company_id", companyId)
      .eq("status", "ACTIVE"),
  ]);

  const employeesById = new Map((employees ?? []).map((e) => [e.id, e]));

  return (profiles ?? [])
    .filter((profile) => employeesById.has(profile.employee_id))
    .map((profile) => {
      const employee = employeesById.get(profile.employee_id)!;
      return {
        id: profile.employee_id,
        name: `${employee.first_name} ${employee.last_name}`,
        contractHoursPerWeek: Number(profile.contract_hours_per_week),
        dayOnly: profile.day_only,
        nightOnly: profile.night_only,
        minNightsPerPeriod: profile.min_nights_per_period,
        maxNightsPerPeriod: profile.max_nights_per_period,
      };
    });
}

function computePeriodEnd(periodStart: string): string {
  const start = new Date(`${periodStart}T00:00:00.000Z`);
  const end = new Date(start.getTime() + (TOTAL_DAYS - 1) * 86_400_000);
  return end.toISOString().slice(0, 10);
}

export async function createSchedulePeriod(
  companyId: string,
  input: { name: string; periodStart: string; settings: SchedulingSettings },
): Promise<{ ok: true; id: string } | { ok: false; error: "generic_error" }> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase
    .from("schedule_periods")
    .insert({
      company_id: companyId,
      name: input.name,
      period_start: input.periodStart,
      period_end: computePeriodEnd(input.periodStart),
      settings: input.settings,
    })
    .select("id")
    .single();

  if (error || !data) {
    return { ok: false, error: "generic_error" };
  }
  return { ok: true, id: data.id };
}

export async function listSchedulePeriods(companyId: string) {
  const supabase = await createSupabaseServerClient();
  const { data } = await supabase
    .from("schedule_periods")
    .select("*")
    .eq("company_id", companyId)
    .order("period_start", { ascending: false });
  return data ?? [];
}

export async function getSchedulePeriod(companyId: string, periodId: string) {
  const supabase = await createSupabaseServerClient();
  const { data } = await supabase
    .from("schedule_periods")
    .select("*")
    .eq("company_id", companyId)
    .eq("id", periodId)
    .maybeSingle();
  return data;
}

export async function updateSchedulePeriodSettings(
  companyId: string,
  periodId: string,
  settings: SchedulingSettings,
): Promise<{ ok: true } | { ok: false; error: "generic_error" }> {
  const supabase = await createSupabaseServerClient();
  const { error } = await supabase
    .from("schedule_periods")
    .update({ settings })
    .eq("company_id", companyId)
    .eq("id", periodId);
  return error ? { ok: false, error: "generic_error" } : { ok: true };
}

export async function deleteSchedulePeriod(companyId: string, periodId: string) {
  const supabase = await createSupabaseServerClient();
  await supabase.from("schedule_periods").delete().eq("company_id", companyId).eq("id", periodId);
}

export async function getScheduleGrid(
  companyId: string,
  periodId: string,
  employees: SchedulingEmployee[],
): Promise<ScheduleGrid> {
  const supabase = await createSupabaseServerClient();
  const { data } = await supabase
    .from("schedule_shifts")
    .select("employee_id, day_index, code")
    .eq("company_id", companyId)
    .eq("schedule_period_id", periodId);

  const grid: ScheduleGrid = {};
  for (const employee of employees) {
    grid[employee.id] = new Array(TOTAL_DAYS).fill(REST_CODE);
  }
  for (const row of data ?? []) {
    if (grid[row.employee_id]) {
      grid[row.employee_id][row.day_index] = row.code as ScheduleGrid[string][number];
    }
  }
  return grid;
}

/** Remplace entièrement les cases d'une période (utilisé après une génération). */
export async function replaceScheduleGrid(
  companyId: string,
  periodId: string,
  grid: ScheduleGrid,
): Promise<{ ok: true } | { ok: false; error: "generic_error" }> {
  const supabase = await createSupabaseServerClient();

  const { error: deleteError } = await supabase
    .from("schedule_shifts")
    .delete()
    .eq("company_id", companyId)
    .eq("schedule_period_id", periodId);
  if (deleteError) return { ok: false, error: "generic_error" };

  const rows = Object.entries(grid).flatMap(([employeeId, schedule]) =>
    schedule
      .map((code, dayIndex) => ({ code, dayIndex }))
      .filter(({ code }) => code !== REST_CODE)
      .map(({ code, dayIndex }) => ({
        schedule_period_id: periodId,
        employee_id: employeeId,
        company_id: companyId,
        day_index: dayIndex,
        code,
        locked: false,
      })),
  );

  if (rows.length === 0) return { ok: true };

  const { error: insertError } = await supabase.from("schedule_shifts").insert(rows);
  return insertError ? { ok: false, error: "generic_error" } : { ok: true };
}

export async function setScheduleShiftCell(
  companyId: string,
  periodId: string,
  employeeId: string,
  dayIndex: number,
  code: string,
): Promise<{ ok: true } | { ok: false; error: "generic_error" }> {
  const supabase = await createSupabaseServerClient();

  if (code === REST_CODE) {
    const { error } = await supabase
      .from("schedule_shifts")
      .delete()
      .eq("company_id", companyId)
      .eq("schedule_period_id", periodId)
      .eq("employee_id", employeeId)
      .eq("day_index", dayIndex);
    return error ? { ok: false, error: "generic_error" } : { ok: true };
  }

  const { error } = await supabase.from("schedule_shifts").upsert(
    {
      schedule_period_id: periodId,
      employee_id: employeeId,
      company_id: companyId,
      day_index: dayIndex,
      code,
      locked: false,
    },
    { onConflict: "schedule_period_id,employee_id,day_index" },
  );
  return error ? { ok: false, error: "generic_error" } : { ok: true };
}
