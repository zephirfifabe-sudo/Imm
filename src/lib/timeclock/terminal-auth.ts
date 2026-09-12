import "server-only";
import bcrypt from "bcryptjs";
import { createSupabaseServiceRoleClient } from "@/lib/supabase/service-role";
import type { Terminal } from "@/types/database";

const SALT_ROUNDS = 10;

// Un code à 6 chiffres (1 000 000 de combinaisons) sans expiration reste
// devinable indéfiniment, sans qu'aucune limitation de débit ne soit en
// place au niveau applicatif. Une fenêtre de validité courte réduit
// fortement la surface d'attaque exploitable.
const ACTIVATION_CODE_TTL_MS = 24 * 60 * 60 * 1000;

/** Code court (6 chiffres), à taper une seule fois sur la tablette lors de l'activation. */
export function generateActivationCode(): string {
  return Math.floor(100000 + Math.random() * 900000).toString();
}

export function getActivationCodeExpiry(): string {
  return new Date(Date.now() + ACTIVATION_CODE_TTL_MS).toISOString();
}

function generateSecret(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

export type ActivateTerminalResult =
  | { ok: true; token: string; terminalName: string }
  | { ok: false; error: "invalid_code" | "generic_error" };

/**
 * Consomme un code d'activation à usage unique et émet le token permanent
 * du terminal. Le token complet (id.secret) n'est jamais stocké: seul le
 * hash du secret l'est, comme un mot de passe.
 */
export async function activateTerminal(
  activationCode: string,
): Promise<ActivateTerminalResult> {
  const serviceRole = createSupabaseServiceRoleClient();

  const { data: terminal } = await serviceRole
    .from("terminals")
    .select("id, name")
    .eq("activation_code", activationCode)
    .eq("status", "PENDING_ACTIVATION")
    .gt("activation_code_expires_at", new Date().toISOString())
    .maybeSingle();

  if (!terminal) {
    return { ok: false, error: "invalid_code" };
  }

  const secret = generateSecret();
  const secretHash = await bcrypt.hash(secret, SALT_ROUNDS);

  const { error } = await serviceRole
    .from("terminals")
    .update({
      terminal_secret_hash: secretHash,
      activation_code: null,
      activation_code_expires_at: null,
      status: "ACTIVE",
      last_seen_at: new Date().toISOString(),
    })
    .eq("id", terminal.id);

  if (error) {
    return { ok: false, error: "generic_error" };
  }

  return { ok: true, token: `${terminal.id}.${secret}`, terminalName: terminal.name };
}

/**
 * Vérifie un token présenté par le terminal à chaque appel (aucune session
 * n'est conservée côté serveur). Un terminal désactivé ou dont le token ne
 * correspond plus est traité comme non authentifié.
 */
export async function verifyTerminalToken(
  token: string,
): Promise<Terminal | null> {
  const separatorIndex = token.indexOf(".");
  if (separatorIndex === -1) return null;

  const terminalId = token.slice(0, separatorIndex);
  const secret = token.slice(separatorIndex + 1);
  if (!terminalId || !secret) return null;

  const serviceRole = createSupabaseServiceRoleClient();
  const { data: terminal } = await serviceRole
    .from("terminals")
    .select("*")
    .eq("id", terminalId)
    .maybeSingle();

  if (
    !terminal ||
    terminal.status !== "ACTIVE" ||
    !terminal.terminal_secret_hash
  ) {
    return null;
  }

  const isValid = await bcrypt.compare(secret, terminal.terminal_secret_hash);
  if (!isValid) return null;

  await serviceRole
    .from("terminals")
    .update({ last_seen_at: new Date().toISOString() })
    .eq("id", terminal.id);

  return terminal;
}
