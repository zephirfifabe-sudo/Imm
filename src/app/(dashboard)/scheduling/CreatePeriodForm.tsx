"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { getTranslator } from "@/i18n";
import { createSchedulePeriodAction } from "./actions";

const t = getTranslator();

function defaultPeriodStart(): string {
  return new Date().toISOString().slice(0, 10);
}

export function CreatePeriodForm() {
  const [state, formAction, isPending] = useActionState(
    createSchedulePeriodAction,
    undefined,
  );

  return (
    <form action={formAction} className="space-y-4">
      <div>
        <Label htmlFor="period-name">{t("scheduling.periodNameLabel")}</Label>
        <Input id="period-name" name="name" required maxLength={100} placeholder="Horaire 1" />
      </div>
      <div>
        <Label htmlFor="period-start">{t("scheduling.periodStartLabel")}</Label>
        <Input
          id="period-start"
          name="periodStart"
          type="date"
          required
          defaultValue={defaultPeriodStart()}
        />
        <p className="mt-1 text-xs text-muted">{t("scheduling.periodStartHint")}</p>
      </div>
      {state?.ok === false && (
        <p role="alert" className="text-sm text-danger">
          {t(state.error === "invalid_input" ? "auth.invalidInput" : "auth.genericError")}
        </p>
      )}
      <Button type="submit" disabled={isPending}>
        {t("scheduling.createPeriod")}
      </Button>
    </form>
  );
}
