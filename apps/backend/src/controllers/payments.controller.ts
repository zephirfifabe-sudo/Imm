import type { Request, Response } from "express";
import {
  createCreditPackPaymentIntent,
  handleStripeWebhookEvent,
} from "../services/payments/stripe.service";
import { ApiError } from "../middleware/error.middleware";

export async function createPaymentIntent(req: Request, res: Response) {
  const { packId } = req.body as { packId?: string };
  if (!packId) {
    throw new ApiError(400, "packId requis.");
  }
  const result = await createCreditPackPaymentIntent(req.user!.id, packId);
  res.status(200).json(result);
}

export async function stripeWebhook(req: Request, res: Response) {
  const signature = req.headers["stripe-signature"];
  if (typeof signature !== "string") {
    throw new ApiError(400, "Signature Stripe manquante.");
  }
  await handleStripeWebhookEvent(req.body as Buffer, signature);
  res.status(200).json({ received: true });
}
