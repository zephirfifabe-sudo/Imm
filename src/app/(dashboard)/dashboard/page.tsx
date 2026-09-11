import { requireCurrentUser } from "@/lib/auth/current-user";
import { logoutAction } from "../actions";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { getTranslator } from "@/i18n";

const t = getTranslator();

export default async function DashboardPage() {
  const { user, company } = await requireCurrentUser();

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-10">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">
            {t("dashboard.greeting", { name: user.first_name })}
          </h1>
          <p className="text-sm text-muted">{company.name}</p>
        </div>
        <form action={logoutAction}>
          <Button type="submit" variant="secondary">
            Déconnexion
          </Button>
        </form>
      </header>

      <Card>
        <p className="text-sm text-muted">
          Le tableau de bord de présence sera construit en Phase 5. Cette page
          confirme que l&apos;authentification, l&apos;isolation
          multi-tenant et le layout de base fonctionnent.
        </p>
      </Card>
    </main>
  );
}
