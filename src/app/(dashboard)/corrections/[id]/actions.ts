"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { requireCurrentUser } from "@/lib/auth/current-user";
import { correctTimeEntry } from "@/lib/corrections/mutations";

const correctionSchema = z.object({
  newOccurredAt: z.string().min(1),
  reason: z.string().trim().min(3).max(500),
});

export type CorrectionFormState =
  | { ok: false; error: "invalid_input" | "not_found" | "generic_error" }
  | undefined;

export async function submitCorrectionAction(
  timeEntryId: string,
  _prevState: CorrectionFormState,
  formData: FormData,
): Promise<CorrectionFormState> {
  const { user, company } = await requireCurrentUser();

  const parsed = correctionSchema.safeParse({
    newOccurredAt: formData.get("newOccurredAt"),
    reason: formData.get("reason"),
  });

  if (!parsed.success) {
    return { error: "invalid_input", ok: false };
  }

  const newOccurredAt = new Date(parsed.data.newOccurredAt);
  if (Number.isNaN(newOccurredAt.getTime())) {
    return { error: "invalid_input", ok: false };
  }

  const result = await correctTimeEntry({
    companyId: company.id,
    correctedByUserId: user.id,
    timeEntryId,
    newOccurredAt,
    reason: parsed.data.reason,
  });

  if (!result.ok) {
    return result;
  }

  redirect("/history");
}
