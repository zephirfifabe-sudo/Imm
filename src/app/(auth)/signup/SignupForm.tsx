"use client";

import { useActionState } from "react";
import { signupAction } from "./actions";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { getTranslator } from "@/i18n";

const t = getTranslator();

const ERROR_KEYS = {
  invalid_input: "auth.invalidInput",
  email_taken: "auth.emailTaken",
  generic_error: "auth.genericError",
} as const;

export function SignupForm() {
  const [state, formAction, isPending] = useActionState(signupAction, undefined);

  return (
    <form action={formAction} className="space-y-4">
      <div>
        <Label htmlFor="companyName">{t("auth.companyNameLabel")}</Label>
        <Input id="companyName" name="companyName" required minLength={2} maxLength={200} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="firstName">{t("auth.firstNameLabel")}</Label>
          <Input id="firstName" name="firstName" required maxLength={100} />
        </div>
        <div>
          <Label htmlFor="lastName">{t("auth.lastNameLabel")}</Label>
          <Input id="lastName" name="lastName" required maxLength={100} />
        </div>
      </div>
      <div>
        <Label htmlFor="email">{t("auth.emailLabel")}</Label>
        <Input id="email" name="email" type="email" autoComplete="email" required />
      </div>
      <div>
        <Label htmlFor="password">{t("auth.passwordLabel")}</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          maxLength={72}
        />
      </div>
      {state?.error && (
        <p role="alert" className="text-sm text-danger">
          {t(ERROR_KEYS[state.error])}
        </p>
      )}
      <Button type="submit" className="w-full" disabled={isPending}>
        {t("auth.createAccount")}
      </Button>
    </form>
  );
}
