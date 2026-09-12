"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { requireAdmin } from "@/lib/auth/current-user";
import { createSchedulePeriod, deleteSchedulePeriod } from "@/lib/scheduling/mutations";
import { DEFAULT_SCHEDULING_SETTINGS } from "@/lib/scheduling/types";

const createPeriodSchema = z.object({
  name: z.string().trim().min(1).max(100),
  periodStart: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
});

export type CreatePeriodState =
  | { ok: true }
  | { ok: false; error: "invalid_input" | "generic_error" }
  | undefined;

export async function createSchedulePeriodAction(
  _prevState: CreatePeriodState,
  formData: FormData,
): Promise<CreatePeriodState> {
  const { company } = await requireAdmin();

  const parsed = createPeriodSchema.safeParse({
    name: formData.get("name"),
    periodStart: formData.get("periodStart"),
  });
  if (!parsed.success) {
    return { ok: false, error: "invalid_input" };
  }

  const result = await createSchedulePeriod(company.id, {
    name: parsed.data.name,
    periodStart: parsed.data.periodStart,
    settings: DEFAULT_SCHEDULING_SETTINGS,
  });
  if (!result.ok) {
    return result;
  }

  revalidatePath("/scheduling");
  return { ok: true };
}

export async function deleteSchedulePeriodAction(periodId: string) {
  const { company } = await requireAdmin();
  await deleteSchedulePeriod(company.id, periodId);
  revalidatePath("/scheduling");
}
