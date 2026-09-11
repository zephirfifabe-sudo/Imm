import { notFound } from "next/navigation";
import { requireCurrentUser } from "@/lib/auth/current-user";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getCorrectionsForEntries } from "@/lib/corrections/queries";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { CorrectionForm } from "./CorrectionForm";
import { getTranslator } from "@/i18n";
import type { TimeEntryType } from "@/types/database";

const t = getTranslator();

const TYPE_LABELS: Record<TimeEntryType, string> = {
  CLOCK_IN: "Arrivée",
  CLOCK_OUT: "Départ",
  BREAK_START: "Pause",
  BREAK_END: "Reprise",
};

function toDatetimeLocalValue(iso: string): string {
  const date = new Date(iso);
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("fr-BE", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

export default async function CorrectionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { company } = await requireCurrentUser();

  const supabase = await createSupabaseServerClient();
  const { data: entry } = await supabase
    .from("time_entries")
    .select("*")
    .eq("id", id)
    .eq("company_id", company.id)
    .maybeSingle();

  if (!entry) {
    notFound();
  }

  const { data: employee } = await supabase
    .from("employees")
    .select("first_name, last_name")
    .eq("id", entry.employee_id)
    .maybeSingle();

  const correctionsByEntry = await getCorrectionsForEntries(company.id, [entry.id]);
  const previousCorrections = correctionsByEntry.get(entry.id) ?? [];

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-foreground">
        {t("corrections.title")}
      </h1>

      <Card>
        <p className="text-sm text-muted">{t("corrections.originalLabel")}</p>
        <p className="mt-1 text-foreground">
          <span className="font-semibold">
            {employee ? `${employee.first_name} ${employee.last_name}` : "—"}
          </span>{" "}
          — {TYPE_LABELS[entry.type]} — {formatDateTime(entry.occurred_at)}
        </p>
      </Card>

      {previousCorrections.length > 0 && (
        <Card>
          <p className="mb-3 text-sm font-medium text-foreground">
            {t("corrections.historyLabel")}
          </p>
          <ul className="space-y-2">
            {previousCorrections.map((correction) => (
              <li key={correction.id} className="text-sm text-muted">
                <Badge tone="neutral" className="mr-2">
                  {formatDateTime(correction.previous_occurred_at)} →{" "}
                  {formatDateTime(correction.new_occurred_at)}
                </Badge>
                {correction.reason} ({formatDateTime(correction.created_at)})
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <CorrectionForm
          timeEntryId={entry.id}
          defaultDateTime={toDatetimeLocalValue(entry.occurred_at)}
        />
      </Card>
    </div>
  );
}
