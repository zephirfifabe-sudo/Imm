"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { createSupabaseServerClient } from "@/lib/supabase/server";

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

export type EmployeeLoginState = { error?: string } | undefined;

export async function employeeLoginAction(
  _prevState: EmployeeLoginState,
  formData: FormData,
): Promise<EmployeeLoginState> {
  const parsed = loginSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
  });

  if (!parsed.success) {
    return { error: "invalid_credentials" };
  }

  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.signInWithPassword(parsed.data);

  if (error || !data.user) {
    return { error: "invalid_credentials" };
  }

  // Un compte Auth valide n'est pas forcément un compte employé (ex: un
  // ADMIN qui se trompe d'écran de connexion) — sans profil `employees`
  // correspondant, on referme immédiatement la session ouverte par erreur.
  const { data: employee } = await supabase
    .from("employees")
    .select("id")
    .eq("auth_user_id", data.user.id)
    .maybeSingle();

  if (!employee) {
    await supabase.auth.signOut();
    return { error: "invalid_credentials" };
  }

  redirect("/employee/schedule");
}

export async function employeeLogoutAction() {
  const supabase = await createSupabaseServerClient();
  await supabase.auth.signOut();
  redirect("/employee/login");
}
