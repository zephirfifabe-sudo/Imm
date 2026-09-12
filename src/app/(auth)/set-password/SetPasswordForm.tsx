"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { getTranslator } from "@/i18n";
import { setPasswordAction } from "./actions";

const t = getTranslator();

const ERROR_KEYS: Record<string, string> = {
  invalid_input: "auth.invalidInput",
  no_session: "auth.setPasswordNoSession",
  generic_error: "auth.genericError",
};

export function SetPasswordForm() {
  const [state, formAction, isPending] = useActionState(setPasswordAction, undefined);

  return (
    <form action={formAction} className="space-y-4">
      <div>
        <Label htmlFor="password">{t("auth.newPasswordLabel")}</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
        />
      </div>
      {state?.ok === false && (
        <p role="alert" className="text-sm text-danger">
          {t(ERROR_KEYS[state.error] ?? "auth.genericError")}
        </p>
      )}
      <Button type="submit" className="w-full" disabled={isPending}>
        {t("auth.setPasswordSubmit")}
      </Button>
    </form>
  );
}
