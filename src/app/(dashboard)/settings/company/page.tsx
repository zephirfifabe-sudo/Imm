import { requireAdmin } from "@/lib/auth/current-user";
import { Card } from "@/components/ui/Card";
import { CompanyForm } from "./CompanyForm";
import { getTranslator } from "@/i18n";

const t = getTranslator();

export default async function CompanySettingsPage() {
  const { company } = await requireAdmin();

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-foreground">
        {t("settings.company.title")}
      </h1>
      <Card>
        <CompanyForm company={company} />
      </Card>
    </div>
  );
}
