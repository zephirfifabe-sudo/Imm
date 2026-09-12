"use server";

import { z } from "zod";
import { activateTerminal, verifyTerminalToken } from "@/lib/timeclock/terminal-auth";
import { getIdentificationProvider, type IdentificationMethod } from "@/lib/timeclock/identification-providers";
import { getLastEntryType, recordClockEvent } from "@/lib/timeclock/mutations";
import { getValidNextActions } from "@/lib/timeclock/service";
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

/**
 * Vérifie qu'un token stocké sur l'appareil correspond toujours à un
 * terminal actif, sans rien tenter d'autre (pas d'identification, pas de
 * pointage). Utilisé au chargement de l'écran pour détecter un terminal
 * désactivé entre-temps: sans ce contrôle, l'écran d'accueil (PIN/QR/NFC)
 * reste affiché — basé uniquement sur la présence du token en local —
 * jusqu'à ce qu'un employé tente réellement de s'identifier et échoue.
 */
export async function checkTerminalStatusAction(token: string): Promise<{ ok: boolean }> {
  const terminal = await verifyTerminalToken(token);
  return { ok: terminal !== null };
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
  method: IdentificationMethod,
  value: string,
): Promise<IdentifyResult> {
  const terminal = await verifyTerminalToken(token);
  if (!terminal) {
    return { ok: false, error: "invalid_terminal" };
  }

  const provider = getIdentificationProvider(method);
  if (!provider.isValidInput(value)) {
    return { ok: false, error: "invalid_input" };
  }

  const employee = await provider.identify(terminal.company_id, value);

  if (!employee) {
    return { ok: false, error: "not_found" };
  }

  const lastType = await getLastEntryType(terminal.company_id, employee.id);

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
      error:
        | "invalid_terminal"
        | "invalid_transition"
        | "not_found"
        | "invalid_timestamp"
        | "generic_error";
    };

// Tolérance à la dérive d'horloge du terminal (le pointage ne peut pas être
// dans le futur au-delà de ça) et fenêtre maximale acceptée pour un
// pointage mis en file d'attente hors-ligne puis synchronisé plus tard.
const MAX_CLOCK_SKEW_MS = 5 * 60 * 1000;
const MAX_OFFLINE_BACKLOG_MS = 7 * 24 * 60 * 60 * 1000;

export async function recordClockAction(
  token: string,
  employeeId: string,
  type: TimeEntryType,
  method: IdentificationMethod,
  eventId: string,
  occurredAt: string,
): Promise<ClockResult> {
  const terminal = await verifyTerminalToken(token);
  if (!terminal) {
    return { ok: false, error: "invalid_terminal" };
  }

  const occurredAtMs = new Date(occurredAt).getTime();
  const nowMs = Date.now();
  if (
    Number.isNaN(occurredAtMs) ||
    occurredAtMs > nowMs + MAX_CLOCK_SKEW_MS ||
    occurredAtMs < nowMs - MAX_OFFLINE_BACKLOG_MS
  ) {
    return { ok: false, error: "invalid_timestamp" };
  }

  const result = await recordClockEvent({
    companyId: terminal.company_id,
    siteId: terminal.site_id,
    employeeId,
    terminalId: terminal.id,
    type,
    source: method,
    eventId,
    occurredAt,
  });

  if (!result.ok) {
    return result;
  }

  return { ok: true, type: result.entry.type, occurredAt: result.entry.occurred_at };
}
