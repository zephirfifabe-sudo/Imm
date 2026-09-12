import { requireAdmin } from "@/lib/auth/current-user";
import {
  getScheduleGrid,
  getSchedulePeriod,
  listSchedulingEmployees,
} from "@/lib/scheduling/mutations";
import { matrixToCsv } from "@/lib/exports/csv";
import { totalHoursAssigned } from "@/lib/scheduling/engine";
import { TOTAL_DAYS } from "@/lib/scheduling/types";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ periodId: string }> },
) {
  const { periodId } = await params;
  const { company } = await requireAdmin();

  const period = await getSchedulePeriod(company.id, periodId);
  if (!period) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }

  const employees = await listSchedulingEmployees(company.id);
  const grid = await getScheduleGrid(company.id, periodId, employees);

  const header = ["Employé", ...Array.from({ length: TOTAL_DAYS }, (_, i) => `Jour ${i + 1}`), "Total heures"];
  const rows = employees
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((employee) => {
      const schedule = grid[employee.id] ?? new Array(TOTAL_DAYS).fill("");
      return [
        employee.name,
        ...schedule.map((code) => (code === "" ? "repos" : code)),
        String(totalHoursAssigned(schedule)),
      ];
    });

  const csv = matrixToCsv([header, ...rows]);

  return new Response(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="klock-planning_${period.name.replace(/[^a-zA-Z0-9_-]/g, "_")}.csv"`,
    },
  });
}
