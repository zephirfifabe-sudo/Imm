import "server-only";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getPresenceState, summarizeDay, type PresenceState } from "@/lib/timeclock/summary";
import type { Employee, TimeEntry } from "@/types/database";

export type PresenceRow = {
  employee: Employee;
  state: PresenceState;
};

export type RecentEntry = TimeEntry & { employeeName: string };

export type DashboardData = {
  presence: PresenceRow[];
  presentCount: number;
  onBreakCount: number;
  absentCount: number;
  recentEntries: RecentEntry[];
  anomalyCount: number;
};

/**
 * Vue "aujourd'hui" du dashboard: qui est présent/en pause/absent, les
 * derniers pointages et le nombre d'anomalies. Calculée à chaque chargement
 * de page (pas de push temps réel pour l'instant — voir README).
 *
 * La fenêtre de recherche remonte à 2 jours pour que le dernier pointage
 * d'un employé qui travaille de nuit (arrivée hier soir) soit quand même
 * pris en compte pour déterminer sa présence actuelle.
 */
export async function getDashboardData(companyId: string): Promise<DashboardData> {
  const supabase = await createSupabaseServerClient();

  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const lookbackStart = new Date(startOfToday);
  lookbackStart.setDate(lookbackStart.getDate() - 2);

  const [{ data: employees }, { data: entries }] = await Promise.all([
    supabase
      .from("employees")
      .select("*")
      .eq("company_id", companyId)
      .eq("status", "ACTIVE"),
    supabase
      .from("time_entries")
      .select("*")
      .eq("company_id", companyId)
      .gte("occurred_at", lookbackStart.toISOString())
      .order("occurred_at", { ascending: false }),
  ]);

  const entriesByEmployee = new Map<string, TimeEntry[]>();
  for (const entry of entries ?? []) {
    const list = entriesByEmployee.get(entry.employee_id) ?? [];
    list.push(entry);
    entriesByEmployee.set(entry.employee_id, list);
  }

  const presence: PresenceRow[] = (employees ?? []).map((employee) => {
    const employeeEntries = entriesByEmployee.get(employee.id) ?? [];
    const lastEntry = employeeEntries[0]; // déjà trié desc par la requête
    return { employee, state: getPresenceState(lastEntry?.type ?? null) };
  });

  const presentCount = presence.filter((p) => p.state === "PRESENT").length;
  const onBreakCount = presence.filter((p) => p.state === "ON_BREAK").length;
  const absentCount = presence.length - presentCount - onBreakCount;

  const employeeNameById = new Map(
    (employees ?? []).map((e) => [e.id, `${e.first_name} ${e.last_name}`]),
  );

  const todaysEntries = (entries ?? []).filter(
    (entry) => new Date(entry.occurred_at) >= startOfToday,
  );

  let anomalyCount = 0;
  for (const employeeEntries of entriesByEmployee.values()) {
    const todaysForEmployee = employeeEntries.filter(
      (entry) => new Date(entry.occurred_at) >= startOfToday,
    );
    if (todaysForEmployee.length === 0) continue;
    anomalyCount += summarizeDay(todaysForEmployee, { isPastDay: false }).anomalies.length;
  }

  const recentEntries: RecentEntry[] = todaysEntries.slice(0, 20).map((entry) => ({
    ...entry,
    employeeName: employeeNameById.get(entry.employee_id) ?? "—",
  }));

  return { presence, presentCount, onBreakCount, absentCount, recentEntries, anomalyCount };
}
