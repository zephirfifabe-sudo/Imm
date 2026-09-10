import { FREE_ANALYSES_PER_ACCOUNT } from "@previsite/shared";
import { prisma } from "../../db/prisma";
import { ApiError } from "../../middleware/error.middleware";

export type ConsumptionSource = "free" | "credit";

/**
 * Consomme un droit d'analyse pour l'utilisateur : d'abord les analyses
 * gratuites à vie (FREE_ANALYSES_PER_ACCOUNT), puis les crédits achetés.
 * Lève une ApiError(402) si l'utilisateur n'a plus aucun droit disponible —
 * l'appelant ne doit exécuter l'analyse (vision + LLM) qu'après ce succès,
 * pour ne jamais consommer un appel IA payant sans contrepartie de crédit.
 */
export async function consumeAnalysisEntitlement(userId: string): Promise<ConsumptionSource> {
  return prisma.$transaction(async (tx) => {
    const user = await tx.user.findUniqueOrThrow({ where: { id: userId } });

    if (user.freeAnalysesUsed < FREE_ANALYSES_PER_ACCOUNT) {
      await tx.user.update({
        where: { id: userId },
        data: { freeAnalysesUsed: { increment: 1 } },
      });
      return "free";
    }

    if (user.creditBalance > 0) {
      await tx.user.update({
        where: { id: userId },
        data: { creditBalance: { decrement: 1 } },
      });
      await tx.creditTransaction.create({
        data: { userId, type: "consumption", amount: -1 },
      });
      return "credit";
    }

    throw new ApiError(
      402,
      "Tu as utilisé toutes tes analyses gratuites et ton solde de crédits est à zéro. Achète un pack pour continuer.",
    );
  });
}

export async function grantCredits(
  userId: string,
  amount: number,
  creditPackId: string,
  stripePaymentIntentId: string,
): Promise<void> {
  await prisma.$transaction([
    prisma.user.update({
      where: { id: userId },
      data: { creditBalance: { increment: amount } },
    }),
    prisma.creditTransaction.create({
      data: { userId, type: "purchase", amount, creditPackId, stripePaymentIntentId },
    }),
  ]);
}

export async function getCreditSummary(userId: string) {
  const user = await prisma.user.findUniqueOrThrow({ where: { id: userId } });
  return {
    creditBalance: user.creditBalance,
    freeAnalysesUsed: user.freeAnalysesUsed,
    freeAnalysesRemaining: Math.max(0, FREE_ANALYSES_PER_ACCOUNT - user.freeAnalysesUsed),
  };
}
