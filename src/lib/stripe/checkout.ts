import "server-only";
import { getStripeClient } from "@/lib/stripe/client";
import { getStripePriceIdForPlanCode } from "@/lib/stripe/plan-prices";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { env } from "@/lib/config/env";

export type CreateCheckoutSessionResult =
  | { ok: true; url: string }
  | { ok: false; error: "plan_not_configured" | "generic_error" };

/**
 * Crée une session Stripe Checkout (page hébergée par Stripe) pour
 * souscrire à un plan. On réutilise le `stripe_customer_id` existant s'il y
 * en a un, pour éviter de créer un doublon de client Stripe à chaque
 * tentative d'abonnement.
 */
export async function createCheckoutSession(params: {
  companyId: string;
  planCode: string;
  userEmail: string;
}): Promise<CreateCheckoutSessionResult> {
  const priceId = getStripePriceIdForPlanCode(params.planCode);
  if (!priceId) {
    return { ok: false, error: "plan_not_configured" };
  }

  const supabase = await createSupabaseServerClient();
  const { data: subscription } = await supabase
    .from("subscriptions")
    .select("stripe_customer_id")
    .eq("company_id", params.companyId)
    .maybeSingle();

  const stripe = getStripeClient();

  try {
    const session = await stripe.checkout.sessions.create({
      mode: "subscription",
      customer: subscription?.stripe_customer_id ?? undefined,
      customer_email: subscription?.stripe_customer_id ? undefined : params.userEmail,
      line_items: [{ price: priceId, quantity: 1 }],
      success_url: `${env.appUrl}/settings/subscription?checkout=success`,
      cancel_url: `${env.appUrl}/settings/subscription?checkout=cancelled`,
      client_reference_id: params.companyId,
      metadata: { company_id: params.companyId, plan_code: params.planCode },
      subscription_data: {
        metadata: { company_id: params.companyId, plan_code: params.planCode },
      },
    });

    if (!session.url) {
      return { ok: false, error: "generic_error" };
    }

    return { ok: true, url: session.url };
  } catch {
    return { ok: false, error: "generic_error" };
  }
}

export type CreateBillingPortalSessionResult =
  | { ok: true; url: string }
  | { ok: false; error: "no_customer" | "generic_error" };

/** Portail client hébergé par Stripe: factures, moyen de paiement, résiliation. */
export async function createBillingPortalSession(
  companyId: string,
): Promise<CreateBillingPortalSessionResult> {
  const supabase = await createSupabaseServerClient();
  const { data: subscription } = await supabase
    .from("subscriptions")
    .select("stripe_customer_id")
    .eq("company_id", companyId)
    .maybeSingle();

  if (!subscription?.stripe_customer_id) {
    return { ok: false, error: "no_customer" };
  }

  const stripe = getStripeClient();

  try {
    const session = await stripe.billingPortal.sessions.create({
      customer: subscription.stripe_customer_id,
      return_url: `${env.appUrl}/settings/subscription`,
    });

    return { ok: true, url: session.url };
  } catch {
    return { ok: false, error: "generic_error" };
  }
}
