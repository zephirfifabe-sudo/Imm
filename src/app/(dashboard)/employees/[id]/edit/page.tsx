import { notFound } from "next/navigation";
import { requireCurrentUser } from "@/lib/auth/current-user";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { EmployeeForm } from "../../EmployeeForm";
import { updateEmployeeAction, regenerateQrTokenAction } from "../../actions";
import { getTranslator } from "@/i18n";
import { getEmployeeSchedulingProfile } from "@/lib/scheduling/mutations";
import { AppAccessCard } from "./AppAccessCard";

const t = getTranslator();

export default async function EditEmployeePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { company } = await requireCurrentUser();

  const supabase = await createSupabaseServerClient();
  const [{ data: employee }, { data: sites }] = await Promise.all([
    supabase
      .from("employees")
      .select("*")
      .eq("id", id)
      .eq("company_id", company.id)
      .maybeSingle(),
    supabase
      .from("sites")
      .select("*")
      .eq("company_id", company.id)
      .order("name", { ascending: true }),
  ]);

  if (!employee) {
    notFound();
  }

  const schedulingProfile = await getEmployeeSchedulingProfile(company.id, employee.id);
  const boundUpdateAction = updateEmployeeAction.bind(null, employee.id);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-foreground">
        {t("employees.editTitle")}
      </h1>

      <Card>
        <EmployeeForm
          action={boundUpdateAction}
          sites={sites ?? []}
          defaultValues={{
            firstName: employee.first_name,
            lastName: employee.last_name,
            email: employee.email ?? undefined,
            internalCode: employee.internal_code,
            jobTitle: employee.job_title ?? undefined,
            siteId: employee.site_id ?? undefined,
            nfcToken: employee.nfc_token ?? undefined,
            contractHoursPerWeek: schedulingProfile
              ? Number(schedulingProfile.contract_hours_per_week)
              : undefined,
            contractType: schedulingProfile?.contract_type,
            dayOnly: schedulingProfile?.day_only,
            nightOnly: schedulingProfile?.night_only,
            minNightsPerPeriod: schedulingProfile?.min_nights_per_period,
            maxNightsPerPeriod: schedulingProfile?.max_nights_per_period,
          }}
          submitLabel={t("common.save")}
        />
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-medium text-foreground">
          {t("employees.appAccessTitle")}
        </h2>
        <AppAccessCard
          employeeId={employee.id}
          hasEmail={Boolean(employee.email)}
          hasAppAccess={Boolean(employee.auth_user_id)}
        />
      </Card>

      <Card>
        <p className="text-sm font-medium text-foreground">
          {t("employees.qrTokenLabel")}
        </p>
        <p className="mt-1 break-all font-mono text-xs text-muted">
          {employee.qr_token}
        </p>
        <form action={regenerateQrTokenAction.bind(null, employee.id)} className="mt-3">
          <Button type="submit" variant="secondary">
            {t("employees.regenerateQr")}
          </Button>
        </form>
      </Card>
    </div>
  );
}
