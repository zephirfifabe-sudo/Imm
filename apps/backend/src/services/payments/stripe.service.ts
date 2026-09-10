import Stripe from "stripe";
import { CREDIT_PACKS } from "@previsite/shared";
import { env } from "../../config/env";
import { ApiError } from "../../middleware/error.middleware";
import { grantCredits } from "../credits/credits.service";

const stripe = env.stripeSecretKey ? new Stripe(env.stripeSecretKey) : null;

function requireStripe(): Stripe {
  if (!stripe) {
    throw new ApiError(
      503,
      "Le paiement n'est pas encore configuré côté serveur (clé Stripe manquante).",
    );
  }
  return stripe;
}

/**
 * Crée un PaymentIntent Stripe (mode test) pour l'achat d'un pack de crédits.
 * Le crédit n'est accordé qu'à la confirmation du paiement (voir webhook),
 * jamais à la simple création de l'intent — pour éviter de créditer un
 * paiement qui échoue côté client.
 */
export async function createCreditPackPaymentIntent(userId: string, packId: string) {
  const pack = CREDIT_PACKS.find((p) => p.id === packId);
  if (!pack) {
    throw new ApiError(400, "Pack de crédits inconnu.");
  }

  const client = requireStripe();
  const paymentIntent = await client.paymentIntents.create({
    amount: pack.priceCents,
    currency: "eur",
    metadata: { userId, packId, credits: String(pack.credits) },
  });

  return { clientSecret: paymentIntent.client_secret, pack };
}

/** Traite l'événement Stripe `payment_intent.succeeded` en créditant l'utilisateur. */
export async function handleStripeWebhookEvent(rawBody: Buffer, signature: string) {
  const client = requireStripe();
  const event = client.webhooks.constructEvent(rawBody, signature, env.stripeWebhookSecret);

  if (event.type === "payment_intent.succeeded") {
    const intent = event.data.object as Stripe.PaymentIntent;
    const { userId, packId, credits } = intent.metadata;
    if (userId && packId && credits) {
      await grantCredits(userId, Number(credits), packId, intent.id);
    }
  }
}
