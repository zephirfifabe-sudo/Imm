"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { getTranslator } from "@/i18n";
import type { Site } from "@/types/database";
import type { EmployeeFormState } from "./actions";
import { CONTRACT_TYPES } from "@/lib/scheduling/profile-schema";

const t = getTranslator();

const ERROR_KEYS: Record<string, string> = {
  invalid_input: "auth.invalidInput",
  duplicate_code: "employees.duplicateCode",
  duplicate_pin: "employees.duplicatePin",
  plan_limit_reached: "employees.planLimitReached",
  generic_error: "auth.genericError",
};

export function EmployeeForm({
  action,
  sites,
  defaultValues,
  submitLabel,
}: {
  action: (
    state: EmployeeFormState,
    formData: FormData,
  ) => Promise<EmployeeFormState>;
  sites: Site[];
  defaultValues?: {
    firstName?: string;
    lastName?: string;
    email?: string;
    internalCode?: string;
    jobTitle?: string;
    siteId?: string;
    nfcToken?: string;
    contractHoursPerWeek?: number;
    contractType?: string;
    dayOnly?: boolean;
    nightOnly?: boolean;
    minNightsPerPeriod?: number;
    maxNightsPerPeriod?: number;
  };
  submitLabel: string;
}) {
  const [state, formAction, isPending] = useActionState(action, undefined);

  return (
    <form action={formAction} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="firstName">{t("auth.firstNameLabel")}</Label>
          <Input
            id="firstName"
            name="firstName"
            required
            maxLength={100}
            defaultValue={defaultValues?.firstName}
          />
        </div>
        <div>
          <Label htmlFor="lastName">{t("auth.lastNameLabel")}</Label>
          <Input
            id="lastName"
            name="lastName"
            required
            maxLength={100}
            defaultValue={defaultValues?.lastName}
          />
        </div>
      </div>
      <div>
        <Label htmlFor="internalCode">{t("employees.internalCodeLabel")}</Label>
        <Input
          id="internalCode"
          name="internalCode"
          required
          maxLength={50}
          defaultValue={defaultValues?.internalCode}
        />
      </div>
      <div>
        <Label htmlFor="email">{t("auth.emailLabel")}</Label>
        <Input
          id="email"
          name="email"
          type="email"
          defaultValue={defaultValues?.email}
        />
      </div>
      <div>
        <Label htmlFor="jobTitle">{t("employees.jobTitleLabel")}</Label>
        <Input
          id="jobTitle"
          name="jobTitle"
          maxLength={100}
          defaultValue={defaultValues?.jobTitle}
        />
      </div>
      <div>
        <Label htmlFor="siteId">{t("employees.siteLabel")}</Label>
        <select
          id="siteId"
          name="siteId"
          defaultValue={defaultValues?.siteId ?? ""}
          className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm"
        >
          <option value="">{t("employees.siteNone")}</option>
          {sites.map((site) => (
            <option key={site.id} value={site.id}>
              {site.name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <Label htmlFor="pin">{t("employees.pinLabel")}</Label>
        <Input id="pin" name="pin" inputMode="numeric" pattern="\d{4}" maxLength={4} />
        <p className="mt-1 text-xs text-muted">{t("employees.pinHint")}</p>
      </div>
      <div>
        <Label htmlFor="nfcToken">{t("employees.nfcTokenLabel")}</Label>
        <Input
          id="nfcToken"
          name="nfcToken"
          maxLength={200}
          defaultValue={defaultValues?.nfcToken}
        />
      </div>
      <div className="border-t border-border pt-4">
        <p className="mb-3 text-sm font-medium text-foreground">
          {t("employees.schedulingSectionTitle")}
        </p>
        <p className="mb-3 text-xs text-muted">{t("employees.schedulingSectionHint")}</p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="contractHoursPerWeek">
              {t("employees.contractHoursLabel")}
            </Label>
            <Input
              id="contractHoursPerWeek"
              name="contractHoursPerWeek"
              type="number"
              min={1}
              max={60}
              step={0.5}
              defaultValue={defaultValues?.contractHoursPerWeek}
            />
          </div>
          <div>
            <Label htmlFor="contractType">{t("employees.contractTypeLabel")}</Label>
            <select
              id="contractType"
              name="contractType"
              defaultValue={defaultValues?.contractType ?? "CDI"}
              className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm"
            >
              {CONTRACT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="mt-3 flex gap-4">
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input
              type="checkbox"
              name="dayOnly"
              value="true"
              defaultChecked={defaultValues?.dayOnly}
            />
            {t("employees.dayOnlyLabel")}
          </label>
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input
              type="checkbox"
              name="nightOnly"
              value="true"
              defaultChecked={defaultValues?.nightOnly}
            />
            {t("employees.nightOnlyLabel")}
          </label>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="minNightsPerPeriod">
              {t("employees.minNightsLabel")}
            </Label>
            <Input
              id="minNightsPerPeriod"
              name="minNightsPerPeriod"
              type="number"
              min={0}
              max={28}
              defaultValue={defaultValues?.minNightsPerPeriod ?? 0}
            />
          </div>
          <div>
            <Label htmlFor="maxNightsPerPeriod">
              {t("employees.maxNightsLabel")}
            </Label>
            <Input
              id="maxNightsPerPeriod"
              name="maxNightsPerPeriod"
              type="number"
              min={0}
              max={28}
              defaultValue={defaultValues?.maxNightsPerPeriod ?? 8}
            />
          </div>
        </div>
      </div>
      {state?.ok === false && (
        <p role="alert" className="text-sm text-danger">
          {t(ERROR_KEYS[state.error] ?? "auth.genericError")}
        </p>
      )}
      {state?.ok === true && (
        <p role="status" className="text-sm text-primary">
          {t("common.savedSuccessfully")}
        </p>
      )}
      <Button type="submit" disabled={isPending}>
        {submitLabel}
      </Button>
    </form>
  );
}
