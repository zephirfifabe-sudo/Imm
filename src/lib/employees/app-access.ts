import "server-only";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { createSupabaseServiceRoleClient } from "@/lib/supabase/service-role";
import { env } from "@/lib/config/env";

export type InviteEmployeeToAppResult =
  | { ok: true }
  | { ok: false; error: "no_email" | "already_invited" | "email_already_used" | "not_found" | "generic_error" };

/**
 * Invite un employé à créer son compte personnel (accès à son horaire
 * depuis son téléphone). Distinct de `inviteTeamMember`: un employé n'a
 * jamais de ligne `users` ni de rôle ADMIN/MANAGER, seulement un compte
 * Auth relié à sa ligne `employees` via `auth_user_id`.
 */
export async function inviteEmployeeToApp(
  companyId: string,
  employeeId: string,
): Promise<InviteEmployeeToAppResult> {
  const supabase = await createSupabaseServerClient();

  const { data: employee } = await supabase
    .from("employees")
    .select("id, email, auth_user_id")
    .eq("id", employeeId)
    .eq("company_id", companyId)
    .maybeSingle();

  if (!employee) {
    return { ok: false, error: "not_found" };
  }
  if (!employee.email) {
    return { ok: false, error: "no_email" };
  }
  if (employee.auth_user_id) {
    return { ok: false, error: "already_invited" };
  }

  const serviceRole = createSupabaseServiceRoleClient();
  const { data: invited, error: inviteError } = await serviceRole.auth.admin.inviteUserByEmail(
    employee.email,
    { redirectTo: `${env.appUrl}/auth/callback` },
  );

  if (inviteError || !invited.user) {
    // Cause la plus probable: cet e-mail correspond déjà à un compte Auth
    // (un compte employeur `users`, ou un autre employé) — les comptes
    // partagent le même espace Supabase Auth, un e-mail y est unique.
    return { ok: false, error: "email_already_used" };
  }

  const { error: updateError } = await supabase
    .from("employees")
    .update({ auth_user_id: invited.user.id })
    .eq("id", employeeId)
    .eq("company_id", companyId);

  if (updateError) {
    await serviceRole.auth.admin.deleteUser(invited.user.id);
    return { ok: false, error: "generic_error" };
  }

  return { ok: true };
}

export async function revokeEmployeeAppAccess(
  companyId: string,
  employeeId: string,
): Promise<{ ok: true } | { ok: false; error: "not_found" | "generic_error" }> {
  const supabase = await createSupabaseServerClient();

  const { data: employee } = await supabase
    .from("employees")
    .select("id, auth_user_id")
    .eq("id", employeeId)
    .eq("company_id", companyId)
    .maybeSingle();

  if (!employee) {
    return { ok: false, error: "not_found" };
  }
  if (!employee.auth_user_id) {
    return { ok: true };
  }

  const serviceRole = createSupabaseServiceRoleClient();
  const { error } = await serviceRole.auth.admin.deleteUser(employee.auth_user_id);

  // La suppression du compte Auth déclenche `on delete set null`: la ligne
  // `employees` n'a rien de plus à faire, et l'e-mail redevient disponible
  // pour une future invitation.
  return error ? { ok: false, error: "generic_error" } : { ok: true };
}
