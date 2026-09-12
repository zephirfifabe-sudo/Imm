import { NextResponse } from "next/server";
import type Stripe from "stripe";
import { getStripeClient } from "@/lib/stripe/client";
import { getPlanCodeForStripePriceId } from "@/lib/stripe/plan-prices";
import { createSupabaseServiceRoleClient } from "@/lib/supabase/service-role";

/**
 * Webhook Stripe: seule source de vérité pour l'état réel d'un abonnement
 * (paiement réussi, échoué, annulé...). La signature est vérifiée avant
 * tout traitement — jamais de confiance dans le corps de la requête seul.
 */
export async function POST(request: Request) {
  const signature = request.headers.get("stripe-signature");
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

  if (!signature || !webhookSecret) {
    return NextResponse.json({ error: "missing_signature" }, { status: 400 });
  }

  const rawBody = await request.text();
  const stripe = getStripeClient();

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(rawBody, signature, webhookSecret);
  } catch {
    return NextResponse.json({ error: "invalid_signature" }, { status: 400 });
  }

  const serviceRole = createSupabaseServiceRoleClient();

  // Une écriture ratée ici ne doit jamais renvoyer 200: Stripe ne
  // réessaiera plus l'événement, et l'abonnement resterait désynchronisé
  // silencieusement (le client aurait payé sans que KLOCK le sache, ou
  // l'inverse). On répond 500 pour déclencher le retry de Stripe, et on
  // journalise pour pouvoir diagnostiquer si l'échec persiste.
  let writeError: unknown = null;

  switch (event.type) {
    case "checkout.session.completed": {
      const session = event.data.object as Stripe.Checkout.Session;
      const companyId = session.metadata?.company_id ?? session.client_reference_id;
      const customerId =
        typeof session.customer === "string" ? session.customer : session.customer?.id;
      const subscriptionId =
        typeof session.subscription === "string"
          ? session.subscription
          : session.subscription?.id;

      if (companyId && customerId && subscriptionId) {
        const { error } = await serviceRole
          .from("subscriptions")
          .update({
            stripe_customer_id: customerId,
            stripe_subscription_id: subscriptionId,
            status: "active",
          })
          .eq("company_id", companyId);
        writeError = error;
      } else {
        console.error("stripe webhook: checkout.session.completed missing company/customer/subscription id", {
          eventId: event.id,
          companyId,
          customerId,
          subscriptionId,
        });
      }
      break;
    }

    case "customer.subscription.updated":
    case "customer.subscription.deleted": {
      const subscription = event.data.object as Stripe.Subscription;
      const companyId = subscription.metadata?.company_id;
      if (!companyId) {
        console.error("stripe webhook: subscription event missing company_id metadata", {
          eventId: event.id,
          subscriptionId: subscription.id,
        });
        break;
      }

      const item = subscription.items.data[0];
      const priceId = item?.price.id;
      const planCode = priceId ? getPlanCodeForStripePriceId(priceId) : null;

      const update: { status: string; current_period_end: string | null; plan_id?: string } = {
        status: subscription.status,
        current_period_end: item
          ? new Date(item.current_period_end * 1000).toISOString()
          : null,
      };

      if (planCode) {
        const { data: plan } = await serviceRole
          .from("plans")
          .select("id")
          .eq("code", planCode)
          .maybeSingle();
        if (plan) {
          update.plan_id = plan.id;
        }
      }

      const { error } = await serviceRole
        .from("subscriptions")
        .update(update)
        .eq("company_id", companyId);
      writeError = error;
      break;
    }

    default:
      break;
  }

  if (writeError) {
    console.error("stripe webhook: failed to sync subscription state", {
      eventId: event.id,
      eventType: event.type,
      error: writeError,
    });
    return NextResponse.json({ error: "sync_failed" }, { status: 500 });
  }

  return NextResponse.json({ received: true });
}
