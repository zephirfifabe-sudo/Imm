"use client";

import { useActionState } from "react";
import { createTerminalAction } from "./actions";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { getTranslator } from "@/i18n";
import type { Site } from "@/types/database";

const t = getTranslator();

export function TerminalForm({ sites }: { sites: Site[] }) {
  const [state, formAction, isPending] = useActionState(
    createTerminalAction,
    undefined,
  );

  return (
    <form action={formAction} className="space-y-4">
      <div>
        <Label htmlFor="terminal-name">{t("settings.terminals.nameLabel")}</Label>
        <Input id="terminal-name" name="name" required minLength={2} maxLength={200} />
      </div>
      <div>
        <Label htmlFor="terminal-siteId">{t("employees.siteLabel")}</Label>
        <select
          id="terminal-siteId"
          name="siteId"
          defaultValue=""
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
      {state?.ok === false && (
        <p role="alert" className="text-sm text-danger">
          {t(state.error === "invalid_input" ? "auth.invalidInput" : "auth.genericError")}
        </p>
      )}
      {state?.ok === true && (
        <p role="status" className="text-sm text-foreground">
          {t("settings.terminals.activationCodeIntro")}{" "}
          <span className="font-mono text-lg font-bold tracking-widest text-primary">
            {state.activationCode}
          </span>
        </p>
      )}
      <Button type="submit" disabled={isPending}>
        {t("common.add")}
      </Button>
    </form>
  );
}
