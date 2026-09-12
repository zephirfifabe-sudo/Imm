"use client";

import type { SchedulePeriod } from "@/types/database";

export function PeriodSelect({
  periods,
  selectedId,
}: {
  periods: SchedulePeriod[];
  selectedId: string;
}) {
  return (
    <form method="get" className="flex items-center gap-2">
      <select
        name="period"
        defaultValue={selectedId}
        onChange={(e) => e.currentTarget.form?.submit()}
        className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
      >
        {periods.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
    </form>
  );
}
