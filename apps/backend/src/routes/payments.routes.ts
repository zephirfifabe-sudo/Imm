import { Router } from "express";
import { createPaymentIntent } from "../controllers/payments.controller";
import { requireAuth } from "../middleware/auth.middleware";
import { asyncHandler } from "../utils/async-handler";

export const paymentsRouter = Router();

paymentsRouter.post("/intent", requireAuth, asyncHandler(createPaymentIntent));

// Le webhook Stripe (/webhooks/stripe) est monté séparément dans app.ts
// car il exige le corps brut (raw body) pour vérifier la signature.
