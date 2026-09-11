import "server-only";
import { identifyByPin, identifyByQrToken, identifyByNfcToken } from "@/lib/timeclock/identify";
import { PIN_REGEX } from "@/lib/employees/schema";
import type { Employee } from "@/types/database";

/**
 * Couche d'abstraction de l'identification (section "IdentificationProvider"
 * du cahier des charges): le terminal ne doit jamais coupler sa logique
 * métier à une technologie d'identification précise. Ajouter un nouveau
 * moyen d'identification (un autre type de badge, une appli mobile...)
 * signifie ajouter un provider ici, jamais modifier `identifyEmployeeAction`
 * ou `recordClockAction`.
 *
 * Un provider ne sait rien du matériel qui produit sa valeur d'entrée: un
 * badge NFC lu par un lecteur USB en mode clavier, par l'API Web NFC, ou
 * tapé manuellement arrivent tous comme la même chaîne de caractères.
 */
export type IdentificationMethod = "PIN" | "QR" | "NFC";

export interface IdentificationProvider {
  method: IdentificationMethod;
  isValidInput(value: string): boolean;
  identify(companyId: string, value: string): Promise<Employee | null>;
}

export const pinProvider: IdentificationProvider = {
  method: "PIN",
  isValidInput: (value) => PIN_REGEX.test(value),
  identify: (companyId, value) => identifyByPin(companyId, value),
};

export const qrProvider: IdentificationProvider = {
  method: "QR",
  isValidInput: (value) => value.trim().length > 0,
  identify: (companyId, value) => identifyByQrToken(companyId, value.trim()),
};

export const nfcProvider: IdentificationProvider = {
  method: "NFC",
  isValidInput: (value) => value.trim().length > 0,
  identify: (companyId, value) => identifyByNfcToken(companyId, value.trim()),
};

const providersByMethod: Record<IdentificationMethod, IdentificationProvider> = {
  PIN: pinProvider,
  QR: qrProvider,
  NFC: nfcProvider,
};

export function getIdentificationProvider(
  method: IdentificationMethod,
): IdentificationProvider {
  return providersByMethod[method];
}
