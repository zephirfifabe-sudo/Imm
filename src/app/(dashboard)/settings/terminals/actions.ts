"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { requireAdmin } from "@/lib/auth/current-user";
import {
  createTerminal,
  deactivateTerminal,
  reissueActivationCode,
} from "@/lib/terminals/mutations";

const createTerminalSchema = z.object({
  name: z.string().trim().min(2).max(200),
  siteId: z.string().uuid().optional().or(z.literal("")),
});

export type CreateTerminalState =
  | { ok: true; activationCode: string }
  | { ok: false; error: "invalid_input" | "generic_error" }
  | undefined;

export async function createTerminalAction(
  _prevState: CreateTerminalState,
  formData: FormData,
): Promise<CreateTerminalState> {
  const { company } = await requireAdmin();

  const parsed = createTerminalSchema.safeParse({
    name: formData.get("name"),
    siteId: formData.get("siteId"),
  });

  if (!parsed.success) {
    return { ok: false, error: "invalid_input" };
  }

  const result = await createTerminal(company.id, {
    name: parsed.data.name,
    siteId: parsed.data.siteId || undefined,
  });

  if (!result.ok) {
    return result;
  }

  revalidatePath("/settings/terminals");
  return result;
}

export async function deactivateTerminalAction(terminalId: string) {
  const { company } = await requireAdmin();
  await deactivateTerminal(company.id, terminalId);
  revalidatePath("/settings/terminals");
}

export async function reissueActivationCodeAction(terminalId: string) {
  const { company } = await requireAdmin();
  await reissueActivationCode(company.id, terminalId);
  revalidatePath("/settings/terminals");
}
