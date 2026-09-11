import Link from "next/link";
import { requireCurrentUser } from "@/lib/auth/current-user";
import { getDashboardData } from "@/lib/dashboard/queries";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { getTranslator } from "@/i18n";
import type { PresenceState } from "@/lib/timeclock/summary";
import type { TimeEntryType } from "@/types/database";

const t = getTranslator();

const TYPE_LABELS: Record<TimeEntryType, string> = {
  CLOCK_IN: "Arrivée",
  CLOCK_OUT: "Départ",
  BREAK_START: "Pause",
  BREAK_END: "Reprise",
};

const PRESENCE_TONE: Record<PresenceState, "success" | "warning" | "neutral"> = {
  PRESENT: "success",
  ON_BREAK: "warning",
  ABSENT: "neutral",
};

const PRESENCE_LABEL_KEY: Record<PresenceState, string> = {
  PRESENT: "dashboard.statePresent",
  ON_BREAK: "dashboard.stateOnBreak",
  ABSENT: "dashboard.stateAbsent",
};

export default async function DashboardPage() {
  const { user, company } = await requireCurrentUser();
  const data = await getDashboardData(company.id);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-foreground">
        {t("dashboard.greeting", { name: user.first_name })}
      </h1>

      <div className="grid grid-cols-3 gap-3">
        <Card className="text-center">
          <p className="text-2xl font-bold text-foreground">{data.presentCount}</p>
          <p className="text-xs text-muted">{t("dashboard.present")}</p>
        </Card>
        <Card className="text-center">
          <p className="text-2xl font-bold text-foreground">{data.onBreakCount}</p>
          <p className="text-xs text-muted">{t("dashboard.onBreak")}</p>
        </Card>
        <Card className="text-center">
          <p className="text-2xl font-bold text-foreground">{data.absentCount}</p>
          <p className="text-xs text-muted">{t("dashboard.absent")}</p>
        </Card>
      </div>

      {data.anomalyCount > 0 && (
        <Card className="border-amber-300 bg-amber-50">
          <p className="text-sm font-medium text-amber-800">
            ⚠ {t("dashboard.anomaliesCount", { count: data.anomalyCount })}
          </p>
        </Card>
      )}

      <Card>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-medium text-foreground">
            {t("dashboard.presenceTitle")}
          </h2>
          <Link href="/history" className="text-xs text-primary hover:underline">
            {t("dashboard.viewHistory")}
          </Link>
        </div>
        {data.presence.length > 0 ? (
          <ul className="divide-y divide-border">
            {data.presence.map(({ employee, state }) => (
              <li
                key={employee.id}
                className="flex items-center justify-between py-2.5 text-sm first:pt-0 last:pb-0"
              >
                <span className="text-foreground">
                  {employee.first_name} {employee.last_name}
                </span>
                <Badge tone={PRESENCE_TONE[state]}>{t(PRESENCE_LABEL_KEY[state])}</Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">{t("dashboard.noEmployees")}</p>
        )}
      </Card>

      <Card>
        <h2 className="mb-4 text-sm font-medium text-foreground">
          {t("dashboard.recentTitle")}
        </h2>
        {data.recentEntries.length > 0 ? (
          <ul className="divide-y divide-border">
            {data.recentEntries.map((entry) => (
              <li
                key={entry.id}
                className="flex items-center justify-between py-2.5 text-sm first:pt-0 last:pb-0"
              >
                <span className="text-muted">
                  {new Date(entry.occurred_at).toLocaleTimeString("fr-BE", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
                <span className="flex-1 px-3 text-foreground">{entry.employeeName}</span>
                <Badge tone="neutral">{TYPE_LABELS[entry.type]}</Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">{t("dashboard.noPunchesToday")}</p>
        )}
      </Card>
    </div>
  );
}
