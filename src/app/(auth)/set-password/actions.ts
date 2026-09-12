"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { createSupabaseServerClient } from "@/lib/supabase/server";

const setPasswordSchema = z.object({
  password: z.string().min(8).max(200),
});

export type SetPasswordState =
  | { ok: false; error: "invalid_input" | "no_session" | "generic_error" }
  | undefined;

/**
 * Termine une invitation (employeur ou employé): pose le mot de passe sur
 * le compte Auth déjà créé par `inviteUserByEmail`, puis renvoie vers
 * l'espace qui correspond au compte — jamais un choix laissé au client.
 */
export async function setPasswordAction(
  _prevState: SetPasswordState,
  formData: FormData,
): Promise<SetPasswordState> {
  const parsed = setPasswordSchema.safeParse({ password: formData.get("password") });
  if (!parsed.success) {
    return { ok: false, error: "invalid_input" };
  }

  const supabase = await createSupabaseServerClient();
  const { data: authData } = await supabase.auth.getUser();
  if (!authData.user) {
    return { ok: false, error: "no_session" };
  }

  const { error: updateError } = await supabase.auth.updateUser({
    password: parsed.data.password,
  });
  if (updateError) {
    return { ok: false, error: "generic_error" };
  }

  const { data: user } = await supabase
    .from("users")
    .select("id")
    .eq("auth_user_id", authData.user.id)
    .maybeSingle();
  if (user) {
    redirect("/dashboard");
  }

  const { data: employee } = await supabase
    .from("employees")
    .select("id")
    .eq("auth_user_id", authData.user.id)
    .maybeSingle();
  if (employee) {
    redirect("/employee/schedule");
  }

  redirect("/login");
}
