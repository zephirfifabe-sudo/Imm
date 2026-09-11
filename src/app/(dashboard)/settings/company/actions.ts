"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { requireAdmin } from "@/lib/auth/current-user";

const updateCompanySchema = z.object({
  name: z.string().trim().min(2).max(200),
  vatNumber: z.string().trim().max(50).optional().or(z.literal("")),
  address: z.string().trim().max(500).optional().or(z.literal("")),
});

export type UpdateCompanyState =
  | { ok: true }
  | { ok: false; error: "invalid_input" | "generic_error" }
  | undefined;

export async function updateCompanyAction(
  _prevState: UpdateCompanyState,
  formData: FormData,
): Promise<UpdateCompanyState> {
  const { company } = await requireAdmin();

  const parsed = updateCompanySchema.safeParse({
    name: formData.get("name"),
    vatNumber: formData.get("vatNumber"),
    address: formData.get("address"),
  });

  if (!parsed.success) {
    return { ok: false, error: "invalid_input" };
  }

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase
    .from("companies")
    .update({
      name: parsed.data.name,
      vat_number: parsed.data.vatNumber || null,
      address: parsed.data.address || null,
    })
    .eq("id", company.id);

  if (error) {
    return { ok: false, error: "generic_error" };
  }

  revalidatePath("/settings/company");
  return { ok: true };
}
