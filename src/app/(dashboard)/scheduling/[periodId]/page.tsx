import { notFound } from "next/navigation";
import { requireAdmin } from "@/lib/auth/current-user";
import {
  getScheduleGrid,
  getSchedulePeriod,
  listSchedulingEmployees,
} from "@/lib/scheduling/mutations";
import { DEFAULT_SCHEDULING_SETTINGS, type SchedulingSettings } from "@/lib/scheduling/types";
import { SchedulingBoard } from "./SchedulingBoard";
import { getTranslator } from "@/i18n";

const t = getTranslator();

export default async function SchedulePeriodPage({
  params,
}: {
  params: Promise<{ periodId: string }>;
}) {
  const { periodId } = await params;
  const { company } = await requireAdmin();

  const period = await getSchedulePeriod(company.id, periodId);
  if (!period) {
    notFound();
  }

  const employees = await listSchedulingEmployees(company.id);
  const grid = await getScheduleGrid(company.id, periodId, employees);

  const settings: SchedulingSettings = {
    ...DEFAULT_SCHEDULING_SETTINGS,
    ...(period.settings as Partial<SchedulingSettings>),
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">{period.name}</h1>
        <p className="text-sm text-muted">{t("scheduling.periodSubtitle")}</p>
      </div>

      <SchedulingBoard
        periodId={period.id}
        periodStartIso={period.period_start}
        initialSettings={settings}
        employees={employees}
        initialGrid={grid}
      />
    </div>
  );
}
