import express from "express";
import cors from "cors";
import { env } from "./config/env";
import { apiRouter } from "./routes";
import { UPLOADS_DIR } from "./middleware/upload.middleware";
import { errorHandler, notFoundHandler } from "./middleware/error.middleware";
import { asyncHandler } from "./utils/async-handler";
import { stripeWebhook } from "./controllers/payments.controller";

export const app = express();

app.use(cors({ origin: env.corsOrigin }));

// Le webhook Stripe exige le corps brut pour vérifier la signature :
// il est monté AVANT express.json() pour ne pas être parsé en JSON.
app.post("/webhooks/stripe", express.raw({ type: "application/json" }), asyncHandler(stripeWebhook));

app.use(express.json());
app.use("/uploads", express.static(UPLOADS_DIR));

app.get("/health", (_req, res) => res.status(200).json({ status: "ok" }));

app.use("/api", apiRouter);

app.use(notFoundHandler);
app.use(errorHandler);
