import Link from "next/link";
import { requireCurrentUser } from "@/lib/auth/current-user";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getHistory } from "@/lib/history/queries";
import { getCorrectionsForEntries } from "@/lib/corrections/queries";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { getTranslator } from "@/i18n";
import type { TimeEntryType } from "@/types/database";
import type { Anomaly } from "@/lib/timeclock/summary";

const t = getTranslator();

const TYPE_LABELS: Record<TimeEntryType, string> = {
  CLOCK_IN: "Arrivée",
  CLOCK_OUT: "Départ",
  BREAK_START: "Pause",
  BREAK_END: "Reprise",
};

function formatMinutes(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}h${m.toString().padStart(2, "0")}`;
}

function formatDateKey(dateKey: string): string {
  return new Date(`${dateKey}T00:00:00`).toLocaleDateString("fr-BE", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}

function toDateInputValue(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export default async function HistoryPage({
  searchParams,
}: {
  searchParams: Promise<{
    employeeId?: string;
    siteId?: string;
    from?: string;
    to?: string;
  }>;
}) {
  const { company } = await requireCurrentUser();
  const params = await searchParams;

  const today = new Date();
  const defaultFrom = new Date(today);
  defaultFrom.setDate(defaultFrom.getDate() - 6);

  const from = params.from ? new Date(params.from) : defaultFrom;
  const to = params.to ? new Date(params.to) : today;
  const employeeId = params.employeeId || undefined;
  const siteId = params.siteId || undefined;

  const supabase = await createSupabaseServerClient();
  const [{ data: employees }, { data: sites }, groups] = await Promise.all([
    supabase
      .from("employees")
      .select("id, first_name, last_name")
      .eq("company_id", company.id)
      .order("first_name", { ascending: true }),
    supabase
      .from("sites")
      .select("id, name")
      .eq("company_id", company.id)
      .order("name", { ascending: true }),
    getHistory(company.id, { employeeId, siteId, from, to }),
  ]);

  const exportParams = new URLSearchParams({
    from: toDateInputValue(from),
    to: toDateInputValue(to),
  });
  if (employeeId) exportParams.set("employeeId", employeeId);
  if (siteId) exportParams.set("siteId", siteId);

  const allEntryIds = groups.flatMap((group) => group.entries.map((e) => e.id));
  const correctionsByEntry = await getCorrectionsForEntries(company.id, allEntryIds);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-foreground">{t("history.title")}</h1>

      <Card>
        <form className="grid grid-cols-2 gap-3 sm:grid-cols-4 sm:items-end" method="get">
          <div className="col-span-2 sm:col-span-1">
            <label className="mb-1.5 block text-sm font-medium text-foreground" htmlFor="employeeId">
              {t("history.employeeLabel")}
            </label>
            <select
              id="employeeId"
              name="employeeId"
              defaultValue={employeeId ?? ""}
              className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm"
            >
              <option value="">{t("history.allEmployees")}</option>
              {(employees ?? []).map((e) => (
                <option key={e.id} value={e.id}>
                  {e.first_name} {e.last_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground" htmlFor="siteId">
              {t("employees.siteLabel")}
            </label>
            <select
              id="siteId"
              name="siteId"
              defaultValue={siteId ?? ""}
              className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm"
            >
              <option value="">{t("history.allSites")}</option>
              {(sites ?? []).map((site) => (
                <option key={site.id} value={site.id}>
                  {site.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground" htmlFor="from">
              {t("history.fromLabel")}
            </label>
            <input
              id="from"
              name="from"
              type="date"
              defaultValue={toDateInputValue(from)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground" htmlFor="to">
              {t("history.toLabel")}
            </label>
            <input
              id="to"
              name="to"
              type="date"
              defaultValue={toDateInputValue(to)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm"
            />
          </div>
          <Button type="submit">{t("history.filter")}</Button>
        </form>
      </Card>

      <div className="flex flex-wrap gap-3">
        <a href={`/api/exports/time-entries?${exportParams}&format=csv`}>
          <Button variant="secondary">{t("history.exportCsv")}</Button>
        </a>
        <a href={`/api/exports/time-entries?${exportParams}&format=xlsx`}>
          <Button variant="secondary">{t("history.exportExcel")}</Button>
        </a>
      </div>

      {groups.length > 0 ? (
        <div className="space-y-4">
          {groups.map((group) => (
            <Card key={`${group.employeeId}-${group.dateKey}`}>
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold text-foreground">
                    {group.employeeName}
                  </p>
                  <p className="text-xs capitalize text-muted">
                    {formatDateKey(group.dateKey)}
                  </p>
                </div>
                {group.anomalies.length > 0 && (
                  <div className="flex flex-wrap justify-end gap-1">
                    {group.anomalies.map((anomaly: Anomaly, i) => (
                      <Badge key={i} tone="warning">
                        {t(`history.anomaly.${anomaly}`)}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
              <ul className="mb-3 space-y-1 text-sm text-foreground">
                {group.entries.map((entry) => {
                  const wasCorrected = (correctionsByEntry.get(entry.id)?.length ?? 0) > 0;
                  return (
                    <li key={entry.id} className="flex items-center gap-3">
                      <span className="text-muted">
                        {new Date(entry.occurred_at).toLocaleTimeString("fr-BE", {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                      <span>{TYPE_LABELS[entry.type]}</span>
                      {wasCorrected && (
                        <Badge tone="warning">{t("corrections.correctedBadge")}</Badge>
                      )}
                      <Link
                        href={`/corrections/${entry.id}`}
                        className="ml-auto text-xs text-primary hover:underline"
                      >
                        {t("corrections.correctLink")}
                      </Link>
                    </li>
                  );
                })}
              </ul>
              <div className="flex gap-6 border-t border-border pt-3 text-sm">
                <p>
                  <span className="text-muted">{t("history.workedLabel")} : </span>
                  <span className="font-semibold text-foreground">
                    {formatMinutes(group.workedMinutes)}
                  </span>
                </p>
                {group.breakMinutes > 0 && (
                  <p>
                    <span className="text-muted">{t("history.breakLabel")} : </span>
                    <span className="font-semibold text-foreground">
                      {formatMinutes(group.breakMinutes)}
                    </span>
                  </p>
                )}
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <p className="text-sm text-muted">{t("history.noEntries")}</p>
        </Card>
      )}
    </div>
  );
}
