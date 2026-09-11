"use server";

import { z } from "zod";
import { activateTerminal, verifyTerminalToken } from "@/lib/timeclock/terminal-auth";
import { identifyByPin, identifyByQrToken } from "@/lib/timeclock/identify";
import { getLastEntryType, recordClockEvent } from "@/lib/timeclock/mutations";
import { getValidNextActions } from "@/lib/timeclock/service";
import { PIN_REGEX } from "@/lib/employees/schema";
import type { TimeEntryType } from "@/types/database";

export type ActivateResult =
  | { ok: true; token: string; terminalName: string }
  | { ok: false; error: "invalid_code" | "generic_error" };

export async function activateTerminalAction(
  activationCode: string,
): Promise<ActivateResult> {
  const parsed = z
    .string()
    .trim()
    .regex(/^\d{6}$/)
    .safeParse(activationCode);

  if (!parsed.success) {
    return { ok: false, error: "invalid_code" };
  }

  return activateTerminal(parsed.data);
}

export type IdentifyResult =
  | {
      ok: true;
      employeeId: string;
      firstName: string;
      validActions: TimeEntryType[];
    }
  | { ok: false; error: "invalid_terminal" | "invalid_input" | "not_found" };

export async function identifyEmployeeAction(
  token: string,
  method: "PIN" | "QR",
  value: string,
): Promise<IdentifyResult> {
  const terminal = await verifyTerminalToken(token);
  if (!terminal) {
    return { ok: false, error: "invalid_terminal" };
  }

  if (method === "PIN" && !PIN_REGEX.test(value)) {
    return { ok: false, error: "invalid_input" };
  }
  if (method === "QR" && value.trim().length === 0) {
    return { ok: false, error: "invalid_input" };
  }

  const employee =
    method === "PIN"
      ? await identifyByPin(terminal.company_id, value)
      : await identifyByQrToken(terminal.company_id, value.trim());

  if (!employee) {
    return { ok: false, error: "not_found" };
  }

  const lastType = await getLastEntryType(employee.id);

  return {
    ok: true,
    employeeId: employee.id,
    firstName: employee.first_name,
    validActions: getValidNextActions(lastType),
  };
}

export type ClockResult =
  | { ok: true; type: TimeEntryType; occurredAt: string }
  | {
      ok: false;
      error: "invalid_terminal" | "invalid_transition" | "not_found" | "generic_error";
    };

export async function recordClockAction(
  token: string,
  employeeId: string,
  type: TimeEntryType,
  method: "PIN" | "QR",
  eventId: string,
): Promise<ClockResult> {
  const terminal = await verifyTerminalToken(token);
  if (!terminal) {
    return { ok: false, error: "invalid_terminal" };
  }

  const result = await recordClockEvent({
    companyId: terminal.company_id,
    siteId: terminal.site_id,
    employeeId,
    terminalId: terminal.id,
    type,
    source: method,
    eventId,
  });

  if (!result.ok) {
    return result;
  }

  return { ok: true, type: result.entry.type, occurredAt: result.entry.occurred_at };
}
