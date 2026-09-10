import type { CREDIT_PACKS } from "@previsite/shared";
import { apiClient } from "./client";

export interface CreditSummary {
  creditBalance: number;
  freeAnalysesUsed: number;
  freeAnalysesRemaining: number;
}

type CreditPack = (typeof CREDIT_PACKS)[number];

export function fetchCreditSummary() {
  return apiClient.get<CreditSummary>("/api/credits/me");
}

export function fetchCreditPacks() {
  return apiClient.get<{ packs: CreditPack[] }>("/api/credits/packs", false);
}

export function createPaymentIntent(packId: string) {
  return apiClient.post<{ clientSecret: string | null; pack: CreditPack }>(
    "/api/payments/intent",
    { packId },
  );
}
