"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { createCompanyWithAdmin } from "@/lib/company/onboarding";

const signupSchema = z.object({
  companyName: z.string().trim().min(2).max(200),
  firstName: z.string().trim().min(1).max(100),
  lastName: z.string().trim().min(1).max(100),
  email: z.string().trim().email(),
  password: z.string().min(8).max(72),
});

export type SignupActionState =
  | { error: "invalid_input" | "email_taken" | "generic_error" }
  | undefined;

export async function signupAction(
  _prevState: SignupActionState,
  formData: FormData,
): Promise<SignupActionState> {
  const parsed = signupSchema.safeParse({
    companyName: formData.get("companyName"),
    firstName: formData.get("firstName"),
    lastName: formData.get("lastName"),
    email: formData.get("email"),
    password: formData.get("password"),
  });

  if (!parsed.success) {
    return { error: "invalid_input" };
  }

  const result = await createCompanyWithAdmin(parsed.data);

  if (!result.ok) {
    return { error: result.error };
  }

  const supabase = await createSupabaseServerClient();
  const { error: signInError } = await supabase.auth.signInWithPassword({
    email: parsed.data.email,
    password: parsed.data.password,
  });

  if (signInError) {
    return { error: "generic_error" };
  }

  redirect("/dashboard");
}
