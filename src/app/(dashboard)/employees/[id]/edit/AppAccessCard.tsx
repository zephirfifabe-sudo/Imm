"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { getTranslator } from "@/i18n";
import {
  inviteEmployeeToAppAction,
  revokeEmployeeAppAccessAction,
  type InviteEmployeeToAppState,
} from "../../actions";

const t = getTranslator();

const ERROR_KEYS: Record<string, string> = {
  no_email: "employees.appAccessNoEmail",
  already_invited: "employees.appAccessAlreadyInvited",
  email_already_used: "employees.appAccessEmailTaken",
  not_found: "auth.genericError",
  generic_error: "auth.genericError",
};

export function AppAccessCard({
  employeeId,
  hasEmail,
  hasAppAccess,
}: {
  employeeId: string;
  hasEmail: boolean;
  hasAppAccess: boolean;
}) {
  const [state, invite, isPending] = useActionState<InviteEmployeeToAppState, FormData>(
    () => inviteEmployeeToAppAction(employeeId),
    undefined,
  );

  if (!hasEmail) {
    return <p className="text-sm text-muted">{t("employees.appAccessNoEmail")}</p>;
  }

  if (hasAppAccess) {
    return (
      <div className="flex items-center justify-between">
        <Badge tone="success">{t("employees.appAccessActive")}</Badge>
        <form action={revokeEmployeeAppAccessAction.bind(null, employeeId)}>
          <Button type="submit" variant="ghost" className="text-danger">
            {t("employees.appAccessRevoke")}
          </Button>
        </form>
      </div>
    );
  }

  return (
    <form action={invite} className="space-y-3">
      <p className="text-sm text-muted">{t("employees.appAccessHint")}</p>
      {state?.ok === false && (
        <p role="alert" className="text-sm text-danger">
          {t(ERROR_KEYS[state.error] ?? "auth.genericError")}
        </p>
      )}
      {state?.ok === true && (
        <p role="status" className="text-sm text-primary">
          {t("employees.appAccessInviteSent")}
        </p>
      )}
      <Button type="submit" variant="secondary" disabled={isPending}>
        {t("employees.appAccessInvite")}
      </Button>
    </form>
  );
}
