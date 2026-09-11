import { requireCurrentUser } from "@/lib/auth/current-user";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { getTranslator } from "@/i18n";
import type { TimeEntryType } from "@/types/database";

const t = getTranslator();

const TYPE_LABELS: Record<TimeEntryType, string> = {
  CLOCK_IN: "Arrivée",
  CLOCK_OUT: "Départ",
  BREAK_START: "Pause",
  BREAK_END: "Reprise",
};

export default async function DashboardPage() {
  const { user, company } = await requireCurrentUser();

  const supabase = await createSupabaseServerClient();

  // Journée civile approximative (fuseau serveur): un calcul par fuseau
  // d'entreprise viendra avec le vrai dashboard de présence en Phase 5.
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);

  const [{ data: todaysEntries }, { data: employees }] = await Promise.all([
    supabase
      .from("time_entries")
      .select("*")
      .eq("company_id", company.id)
      .gte("occurred_at", startOfToday.toISOString())
      .order("occurred_at", { ascending: false })
      .limit(20),
    supabase.from("employees").select("id, first_name, last_name").eq("company_id", company.id),
  ]);

  const employeeById = new Map((employees ?? []).map((e) => [e.id, e]));

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-foreground">
        {t("dashboard.greeting", { name: user.first_name })}
      </h1>

      <Card>
        <h2 className="mb-4 text-sm font-medium text-foreground">
          Derniers pointages — {t("dashboard.today")}
        </h2>
        {todaysEntries && todaysEntries.length > 0 ? (
          <ul className="divide-y divide-border">
            {todaysEntries.map((entry) => {
              const employee = employeeById.get(entry.employee_id);
              return (
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
                  <span className="flex-1 px-3 text-foreground">
                    {employee ? `${employee.first_name} ${employee.last_name}` : "—"}
                  </span>
                  <Badge tone="neutral">{TYPE_LABELS[entry.type]}</Badge>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-sm text-muted">Aucun pointage aujourd&apos;hui.</p>
        )}
      </Card>
    </div>
  );
}
