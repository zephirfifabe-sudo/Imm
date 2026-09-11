"use server";

import { redirect } from "next/navigation";
import { requireAdmin } from "@/lib/auth/current-user";
import { createCheckoutSession, createBillingPortalSession } from "@/lib/stripe/checkout";

export async function subscribeToPlanAction(planCode: string) {
  const { user, company } = await requireAdmin();

  const result = await createCheckoutSession({
    companyId: company.id,
    planCode,
    userEmail: user.email,
  });

  if (!result.ok) {
    redirect(`/settings/subscription?error=${result.error}`);
  }

  redirect(result.url);
}

export async function manageBillingAction() {
  const { company } = await requireAdmin();

  const result = await createBillingPortalSession(company.id);

  if (!result.ok) {
    redirect(`/settings/subscription?error=${result.error}`);
  }

  redirect(result.url);
}
