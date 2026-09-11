"use client";

import { useActionState } from "react";
import { createSiteAction } from "./actions";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { getTranslator } from "@/i18n";

const t = getTranslator();

export function SiteForm() {
  const [state, formAction, isPending] = useActionState(
    createSiteAction,
    undefined,
  );

  return (
    <form action={formAction} className="space-y-4">
      <div>
        <Label htmlFor="site-name">{t("settings.sites.nameLabel")}</Label>
        <Input id="site-name" name="name" required minLength={2} maxLength={200} />
      </div>
      <div>
        <Label htmlFor="site-address">{t("settings.sites.addressLabel")}</Label>
        <Input id="site-address" name="address" maxLength={500} />
      </div>
      {state?.ok === false && (
        <p role="alert" className="text-sm text-danger">
          {t(state.error === "invalid_input" ? "auth.invalidInput" : "auth.genericError")}
        </p>
      )}
      <Button type="submit" disabled={isPending}>
        {t("common.add")}
      </Button>
    </form>
  );
}
