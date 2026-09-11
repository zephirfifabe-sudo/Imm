"use client";

import { useActionState } from "react";
import { inviteUserAction } from "./actions";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { getTranslator } from "@/i18n";

const t = getTranslator();

const ERROR_KEYS = {
  invalid_input: "auth.invalidInput",
  email_taken_in_company: "settings.users.emailTakenInCompany",
  generic_error: "auth.genericError",
} as const;

export function InviteUserForm() {
  const [state, formAction, isPending] = useActionState(
    inviteUserAction,
    undefined,
  );

  return (
    <form action={formAction} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="invite-firstName">{t("auth.firstNameLabel")}</Label>
          <Input id="invite-firstName" name="firstName" required maxLength={100} />
        </div>
        <div>
          <Label htmlFor="invite-lastName">{t("auth.lastNameLabel")}</Label>
          <Input id="invite-lastName" name="lastName" required maxLength={100} />
        </div>
      </div>
      <div>
        <Label htmlFor="invite-email">{t("auth.emailLabel")}</Label>
        <Input id="invite-email" name="email" type="email" required />
      </div>
      <div>
        <Label htmlFor="invite-role">{t("settings.users.roleLabel")}</Label>
        <select
          id="invite-role"
          name="role"
          defaultValue="MANAGER"
          className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm"
        >
          <option value="MANAGER">{t("settings.users.roleManager")}</option>
          <option value="ADMIN">{t("settings.users.roleAdmin")}</option>
        </select>
      </div>
      {state?.ok === false && (
        <p role="alert" className="text-sm text-danger">
          {t(ERROR_KEYS[state.error])}
        </p>
      )}
      {state?.ok === true && (
        <p role="status" className="text-sm text-primary">
          {t("settings.users.inviteSent")}
        </p>
      )}
      <Button type="submit" disabled={isPending}>
        {t("settings.users.invite")}
      </Button>
    </form>
  );
}
