import "dotenv/config";

function requireInProd(name: string, value: string | undefined): string {
  if (!value && process.env.NODE_ENV === "production") {
    throw new Error(`Variable d'environnement manquante en production: ${name}`);
  }
  return value ?? "";
}

export const env = {
  nodeEnv: process.env.NODE_ENV ?? "development",
  port: Number(process.env.PORT ?? 4000),
  corsOrigin: process.env.CORS_ORIGIN ?? "*",

  jwtSecret: requireInProd("JWT_SECRET", process.env.JWT_SECRET) || "dev-secret-do-not-use-in-prod",
  jwtExpiresIn: process.env.JWT_EXPIRES_IN ?? "30d",

  anthropicApiKey: requireInProd("ANTHROPIC_API_KEY", process.env.ANTHROPIC_API_KEY),
  anthropicVisionModel: process.env.ANTHROPIC_VISION_MODEL ?? "claude-sonnet-5",
  anthropicSynthesisModel: process.env.ANTHROPIC_SYNTHESIS_MODEL ?? "claude-sonnet-5",

  stripeSecretKey: requireInProd("STRIPE_SECRET_KEY", process.env.STRIPE_SECRET_KEY),
  stripeWebhookSecret: process.env.STRIPE_WEBHOOK_SECRET ?? "",
};
