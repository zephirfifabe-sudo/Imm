import "server-only";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { createSupabaseServiceRoleClient } from "@/lib/supabase/service-role";
import { env } from "@/lib/config/env";
import type { UserRole } from "@/types/database";

export type InviteTeamMemberInput = {
  companyId: string;
  email: string;
  firstName: string;
  lastName: string;
  role: UserRole;
};

export type InviteTeamMemberResult =
  | { ok: true }
  | { ok: false; error: "email_taken_in_company" | "generic_error" };

/**
 * Invite un nouvel utilisateur employeur. Seule la création du compte Auth
 * (et l'envoi de l'invitation) nécessite le service_role; l'insertion de la
 * ligne `users` passe par le client lié à la session de l'administrateur,
 * pour rester protégée par RLS en profondeur.
 */
export async function inviteTeamMember(
  input: InviteTeamMemberInput,
): Promise<InviteTeamMemberResult> {
  const supabase = await createSupabaseServerClient();

  const { data: existing } = await supabase
    .from("users")
    .select("id")
    .eq("company_id", input.companyId)
    .eq("email", input.email)
    .maybeSingle();

  if (existing) {
    return { ok: false, error: "email_taken_in_company" };
  }

  const serviceRole = createSupabaseServiceRoleClient();
  const { data: invited, error: inviteError } = await serviceRole.auth.admin.inviteUserByEmail(
    input.email,
    { redirectTo: `${env.appUrl}/auth/callback` },
  );

  if (inviteError || !invited.user) {
    return { ok: false, error: "generic_error" };
  }

  const { error: insertError } = await supabase.from("users").insert({
    auth_user_id: invited.user.id,
    company_id: input.companyId,
    email: input.email,
    first_name: input.firstName,
    last_name: input.lastName,
    role: input.role,
  });

  if (insertError) {
    await serviceRole.auth.admin.deleteUser(invited.user.id);
    return { ok: false, error: "generic_error" };
  }

  return { ok: true };
}

export type UpdateTeamMemberRoleResult =
  | { ok: true }
  | { ok: false; error: "not_found" | "last_admin" | "generic_error" };

export async function updateTeamMemberRole(params: {
  companyId: string;
  targetUserId: string;
  newRole: UserRole;
}): Promise<UpdateTeamMemberRoleResult> {
  const supabase = await createSupabaseServerClient();

  const { data: target } = await supabase
    .from("users")
    .select("id, role")
    .eq("id", params.targetUserId)
    .eq("company_id", params.companyId)
    .maybeSingle();

  if (!target) {
    return { ok: false, error: "not_found" };
  }

  if (target.role === "ADMIN" && params.newRole !== "ADMIN") {
    const remainingAdmins = await countAdmins(params.companyId, supabase);
    if (remainingAdmins <= 1) {
      return { ok: false, error: "last_admin" };
    }
  }

  const { error } = await supabase
    .from("users")
    .update({ role: params.newRole })
    .eq("id", params.targetUserId)
    .eq("company_id", params.companyId);

  if (error) {
    return { ok: false, error: "generic_error" };
  }

  return { ok: true };
}

export type RemoveTeamMemberResult =
  | { ok: true }
  | { ok: false; error: "not_found" | "last_admin" | "generic_error" };

export async function removeTeamMember(params: {
  companyId: string;
  targetUserId: string;
}): Promise<RemoveTeamMemberResult> {
  const supabase = await createSupabaseServerClient();

  const { data: target } = await supabase
    .from("users")
    .select("id, role, auth_user_id")
    .eq("id", params.targetUserId)
    .eq("company_id", params.companyId)
    .maybeSingle();

  if (!target) {
    return { ok: false, error: "not_found" };
  }

  if (target.role === "ADMIN") {
    const remainingAdmins = await countAdmins(params.companyId, supabase);
    if (remainingAdmins <= 1) {
      return { ok: false, error: "last_admin" };
    }
  }

  const serviceRole = createSupabaseServiceRoleClient();
  const { error } = await serviceRole.auth.admin.deleteUser(
    target.auth_user_id,
  );

  if (error) {
    return { ok: false, error: "generic_error" };
  }

  // La suppression de l'utilisateur Auth déclenche `on delete cascade` sur
  // users.auth_user_id: la ligne `users` est déjà supprimée à ce stade.
  return { ok: true };
}

async function countAdmins(
  companyId: string,
  supabase: Awaited<ReturnType<typeof createSupabaseServerClient>>,
): Promise<number> {
  const { count } = await supabase
    .from("users")
    .select("id", { count: "exact", head: true })
    .eq("company_id", companyId)
    .eq("role", "ADMIN");

  return count ?? 0;
}
