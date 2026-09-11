import "server-only";
import Stripe from "stripe";

let cachedClient: Stripe | null = null;

/**
 * Client Stripe serveur. Ne fixe pas `apiVersion` explicitement: on suit la
 * version épinglée par le SDK installé plutôt que de la dupliquer en dur
 * ici (une seule mise à jour de `stripe` suffit alors à changer de version
 * d'API, jamais un changement de code applicatif).
 */
export function getStripeClient(): Stripe {
  if (!cachedClient) {
    const secretKey = process.env.STRIPE_SECRET_KEY;
    if (!secretKey) {
      throw new Error("Missing required environment variable: STRIPE_SECRET_KEY");
    }
    cachedClient = new Stripe(secretKey);
  }
  return cachedClient;
}
