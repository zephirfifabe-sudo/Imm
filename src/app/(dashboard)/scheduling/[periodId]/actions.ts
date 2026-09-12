"use server";

import { revalidatePath } from "next/cache";
import { requireAdmin } from "@/lib/auth/current-user";
import {
  replaceScheduleGrid,
  setScheduleShiftCell,
  updateSchedulePeriodSettings,
} from "@/lib/scheduling/mutations";
import type { ScheduleGrid, SchedulingSettings } from "@/lib/scheduling/types";

export async function updatePeriodSettingsAction(
  periodId: string,
  settings: SchedulingSettings,
): Promise<{ ok: boolean }> {
  const { company } = await requireAdmin();
  const result = await updateSchedulePeriodSettings(company.id, periodId, settings);
  revalidatePath(`/scheduling/${periodId}`);
  return { ok: result.ok };
}

export async function saveGridAction(
  periodId: string,
  grid: ScheduleGrid,
): Promise<{ ok: boolean }> {
  const { company } = await requireAdmin();
  const result = await replaceScheduleGrid(company.id, periodId, grid);
  revalidatePath(`/scheduling/${periodId}`);
  return { ok: result.ok };
}

export async function setCellAction(
  periodId: string,
  employeeId: string,
  dayIndex: number,
  code: string,
): Promise<{ ok: boolean }> {
  const { company } = await requireAdmin();
  const result = await setScheduleShiftCell(company.id, periodId, employeeId, dayIndex, code);
  return { ok: result.ok };
}
