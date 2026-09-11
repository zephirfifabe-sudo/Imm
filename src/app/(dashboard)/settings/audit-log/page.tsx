import { requireAdmin } from "@/lib/auth/current-user";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { Card } from "@/components/ui/Card";
import { getTranslator } from "@/i18n";

const t = getTranslator();

const ACTION_LABELS: Record<string, string> = {
  TIME_ENTRY_CORRECTED: "Pointage corrigé",
};

export default async function AuditLogPage() {
  const { company } = await requireAdmin();

  const supabase = await createSupabaseServerClient();
  const { data: logs } = await supabase
    .from("audit_logs")
    .select("*")
    .eq("company_id", company.id)
    .order("created_at", { ascending: false })
    .limit(50);

  const actorIds = [
    ...new Set(
      (logs ?? [])
        .map((log) => log.actor_user_id)
        .filter((id): id is string => id !== null),
    ),
  ];

  const { data: actors } =
    actorIds.length > 0
      ? await supabase.from("users").select("id, first_name, last_name").in("id", actorIds)
      : { data: [] };

  const actorNameById = new Map(
    (actors ?? []).map((actor) => [actor.id, `${actor.first_name} ${actor.last_name}`]),
  );

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-foreground">{t("auditLog.title")}</h1>

      <Card>
        {logs && logs.length > 0 ? (
          <ul className="divide-y divide-border">
            {logs.map((log) => (
              <li key={log.id} className="py-3 text-sm first:pt-0 last:pb-0">
                <p className="text-foreground">
                  <span className="font-medium">
                    {ACTION_LABELS[log.action] ?? log.action}
                  </span>
                  {log.actor_user_id && (
                    <span className="text-muted">
                      {" "}
                      — {actorNameById.get(log.actor_user_id) ?? "—"}
                    </span>
                  )}
                </p>
                <p className="text-xs text-muted">
                  {new Date(log.created_at).toLocaleString("fr-BE", {
                    dateStyle: "short",
                    timeStyle: "short",
                  })}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">{t("auditLog.empty")}</p>
        )}
      </Card>
    </div>
  );
}
