import { requireAdmin } from "@/lib/auth/current-user";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { SiteForm } from "./SiteForm";
import { deleteSiteAction } from "./actions";
import { getTranslator } from "@/i18n";

const t = getTranslator();

export default async function SitesSettingsPage() {
  await requireAdmin();

  const supabase = await createSupabaseServerClient();
  const { data: sites } = await supabase
    .from("sites")
    .select("*")
    .order("created_at", { ascending: true });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-foreground">
        {t("settings.sites.title")}
      </h1>

      <Card>
        {sites && sites.length > 0 ? (
          <ul className="divide-y divide-border">
            {sites.map((site) => (
              <li
                key={site.id}
                className="flex items-center justify-between py-3 first:pt-0 last:pb-0"
              >
                <div>
                  <p className="text-sm font-medium text-foreground">{site.name}</p>
                  {site.address && (
                    <p className="text-xs text-muted">{site.address}</p>
                  )}
                </div>
                <form action={deleteSiteAction.bind(null, site.id)}>
                  <Button type="submit" variant="ghost" className="text-danger">
                    {t("common.delete")}
                  </Button>
                </form>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">{t("settings.sites.empty")}</p>
        )}
      </Card>

      <Card>
        <h2 className="mb-4 text-sm font-medium text-foreground">
          {t("settings.sites.addTitle")}
        </h2>
        <SiteForm />
      </Card>
    </div>
  );
}
