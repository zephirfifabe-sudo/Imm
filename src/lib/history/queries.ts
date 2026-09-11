import "server-only";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { summarizeDay, type Anomaly } from "@/lib/timeclock/summary";
import type { TimeEntry } from "@/types/database";

export type HistoryDayGroup = {
  employeeId: string;
  employeeName: string;
  dateKey: string;
  entries: TimeEntry[];
  workedMinutes: number;
  breakMinutes: number;
  anomalies: Anomaly[];
};

function dateKeyOf(isoString: string): string {
  // Clé de jour civil basée sur le fuseau du serveur — voir la limite déjà
  // documentée dans summarizeDay pour les équipes qui chevauchent minuit.
  return new Date(isoString).toISOString().slice(0, 10);
}

export async function getHistory(
  companyId: string,
  filters: { employeeId?: string; from: Date; to: Date },
): Promise<HistoryDayGroup[]> {
  const supabase = await createSupabaseServerClient();

  const rangeStart = new Date(filters.from);
  rangeStart.setHours(0, 0, 0, 0);
  const rangeEnd = new Date(filters.to);
  rangeEnd.setHours(23, 59, 59, 999);

  let query = supabase
    .from("employees")
    .select("id, first_name, last_name")
    .eq("company_id", companyId);
  if (filters.employeeId) {
    query = query.eq("id", filters.employeeId);
  }
  const { data: employees } = await query;
  const employeeNameById = new Map(
    (employees ?? []).map((e) => [e.id, `${e.first_name} ${e.last_name}`]),
  );

  let entriesQuery = supabase
    .from("time_entries")
    .select("*")
    .eq("company_id", companyId)
    .gte("occurred_at", rangeStart.toISOString())
    .lte("occurred_at", rangeEnd.toISOString())
    .order("occurred_at", { ascending: true });
  if (filters.employeeId) {
    entriesQuery = entriesQuery.eq("employee_id", filters.employeeId);
  }
  const { data: entries } = await entriesQuery;

  const groups = new Map<string, TimeEntry[]>();
  for (const entry of entries ?? []) {
    const key = `${entry.employee_id}__${dateKeyOf(entry.occurred_at)}`;
    const list = groups.get(key) ?? [];
    list.push(entry);
    groups.set(key, list);
  }

  const todayKey = new Date().toISOString().slice(0, 10);

  const result: HistoryDayGroup[] = [];
  for (const [key, groupEntries] of groups) {
    const [employeeId, dateKey] = key.split("__");
    const summary = summarizeDay(groupEntries, { isPastDay: dateKey < todayKey });
    result.push({
      employeeId,
      employeeName: employeeNameById.get(employeeId) ?? "—",
      dateKey,
      entries: groupEntries,
      workedMinutes: summary.workedMinutes,
      breakMinutes: summary.breakMinutes,
      anomalies: summary.anomalies,
    });
  }

  result.sort((a, b) =>
    a.dateKey === b.dateKey
      ? a.employeeName.localeCompare(b.employeeName)
      : b.dateKey.localeCompare(a.dateKey),
  );

  return result;
}
