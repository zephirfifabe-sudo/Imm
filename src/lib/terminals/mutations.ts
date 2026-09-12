import "server-only";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { generateActivationCode, getActivationCodeExpiry } from "@/lib/timeclock/terminal-auth";

function generateTerminalCode(): string {
  return `KLOCK-TERM-${crypto.randomUUID().slice(0, 8).toUpperCase()}`;
}

export type CreateTerminalResult =
  | { ok: true; activationCode: string }
  | { ok: false; error: "generic_error" };

/**
 * Crée un terminal en attente d'activation et génère son code à usage
 * unique. Le code d'activation étant contraint unique (tant qu'il n'est
 * pas consommé) en base, une collision improbable est simplement retentée
 * une fois plutôt que remontée à l'utilisateur.
 */
export async function createTerminal(
  companyId: string,
  input: { name: string; siteId?: string },
): Promise<CreateTerminalResult> {
  const supabase = await createSupabaseServerClient();

  for (let attempt = 0; attempt < 2; attempt++) {
    const activationCode = generateActivationCode();

    const { error } = await supabase.from("terminals").insert({
      company_id: companyId,
      site_id: input.siteId ?? null,
      name: input.name,
      terminal_code: generateTerminalCode(),
      status: "PENDING_ACTIVATION",
      activation_code: activationCode,
      activation_code_expires_at: getActivationCodeExpiry(),
      terminal_secret_hash: null,
      software_version: null,
      last_seen_at: null,
    });

    if (!error) {
      return { ok: true, activationCode };
    }

    const isActivationCodeCollision = error.code === "23505";
    if (!isActivationCodeCollision) {
      return { ok: false, error: "generic_error" };
    }
  }

  return { ok: false, error: "generic_error" };
}

/**
 * Révoque l'accès du terminal (son token cesse de fonctionner immédiatement)
 * et génère un nouveau code d'activation à usage unique pour le réactiver.
 */
export async function reissueActivationCode(
  companyId: string,
  terminalId: string,
): Promise<CreateTerminalResult> {
  const supabase = await createSupabaseServerClient();

  for (let attempt = 0; attempt < 2; attempt++) {
    const activationCode = generateActivationCode();

    const { error } = await supabase
      .from("terminals")
      .update({
        status: "PENDING_ACTIVATION",
        activation_code: activationCode,
        activation_code_expires_at: getActivationCodeExpiry(),
        terminal_secret_hash: null,
      })
      .eq("id", terminalId)
      .eq("company_id", companyId);

    if (!error) {
      return { ok: true, activationCode };
    }

    const isActivationCodeCollision = error.code === "23505";
    if (!isActivationCodeCollision) {
      return { ok: false, error: "generic_error" };
    }
  }

  return { ok: false, error: "generic_error" };
}

export async function deactivateTerminal(
  companyId: string,
  terminalId: string,
): Promise<{ ok: true } | { ok: false; error: "generic_error" }> {
  const supabase = await createSupabaseServerClient();

  const { error } = await supabase
    .from("terminals")
    .update({
      status: "INACTIVE",
      terminal_secret_hash: null,
      activation_code: null,
      activation_code_expires_at: null,
    })
    .eq("id", terminalId)
    .eq("company_id", companyId);

  return error ? { ok: false, error: "generic_error" } : { ok: true };
}
