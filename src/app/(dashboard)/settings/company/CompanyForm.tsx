"use client";

import { useActionState } from "react";
import { updateCompanyAction } from "./actions";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { getTranslator } from "@/i18n";
import type { Company } from "@/types/database";

const t = getTranslator();

export function CompanyForm({ company }: { company: Company }) {
  const [state, formAction, isPending] = useActionState(
    updateCompanyAction,
    undefined,
  );

  return (
    <form action={formAction} className="space-y-4">
      <div>
        <Label htmlFor="name">{t("settings.company.nameLabel")}</Label>
        <Input
          id="name"
          name="name"
          defaultValue={company.name}
          required
          minLength={2}
          maxLength={200}
        />
      </div>
      <div>
        <Label htmlFor="vatNumber">{t("settings.company.vatLabel")}</Label>
        <Input
          id="vatNumber"
          name="vatNumber"
          defaultValue={company.vat_number ?? ""}
          maxLength={50}
        />
      </div>
      <div>
        <Label htmlFor="address">{t("settings.company.addressLabel")}</Label>
        <Input
          id="address"
          name="address"
          defaultValue={company.address ?? ""}
          maxLength={500}
        />
      </div>
      {state?.ok === false && (
        <p role="alert" className="text-sm text-danger">
          {t(state.error === "invalid_input" ? "auth.invalidInput" : "auth.genericError")}
        </p>
      )}
      {state?.ok === true && (
        <p role="status" className="text-sm text-primary">
          {t("common.savedSuccessfully")}
        </p>
      )}
      <Button type="submit" disabled={isPending}>
        {t("common.save")}
      </Button>
    </form>
  );
}
