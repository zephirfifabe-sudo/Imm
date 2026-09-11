import { requireAdmin } from "@/lib/auth/current-user";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { countActiveEmployees } from "@/lib/subscriptions/limits";
import { formatPriceCents } from "@/lib/config/plans";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { subscribeToPlanAction, manageBillingAction } from "./actions";
import { getTranslator } from "@/i18n";

const t = getTranslator();

const STATUS_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  active: "success",
  trialing: "warning",
  past_due: "danger",
  canceled: "neutral",
  incomplete: "neutral",
  incomplete_expired: "neutral",
  unpaid: "danger",
  paused: "neutral",
};

export default async function SubscriptionSettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { company } = await requireAdmin();
  const { error } = await searchParams;

  const supabase = await createSupabaseServerClient();
  const [{ data: subscription }, { data: plans }, activeEmployeeCount] = await Promise.all([
    supabase.from("subscriptions").select("*").eq("company_id", company.id).maybeSingle(),
    supabase.from("plans").select("*").eq("is_active", true).order("price_cents"),
    countActiveEmployees(company.id),
  ]);

  const currentPlan = subscription
    ? (plans ?? []).find((plan) => plan.id === subscription.plan_id)
    : null;

  const isPaid = Boolean(subscription?.stripe_subscription_id);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-foreground">
        {t("subscription.title")}
      </h1>

      {error && (
        <Card className="border-amber-300 bg-amber-50">
          <p className="text-sm font-medium text-amber-800">
            {t("subscription.genericError")}
          </p>
        </Card>
      )}

      <Card>
        {subscription && currentPlan ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <p className="text-lg font-semibold text-foreground">{currentPlan.name}</p>
              <Badge tone={STATUS_TONE[subscription.status] ?? "neutral"}>
                {t(`subscription.status.${subscription.status}`)}
              </Badge>
            </div>
            <p className="text-sm text-muted">
              {t("subscription.employeeUsage", {
                current: activeEmployeeCount,
                max: currentPlan.max_employees,
              })}
            </p>
            {isPaid && (
              <form action={manageBillingAction} className="pt-2">
                <Button type="submit">{t("subscription.manageBilling")}</Button>
              </form>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted">{t("subscription.noSubscription")}</p>
        )}
      </Card>

      {!isPaid && (
        <div className="grid gap-4 sm:grid-cols-3">
          {(plans ?? []).map((plan) => (
            <Card key={plan.id} className="flex flex-col justify-between">
              <div>
                <p className="text-sm font-semibold text-foreground">{plan.name}</p>
                <p className="mt-1 text-2xl font-bold text-foreground">
                  {formatPriceCents(plan.price_cents)}
                  <span className="text-sm font-normal text-muted">
                    {t("subscription.perMonth")}
                  </span>
                </p>
                <p className="mt-1 text-xs text-muted">
                  {t("subscription.upToEmployees", { count: plan.max_employees })}
                </p>
              </div>
              <form action={subscribeToPlanAction.bind(null, plan.code)} className="mt-4">
                <Button type="submit" className="w-full">
                  {t("subscription.subscribe")}
                </Button>
              </form>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
