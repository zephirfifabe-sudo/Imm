import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import type { AppUser, Company } from "@/types/database";

/**
 * Charge l'utilisateur employeur courant (ligne `users`) et son entreprise.
 * Redirige vers /login si aucune session, ou si la session n'a pas encore
 * de ligne `users` associée (compte en cours d'onboarding).
 */
export async function requireCurrentUser(): Promise<{
  user: AppUser;
  company: Company;
}> {
  const supabase = await createSupabaseServerClient();
  const { data: authData } = await supabase.auth.getUser();

  if (!authData.user) {
    redirect("/login");
  }

  const { data: user } = await supabase
    .from("users")
    .select("*")
    .eq("auth_user_id", authData.user.id)
    .single();

  if (!user) {
    redirect("/login");
  }

  const { data: company } = await supabase
    .from("companies")
    .select("*")
    .eq("id", user.company_id)
    .single();

  if (!company) {
    redirect("/login");
  }

  return { user, company };
}
