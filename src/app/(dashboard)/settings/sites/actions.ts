"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { requireAdmin } from "@/lib/auth/current-user";

const createSiteSchema = z.object({
  name: z.string().trim().min(2).max(200),
  address: z.string().trim().max(500).optional().or(z.literal("")),
});

export type CreateSiteState =
  | { ok: true }
  | { ok: false; error: "invalid_input" | "generic_error" }
  | undefined;

export async function createSiteAction(
  _prevState: CreateSiteState,
  formData: FormData,
): Promise<CreateSiteState> {
  const { company } = await requireAdmin();

  const parsed = createSiteSchema.safeParse({
    name: formData.get("name"),
    address: formData.get("address"),
  });

  if (!parsed.success) {
    return { ok: false, error: "invalid_input" };
  }

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.from("sites").insert({
    company_id: company.id,
    name: parsed.data.name,
    address: parsed.data.address || null,
  });

  if (error) {
    return { ok: false, error: "generic_error" };
  }

  revalidatePath("/settings/sites");
  return { ok: true };
}

export async function deleteSiteAction(siteId: string) {
  const { company } = await requireAdmin();

  const supabase = await createSupabaseServerClient();
  await supabase
    .from("sites")
    .delete()
    .eq("id", siteId)
    .eq("company_id", company.id);

  revalidatePath("/settings/sites");
}
