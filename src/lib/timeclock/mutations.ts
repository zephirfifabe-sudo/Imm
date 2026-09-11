import "server-only";
import { createSupabaseServiceRoleClient } from "@/lib/supabase/service-role";
import { isValidNextAction } from "./service";
import type { TimeEntry, TimeEntryType, TimeEntrySource } from "@/types/database";

export async function getLastEntryType(
  employeeId: string,
): Promise<TimeEntryType | null> {
  const serviceRole = createSupabaseServiceRoleClient();
  const { data } = await serviceRole
    .from("time_entries")
    .select("type")
    .eq("employee_id", employeeId)
    .order("occurred_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  return data?.type ?? null;
}

export type RecordClockResult =
  | { ok: true; entry: TimeEntry }
  | { ok: false; error: "invalid_transition" | "not_found" | "generic_error" };

/**
 * Enregistre un pointage. `event_id` est fourni par le terminal (UUID
 * généré côté client) et garantit l'idempotence: un même événement envoyé
 * deux fois (retry réseau, ou rejeu depuis la file hors-ligne) ne crée
 * qu'une seule ligne. La transition est toujours revérifiée ici à partir
 * du dernier pointage réel en base — le type demandé par le terminal
 * n'est jamais appliqué aveuglément.
 *
 * `occurredAt` est l'instant réel du pointage, capturé côté terminal au
 * moment de l'action (pas au moment de l'écriture en base): un pointage
 * mis en file d'attente hors-ligne puis synchronisé plus tard doit garder
 * son heure réelle, jamais l'heure de synchronisation.
 */
export async function recordClockEvent(params: {
  companyId: string;
  siteId: string | null;
  employeeId: string;
  terminalId: string;
  type: TimeEntryType;
  source: TimeEntrySource;
  eventId: string;
  occurredAt: string;
}): Promise<RecordClockResult> {
  const serviceRole = createSupabaseServiceRoleClient();

  const { data: existing } = await serviceRole
    .from("time_entries")
    .select("*")
    .eq("event_id", params.eventId)
    .maybeSingle();

  if (existing) {
    return { ok: true, entry: existing };
  }

  // Le terminal ne fait jamais foi seul sur l'identité de l'employé: on
  // revérifie ici qu'il appartient bien à l'entreprise du terminal et
  // qu'il est actif, avant d'enregistrer quoi que ce soit.
  const { data: employee } = await serviceRole
    .from("employees")
    .select("id")
    .eq("id", params.employeeId)
    .eq("company_id", params.companyId)
    .eq("status", "ACTIVE")
    .maybeSingle();

  if (!employee) {
    return { ok: false, error: "not_found" };
  }

  const lastType = await getLastEntryType(params.employeeId);
  if (!isValidNextAction(lastType, params.type)) {
    return { ok: false, error: "invalid_transition" };
  }

  const { data, error } = await serviceRole
    .from("time_entries")
    .insert({
      event_id: params.eventId,
      company_id: params.companyId,
      site_id: params.siteId,
      employee_id: params.employeeId,
      terminal_id: params.terminalId,
      type: params.type,
      source: params.source,
      occurred_at: params.occurredAt,
    })
    .select("*")
    .single();

  if (error || !data) {
    return { ok: false, error: "generic_error" };
  }

  return { ok: true, entry: data };
}
