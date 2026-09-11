import "server-only";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import type { TimeEntryCorrection } from "@/types/database";

/** Regroupe les corrections existantes par pointage, pour affichage en liste. */
export async function getCorrectionsForEntries(
  companyId: string,
  timeEntryIds: string[],
): Promise<Map<string, TimeEntryCorrection[]>> {
  if (timeEntryIds.length === 0) return new Map();

  const supabase = await createSupabaseServerClient();
  const { data } = await supabase
    .from("time_entry_corrections")
    .select("*")
    .eq("company_id", companyId)
    .in("time_entry_id", timeEntryIds)
    .order("created_at", { ascending: false });

  const map = new Map<string, TimeEntryCorrection[]>();
  for (const correction of data ?? []) {
    const list = map.get(correction.time_entry_id) ?? [];
    list.push(correction);
    map.set(correction.time_entry_id, list);
  }

  return map;
}
