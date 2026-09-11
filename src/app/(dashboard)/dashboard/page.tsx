import { requireCurrentUser } from "@/lib/auth/current-user";
import { Card } from "@/components/ui/Card";
import { getTranslator } from "@/i18n";

const t = getTranslator();

export default async function DashboardPage() {
  const { user } = await requireCurrentUser();

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-foreground">
        {t("dashboard.greeting", { name: user.first_name })}
      </h1>

      <Card>
        <p className="text-sm text-muted">
          Le tableau de bord de présence sera construit en Phase 5. Cette page
          confirme que l&apos;authentification, l&apos;isolation
          multi-tenant et le layout de base fonctionnent.
        </p>
      </Card>
    </div>
  );
}
