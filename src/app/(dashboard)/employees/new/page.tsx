import { requireCurrentUser } from "@/lib/auth/current-user";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { Card } from "@/components/ui/Card";
import { EmployeeForm } from "../EmployeeForm";
import { createEmployeeAction } from "../actions";
import { getTranslator } from "@/i18n";

const t = getTranslator();

export default async function NewEmployeePage() {
  const { company } = await requireCurrentUser();

  const supabase = await createSupabaseServerClient();
  const [{ data: sites }, { count }] = await Promise.all([
    supabase
      .from("sites")
      .select("*")
      .eq("company_id", company.id)
      .order("name", { ascending: true }),
    supabase
      .from("employees")
      .select("id", { count: "exact", head: true })
      .eq("company_id", company.id),
  ]);

  const suggestedCode = `EMP-${String((count ?? 0) + 1).padStart(4, "0")}`;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-foreground">
        {t("employees.addTitle")}
      </h1>
      <Card>
        <EmployeeForm
          action={createEmployeeAction}
          sites={sites ?? []}
          defaultValues={{ internalCode: suggestedCode }}
          submitLabel={t("common.save")}
        />
      </Card>
    </div>
  );
}
