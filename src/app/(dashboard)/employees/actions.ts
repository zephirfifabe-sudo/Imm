"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireAdmin, requireCurrentUser } from "@/lib/auth/current-user";
import { employeeFormSchema } from "@/lib/employees/schema";
import {
  createEmployee,
  updateEmployee,
  setEmployeeStatus,
  regenerateQrToken,
  type EmployeeMutationError,
} from "@/lib/employees/mutations";
import { employeeSchedulingProfileSchema } from "@/lib/scheduling/profile-schema";
import { upsertEmployeeSchedulingProfile } from "@/lib/scheduling/mutations";
import {
  inviteEmployeeToApp,
  revokeEmployeeAppAccess,
  type InviteEmployeeToAppResult,
} from "@/lib/employees/app-access";

export type EmployeeFormState =
  | { ok: true }
  | { ok: false; error: "invalid_input" | EmployeeMutationError }
  | undefined;

function readEmployeeForm(formData: FormData) {
  return employeeFormSchema.safeParse({
    firstName: formData.get("firstName"),
    lastName: formData.get("lastName"),
    email: formData.get("email"),
    internalCode: formData.get("internalCode"),
    jobTitle: formData.get("jobTitle"),
    siteId: formData.get("siteId"),
    pin: formData.get("pin"),
    nfcToken: formData.get("nfcToken"),
  });
}

function readSchedulingProfileForm(formData: FormData) {
  const contractHoursPerWeek = formData.get("contractHoursPerWeek");
  const contractType = formData.get("contractType");
  const minNightsPerPeriod = formData.get("minNightsPerPeriod");
  const maxNightsPerPeriod = formData.get("maxNightsPerPeriod");

  return employeeSchedulingProfileSchema.safeParse({
    contractHoursPerWeek: contractHoursPerWeek ? contractHoursPerWeek : undefined,
    contractType: contractType ? contractType : undefined,
    dayOnly: formData.get("dayOnly") === "true",
    nightOnly: formData.get("nightOnly") === "true",
    minNightsPerPeriod: minNightsPerPeriod ? minNightsPerPeriod : undefined,
    maxNightsPerPeriod: maxNightsPerPeriod ? maxNightsPerPeriod : undefined,
  });
}

export async function createEmployeeAction(
  _prevState: EmployeeFormState,
  formData: FormData,
): Promise<EmployeeFormState> {
  const { company } = await requireCurrentUser();

  const parsed = readEmployeeForm(formData);
  if (!parsed.success) {
    return { ok: false, error: "invalid_input" };
  }
  const profileParsed = readSchedulingProfileForm(formData);
  if (!profileParsed.success) {
    return { ok: false, error: "invalid_input" };
  }

  const result = await createEmployee(company.id, parsed.data);
  if (!result.ok) {
    return result;
  }

  await upsertEmployeeSchedulingProfile(company.id, result.id, profileParsed.data);

  revalidatePath("/employees");
  return { ok: true };
}

export async function updateEmployeeAction(
  employeeId: string,
  _prevState: EmployeeFormState,
  formData: FormData,
): Promise<EmployeeFormState> {
  const { company } = await requireCurrentUser();

  const parsed = readEmployeeForm(formData);
  if (!parsed.success) {
    return { ok: false, error: "invalid_input" };
  }
  const profileParsed = readSchedulingProfileForm(formData);
  if (!profileParsed.success) {
    return { ok: false, error: "invalid_input" };
  }

  const result = await updateEmployee(company.id, employeeId, parsed.data);
  if (!result.ok) {
    return result;
  }

  await upsertEmployeeSchedulingProfile(company.id, employeeId, profileParsed.data);

  revalidatePath("/employees");
  revalidatePath(`/employees/${employeeId}/edit`);
  return { ok: true };
}

export async function setEmployeeStatusAction(
  employeeId: string,
  status: "ACTIVE" | "INACTIVE",
) {
  const { company } = await requireCurrentUser();
  const result = await setEmployeeStatus(company.id, employeeId, status);
  revalidatePath("/employees");

  if (!result.ok) {
    redirect(`/employees?error=${result.error}`);
  }
}

export async function regenerateQrTokenAction(employeeId: string) {
  const { company } = await requireCurrentUser();
  await regenerateQrToken(company.id, employeeId);
  revalidatePath(`/employees/${employeeId}/edit`);
}

export type InviteEmployeeToAppState = InviteEmployeeToAppResult | undefined;

export async function inviteEmployeeToAppAction(
  employeeId: string,
): Promise<InviteEmployeeToAppState> {
  const { company } = await requireAdmin();
  const result = await inviteEmployeeToApp(company.id, employeeId);
  revalidatePath(`/employees/${employeeId}/edit`);
  return result;
}

export async function revokeEmployeeAppAccessAction(employeeId: string) {
  const { company } = await requireAdmin();
  await revokeEmployeeAppAccess(company.id, employeeId);
  revalidatePath(`/employees/${employeeId}/edit`);
}
