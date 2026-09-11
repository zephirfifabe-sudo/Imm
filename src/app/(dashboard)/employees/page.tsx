import Link from "next/link";
import { requireCurrentUser } from "@/lib/auth/current-user";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { setEmployeeStatusAction } from "./actions";
import { getTranslator } from "@/i18n";

const t = getTranslator();

export default async function EmployeesPage() {
  const { company } = await requireCurrentUser();

  const supabase = await createSupabaseServerClient();
  const [{ data: employees }, { data: sites }] = await Promise.all([
    supabase
      .from("employees")
      .select("*")
      .eq("company_id", company.id)
      .order("created_at", { ascending: true }),
    supabase.from("sites").select("id, name").eq("company_id", company.id),
  ]);

  const siteNameById = new Map((sites ?? []).map((site) => [site.id, site.name]));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">
          {t("employees.title")}
        </h1>
        <Link href="/employees/new">
          <Button>{t("employees.addTitle")}</Button>
        </Link>
      </div>

      <Card>
        {employees && employees.length > 0 ? (
          <ul className="divide-y divide-border">
            {employees.map((employee) => {
              const isActive = employee.status === "ACTIVE";
              const nextStatus = isActive ? "INACTIVE" : "ACTIVE";

              return (
                <li
                  key={employee.id}
                  className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0"
                >
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      {employee.first_name} {employee.last_name}
                    </p>
                    <p className="text-xs text-muted">
                      {employee.internal_code}
                      {employee.job_title ? ` · ${employee.job_title}` : ""}
                      {employee.site_id && siteNameById.has(employee.site_id)
                        ? ` · ${siteNameById.get(employee.site_id)}`
                        : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge tone={isActive ? "success" : "neutral"}>
                      {t(isActive ? "employees.statusActive" : "employees.statusInactive")}
                    </Badge>
                    <Link href={`/employees/${employee.id}/edit`}>
                      <Button variant="secondary" className="px-3 py-1.5 text-xs">
                        {t("employees.edit")}
                      </Button>
                    </Link>
                    <form
                      action={setEmployeeStatusAction.bind(
                        null,
                        employee.id,
                        nextStatus,
                      )}
                    >
                      <Button
                        type="submit"
                        variant="ghost"
                        className="px-3 py-1.5 text-xs"
                      >
                        {t(isActive ? "employees.deactivate" : "employees.activate")}
                      </Button>
                    </form>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-sm text-muted">{t("employees.empty")}</p>
        )}
      </Card>
    </div>
  );
}
