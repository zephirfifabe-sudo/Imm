import "server-only";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { hashPin, pinMatchesHash } from "@/lib/employees/pin";
import {
  countActiveEmployees,
  getCompanyEmployeeLimit,
  isAtOrOverEmployeeLimit,
} from "@/lib/subscriptions/limits";
import type { EmployeeFormInput } from "@/lib/employees/schema";

export type EmployeeMutationError =
  | "duplicate_code"
  | "duplicate_pin"
  | "plan_limit_reached"
  | "generic_error";

async function hasReachedEmployeeLimit(companyId: string): Promise<boolean> {
  const [maxEmployees, activeCount] = await Promise.all([
    getCompanyEmployeeLimit(companyId),
    countActiveEmployees(companyId),
  ]);
  return isAtOrOverEmployeeLimit(activeCount, maxEmployees);
}

export type EmployeeMutationResult =
  | { ok: true; id: string }
  | { ok: false; error: EmployeeMutationError };

/**
 * Le PIN identifie directement l'employé au terminal: il doit donc être
 * unique au sein de l'entreprise. Le PIN est stocké hashé (bcrypt, salé),
 * ce qui empêche une recherche par égalité en base — avec au plus 50
 * employés par plan, comparer le PIN candidat à chaque hash existant reste
 * instantané et évite d'affaiblir le stockage pour gagner une contrainte
 * SQL.
 */
async function findEmployeeWithSamePin(
  supabase: Awaited<ReturnType<typeof createSupabaseServerClient>>,
  companyId: string,
  pin: string,
  excludeEmployeeId?: string,
): Promise<boolean> {
  const { data: candidates } = await supabase
    .from("employees")
    .select("id, pin_hash")
    .eq("company_id", companyId)
    .not("pin_hash", "is", null);

  for (const candidate of candidates ?? []) {
    if (candidate.id === excludeEmployeeId || !candidate.pin_hash) continue;
    if (await pinMatchesHash(pin, candidate.pin_hash)) {
      return true;
    }
  }

  return false;
}

export async function createEmployee(
  companyId: string,
  input: EmployeeFormInput,
): Promise<EmployeeMutationResult> {
  const supabase = await createSupabaseServerClient();

  if (await hasReachedEmployeeLimit(companyId)) {
    return { ok: false, error: "plan_limit_reached" };
  }

  if (input.pin && (await findEmployeeWithSamePin(supabase, companyId, input.pin))) {
    return { ok: false, error: "duplicate_pin" };
  }

  const { data, error } = await supabase
    .from("employees")
    .insert({
      company_id: companyId,
      site_id: input.siteId ?? null,
      internal_code: input.internalCode,
      first_name: input.firstName,
      last_name: input.lastName,
      email: input.email ?? null,
      job_title: input.jobTitle ?? null,
      nfc_token: input.nfcToken ?? null,
      pin_hash: input.pin ? await hashPin(input.pin) : null,
      status: "ACTIVE",
      qr_token: crypto.randomUUID(),
    })
    .select("id")
    .single();

  if (error || !data) {
    const isDuplicateCode = error?.code === "23505";
    return { ok: false, error: isDuplicateCode ? "duplicate_code" : "generic_error" };
  }

  return { ok: true, id: data.id };
}

export async function updateEmployee(
  companyId: string,
  employeeId: string,
  input: EmployeeFormInput,
): Promise<EmployeeMutationResult> {
  const supabase = await createSupabaseServerClient();

  if (
    input.pin &&
    (await findEmployeeWithSamePin(supabase, companyId, input.pin, employeeId))
  ) {
    return { ok: false, error: "duplicate_pin" };
  }

  const { error } = await supabase
    .from("employees")
    .update({
      site_id: input.siteId ?? null,
      internal_code: input.internalCode,
      first_name: input.firstName,
      last_name: input.lastName,
      email: input.email ?? null,
      job_title: input.jobTitle ?? null,
      nfc_token: input.nfcToken ?? null,
      ...(input.pin ? { pin_hash: await hashPin(input.pin) } : {}),
    })
    .eq("id", employeeId)
    .eq("company_id", companyId);

  if (error) {
    const isDuplicateCode = error.code === "23505";
    return { ok: false, error: isDuplicateCode ? "duplicate_code" : "generic_error" };
  }

  return { ok: true, id: employeeId };
}

export async function setEmployeeStatus(
  companyId: string,
  employeeId: string,
  status: "ACTIVE" | "INACTIVE",
): Promise<{ ok: true } | { ok: false; error: "plan_limit_reached" | "generic_error" }> {
  // Réactiver un employé augmente aussi le nombre d'actifs: la même limite
  // de plan s'applique, sinon elle serait contournable en désactivant puis
  // réactivant un employé.
  if (status === "ACTIVE" && (await hasReachedEmployeeLimit(companyId))) {
    return { ok: false, error: "plan_limit_reached" };
  }

  const supabase = await createSupabaseServerClient();

  const { error } = await supabase
    .from("employees")
    .update({ status })
    .eq("id", employeeId)
    .eq("company_id", companyId);

  return error ? { ok: false, error: "generic_error" } : { ok: true };
}

/**
 * Émet un nouveau token QR (ex: badge perdu ou compromis). L'ancien token
 * cesse immédiatement d'identifier l'employé.
 */
export async function regenerateQrToken(
  companyId: string,
  employeeId: string,
): Promise<{ ok: true } | { ok: false; error: "generic_error" }> {
  const supabase = await createSupabaseServerClient();

  const { error } = await supabase
    .from("employees")
    .update({ qr_token: crypto.randomUUID() })
    .eq("id", employeeId)
    .eq("company_id", companyId);

  return error ? { ok: false, error: "generic_error" } : { ok: true };
}
