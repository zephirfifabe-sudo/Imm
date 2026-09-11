"use client";

import { getTranslator } from "@/i18n";

const t = getTranslator();

export function RoleSelect({
  defaultValue,
  disabled,
}: {
  defaultValue: string;
  disabled?: boolean;
}) {
  return (
    <select
      name="role"
      defaultValue={defaultValue}
      disabled={disabled}
      onChange={(event) => event.currentTarget.form?.requestSubmit()}
      className="rounded-lg border border-border bg-background px-2 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
    >
      <option value="ADMIN">{t("settings.users.roleAdmin")}</option>
      <option value="MANAGER">{t("settings.users.roleManager")}</option>
    </select>
  );
}
