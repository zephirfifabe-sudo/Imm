import { requireAdmin } from "@/lib/auth/current-user";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { TerminalForm } from "./TerminalForm";
import { deactivateTerminalAction, reissueActivationCodeAction } from "./actions";
import { getTranslator } from "@/i18n";

const t = getTranslator();

const STATUS_TONE = {
  ACTIVE: "success",
  PENDING_ACTIVATION: "warning",
  INACTIVE: "neutral",
} as const;

export default async function TerminalsSettingsPage() {
  const { company } = await requireAdmin();

  const supabase = await createSupabaseServerClient();
  const [{ data: terminals }, { data: sites }] = await Promise.all([
    supabase
      .from("terminals")
      .select("*")
      .eq("company_id", company.id)
      .order("created_at", { ascending: true }),
    supabase
      .from("sites")
      .select("*")
      .eq("company_id", company.id)
      .order("name", { ascending: true }),
  ]);

  const siteNameById = new Map((sites ?? []).map((site) => [site.id, site.name]));

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-foreground">
        {t("settings.terminals.title")}
      </h1>

      <Card>
        {terminals && terminals.length > 0 ? (
          <ul className="divide-y divide-border">
            {terminals.map((terminal) => (
              <li key={terminal.id} className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
                <div>
                  <p className="text-sm font-medium text-foreground">{terminal.name}</p>
                  <p className="text-xs text-muted">
                    {terminal.site_id && siteNameById.has(terminal.site_id)
                      ? siteNameById.get(terminal.site_id)
                      : t("employees.siteNone")}
                  </p>
                  {terminal.activation_code && (
                    <p className="mt-1 text-xs text-foreground">
                      {t("settings.terminals.activationCodeIntro")}{" "}
                      <span className="font-mono font-bold tracking-widest text-primary">
                        {terminal.activation_code}
                      </span>
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={STATUS_TONE[terminal.status]}>
                    {t(`settings.terminals.status.${terminal.status}`)}
                  </Badge>
                  {terminal.status !== "PENDING_ACTIVATION" && (
                    <form action={reissueActivationCodeAction.bind(null, terminal.id)}>
                      <Button type="submit" variant="secondary" className="px-3 py-1.5 text-xs">
                        {t("settings.terminals.reissueCode")}
                      </Button>
                    </form>
                  )}
                  {terminal.status !== "INACTIVE" && (
                    <form action={deactivateTerminalAction.bind(null, terminal.id)}>
                      <Button type="submit" variant="ghost" className="px-3 py-1.5 text-xs text-danger">
                        {t("settings.terminals.deactivate")}
                      </Button>
                    </form>
                  )}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">{t("settings.terminals.empty")}</p>
        )}
      </Card>

      <Card>
        <h2 className="mb-4 text-sm font-medium text-foreground">
          {t("settings.terminals.addTitle")}
        </h2>
        <TerminalForm sites={sites ?? []} />
      </Card>
    </div>
  );
}
