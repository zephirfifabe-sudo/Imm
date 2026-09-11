"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { requireAdmin } from "@/lib/auth/current-user";
import {
  inviteTeamMember,
  removeTeamMember,
  updateTeamMemberRole,
} from "@/lib/team/mutations";

const inviteSchema = z.object({
  email: z.string().trim().email(),
  firstName: z.string().trim().min(1).max(100),
  lastName: z.string().trim().min(1).max(100),
  role: z.enum(["ADMIN", "MANAGER"]),
});

export type InviteUserState =
  | { ok: true }
  | {
      ok: false;
      error: "invalid_input" | "email_taken_in_company" | "generic_error";
    }
  | undefined;

export async function inviteUserAction(
  _prevState: InviteUserState,
  formData: FormData,
): Promise<InviteUserState> {
  const { company } = await requireAdmin();

  const parsed = inviteSchema.safeParse({
    email: formData.get("email"),
    firstName: formData.get("firstName"),
    lastName: formData.get("lastName"),
    role: formData.get("role"),
  });

  if (!parsed.success) {
    return { ok: false, error: "invalid_input" };
  }

  const result = await inviteTeamMember({
    companyId: company.id,
    ...parsed.data,
  });

  if (!result.ok) {
    return { ok: false, error: result.error };
  }

  revalidatePath("/settings/users");
  return { ok: true };
}

export async function updateUserRoleAction(userId: string, formData: FormData) {
  const { company } = await requireAdmin();

  const parsedRole = z.enum(["ADMIN", "MANAGER"]).safeParse(formData.get("role"));
  if (!parsedRole.success) {
    return;
  }

  await updateTeamMemberRole({
    companyId: company.id,
    targetUserId: userId,
    newRole: parsedRole.data,
  });

  revalidatePath("/settings/users");
}

export async function removeUserAction(userId: string) {
  const { user, company } = await requireAdmin();

  if (userId === user.id) {
    return;
  }

  await removeTeamMember({ companyId: company.id, targetUserId: userId });

  revalidatePath("/settings/users");
}
