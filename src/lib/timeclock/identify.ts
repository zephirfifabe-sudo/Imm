import "server-only";
import { createSupabaseServiceRoleClient } from "@/lib/supabase/service-role";
import { pinMatchesHash } from "@/lib/employees/pin";
import type { Employee } from "@/types/database";

/**
 * Identifie un employé par PIN au sein de l'entreprise du terminal. Le PIN
 * est hashé (bcrypt, salé): on ne peut pas l'indexer, donc on compare au
 * plus aux ~50 employés actifs de l'entreprise (limite de plan) — coût
 * négligeable, sécurité du hash intacte.
 */
export async function identifyByPin(
  companyId: string,
  pin: string,
): Promise<Employee | null> {
  const serviceRole = createSupabaseServiceRoleClient();

  const { data: candidates } = await serviceRole
    .from("employees")
    .select("*")
    .eq("company_id", companyId)
    .eq("status", "ACTIVE")
    .not("pin_hash", "is", null);

  for (const candidate of candidates ?? []) {
    if (candidate.pin_hash && (await pinMatchesHash(pin, candidate.pin_hash))) {
      return candidate;
    }
  }

  return null;
}

/**
 * Identifie un employé par son token QR. Le token est un UUID aléatoire
 * globalement unique: la recherche se fait par égalité indexée, sans lien
 * avec une donnée personnelle.
 */
export async function identifyByQrToken(
  companyId: string,
  qrToken: string,
): Promise<Employee | null> {
  const serviceRole = createSupabaseServiceRoleClient();

  const { data: employee } = await serviceRole
    .from("employees")
    .select("*")
    .eq("qr_token", qrToken)
    .eq("company_id", companyId)
    .eq("status", "ACTIVE")
    .maybeSingle();

  return employee ?? null;
}

/**
 * Identifie un employé par son token NFC (UID du badge, ou identifiant
 * KLOCK associé au badge — jamais une donnée personnelle). Même mécanique
 * que le QR: égalité indexée sur un token opaque, quel que soit le moyen
 * par lequel ce token est arrivé au terminal (lecteur USB en mode clavier,
 * Web NFC, saisie manuelle) — le matériel est invisible à ce niveau.
 */
export async function identifyByNfcToken(
  companyId: string,
  nfcToken: string,
): Promise<Employee | null> {
  const serviceRole = createSupabaseServiceRoleClient();

  const { data: employee } = await serviceRole
    .from("employees")
    .select("*")
    .eq("nfc_token", nfcToken)
    .eq("company_id", companyId)
    .eq("status", "ACTIVE")
    .maybeSingle();

  return employee ?? null;
}
