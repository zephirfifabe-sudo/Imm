import "server-only";
import { createSupabaseServiceRoleClient } from "@/lib/supabase/service-role";

export type OnboardingInput = {
  companyName: string;
  firstName: string;
  lastName: string;
  email: string;
  password: string;
};

export type OnboardingErrorCode = "email_taken" | "generic_error";

export type OnboardingResult =
  | { ok: true }
  | { ok: false; error: OnboardingErrorCode };

/**
 * Crée l'entreprise et son premier utilisateur ADMIN.
 *
 * Aucune ligne `users` n'existe encore pour cette session: les policies RLS
 * ne peuvent pas s'appliquer, cette opération doit donc passer par le
 * service_role. L'insertion company+user reste atomique via la fonction
 * Postgres `create_company_with_admin` (une seule transaction serveur).
 *
 * Si l'insertion échoue après la création du compte Auth, le compte est
 * supprimé pour éviter un compte orphelin sans entreprise.
 */
export async function createCompanyWithAdmin(
  input: OnboardingInput,
): Promise<OnboardingResult> {
  const serviceRole = createSupabaseServiceRoleClient();

  const { data: created, error: createUserError } =
    await serviceRole.auth.admin.createUser({
      email: input.email,
      password: input.password,
      email_confirm: true,
    });

  if (createUserError || !created.user) {
    const isEmailTaken =
      createUserError?.code === "email_exists" ||
      createUserError?.status === 422;
    if (!isEmailTaken) {
      console.error("createCompanyWithAdmin: auth.admin.createUser failed", {
        error: createUserError,
      });
    }
    return { ok: false, error: isEmailTaken ? "email_taken" : "generic_error" };
  }

  const { error: onboardingError } = await serviceRole.rpc(
    "create_company_with_admin",
    {
      p_auth_user_id: created.user.id,
      p_email: input.email,
      p_company_name: input.companyName,
      p_first_name: input.firstName,
      p_last_name: input.lastName,
    },
  );

  if (onboardingError) {
    console.error("createCompanyWithAdmin: create_company_with_admin RPC failed, rolling back auth user", {
      authUserId: created.user.id,
      error: onboardingError,
    });
    const { error: rollbackError } = await serviceRole.auth.admin.deleteUser(
      created.user.id,
    );
    if (rollbackError) {
      console.error("createCompanyWithAdmin: rollback deleteUser also failed — orphaned auth user", {
        authUserId: created.user.id,
        error: rollbackError,
      });
    }
    return { ok: false, error: "generic_error" };
  }

  return { ok: true };
}
