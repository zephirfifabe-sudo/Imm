"use client";

import { useActionState } from "react";
import { submitCorrectionAction } from "./actions";
import { Button } from "@/components/ui/Button";
import { Label } from "@/components/ui/Label";
import { getTranslator } from "@/i18n";

const t = getTranslator();

const ERROR_KEYS: Record<string, string> = {
  invalid_input: "auth.invalidInput",
  not_found: "corrections.notFound",
  generic_error: "auth.genericError",
};

export function CorrectionForm({
  timeEntryId,
  defaultDateTime,
}: {
  timeEntryId: string;
  defaultDateTime: string;
}) {
  const boundAction = submitCorrectionAction.bind(null, timeEntryId);
  const [state, formAction, isPending] = useActionState(boundAction, undefined);

  return (
    <form action={formAction} className="space-y-4">
      <div>
        <Label htmlFor="newOccurredAt">{t("corrections.newTimeLabel")}</Label>
        <input
          id="newOccurredAt"
          name="newOccurredAt"
          type="datetime-local"
          defaultValue={defaultDateTime}
          required
          className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm"
        />
      </div>
      <div>
        <Label htmlFor="reason">{t("corrections.reasonLabel")}</Label>
        <textarea
          id="reason"
          name="reason"
          required
          minLength={3}
          maxLength={500}
          rows={3}
          className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm"
        />
      </div>
      {state?.ok === false && (
        <p role="alert" className="text-sm text-danger">
          {t(ERROR_KEYS[state.error] ?? "auth.genericError")}
        </p>
      )}
      <Button type="submit" disabled={isPending}>
        {t("common.save")}
      </Button>
    </form>
  );
}
