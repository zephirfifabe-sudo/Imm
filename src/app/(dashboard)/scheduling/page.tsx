import Link from "next/link";
import { requireAdmin } from "@/lib/auth/current-user";
import { listSchedulePeriods } from "@/lib/scheduling/mutations";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { CreatePeriodForm } from "./CreatePeriodForm";
import { deleteSchedulePeriodAction } from "./actions";
import { getTranslator } from "@/i18n";

const t = getTranslator();

function formatDate(value: string): string {
  return new Date(`${value}T00:00:00.000Z`).toLocaleDateString("fr-BE", {
    timeZone: "UTC",
  });
}

export default async function SchedulingPage() {
  const { company } = await requireAdmin();
  const periods = await listSchedulePeriods(company.id);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-foreground">{t("scheduling.title")}</h1>

      <Card>
        {periods.length > 0 ? (
          <ul className="divide-y divide-border">
            {periods.map((period) => (
              <li
                key={period.id}
                className="flex items-center justify-between py-3 first:pt-0 last:pb-0"
              >
                <Link href={`/scheduling/${period.id}`} className="flex-1">
                  <p className="text-sm font-medium text-foreground hover:text-primary">
                    {period.name}
                  </p>
                  <p className="text-xs text-muted">
                    {formatDate(period.period_start)} – {formatDate(period.period_end)}
                  </p>
                </Link>
                <form action={deleteSchedulePeriodAction.bind(null, period.id)}>
                  <Button type="submit" variant="ghost" className="text-danger">
                    {t("common.delete")}
                  </Button>
                </form>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">{t("scheduling.empty")}</p>
        )}
      </Card>

      <Card>
        <h2 className="mb-4 text-sm font-medium text-foreground">
          {t("scheduling.createPeriodTitle")}
        </h2>
        <CreatePeriodForm />
      </Card>
    </div>
  );
}
