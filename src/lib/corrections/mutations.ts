import "server-only";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { createSupabaseServiceRoleClient } from "@/lib/supabase/service-role";

export type CorrectTimeEntryResult =
  | { ok: true }
  | { ok: false; error: "not_found" | "generic_error" };

/**
 * Corrige l'heure d'un pointage. L'autorisation (l'auteur appartient bien à
 * l'entreprise du pointage) est vérifiée ici via le client lié à la
 * session avant tout appel privilégié; l'écriture elle-même (mise à jour
 * du pointage + ligne de correction + entrée d'audit, toutes les trois
 * ensemble) passe par `correct_time_entry` en service_role pour rester
 * atomique.
 */
export async function correctTimeEntry(params: {
  companyId: string;
  correctedByUserId: string;
  timeEntryId: string;
  newOccurredAt: Date;
  reason: string;
}): Promise<CorrectTimeEntryResult> {
  const supabase = await createSupabaseServerClient();

  const { data: entry } = await supabase
    .from("time_entries")
    .select("id")
    .eq("id", params.timeEntryId)
    .eq("company_id", params.companyId)
    .maybeSingle();

  if (!entry) {
    return { ok: false, error: "not_found" };
  }

  const serviceRole = createSupabaseServiceRoleClient();
  const { error } = await serviceRole.rpc("correct_time_entry", {
    p_time_entry_id: params.timeEntryId,
    p_company_id: params.companyId,
    p_new_occurred_at: params.newOccurredAt.toISOString(),
    p_reason: params.reason,
    p_corrected_by: params.correctedByUserId,
  });

  if (error) {
    console.error("correctTimeEntry: correct_time_entry RPC failed", {
      companyId: params.companyId,
      timeEntryId: params.timeEntryId,
      error,
    });
    return { ok: false, error: "generic_error" };
  }

  return { ok: true };
}
