import "server-only";
import { createSupabaseServerClient } from "@/lib/supabase/server";

/**
 * Logique pure de comparaison, séparée des accès base pour rester
 * facilement testable. `null` signifie "limite inconnue" (aucun
 * abonnement rattaché) — on ne bloque pas dans ce cas plutôt que
 * d'inventer une limite arbitraire.
 */
export function isAtOrOverEmployeeLimit(
  currentActiveCount: number,
  maxEmployees: number | null,
): boolean {
  if (maxEmployees === null) return false;
  return currentActiveCount >= maxEmployees;
}

export async function getCompanyEmployeeLimit(
  companyId: string,
): Promise<number | null> {
  const supabase = await createSupabaseServerClient();

  const { data: subscription } = await supabase
    .from("subscriptions")
    .select("plan_id")
    .eq("company_id", companyId)
    .maybeSingle();

  if (!subscription) return null;

  const { data: plan } = await supabase
    .from("plans")
    .select("max_employees")
    .eq("id", subscription.plan_id)
    .maybeSingle();

  return plan?.max_employees ?? null;
}

export async function countActiveEmployees(companyId: string): Promise<number> {
  const supabase = await createSupabaseServerClient();

  const { count } = await supabase
    .from("employees")
    .select("id", { count: "exact", head: true })
    .eq("company_id", companyId)
    .eq("status", "ACTIVE");

  return count ?? 0;
}
