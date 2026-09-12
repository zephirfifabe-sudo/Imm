import "server-only";
import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import type { Employee } from "@/types/database";

/**
 * Charge l'employé courant à partir de son compte personnel (distinct des
 * comptes employeur `users`). Redirige vers /employee/login si aucune
 * session, ou si la session ne correspond à aucun employé (ex: un ADMIN
 * connecté qui ouvrirait /employee par erreur).
 */
export async function requireCurrentEmployee(): Promise<{ employee: Employee }> {
  const supabase = await createSupabaseServerClient();
  const { data: authData } = await supabase.auth.getUser();

  if (!authData.user) {
    redirect("/employee/login");
  }

  const { data: employee } = await supabase
    .from("employees")
    .select("*")
    .eq("auth_user_id", authData.user.id)
    .maybeSingle();

  if (!employee) {
    redirect("/employee/login");
  }

  return { employee };
}
