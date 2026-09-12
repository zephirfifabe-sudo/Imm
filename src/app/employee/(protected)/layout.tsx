import type { ReactNode } from "react";
import { requireCurrentEmployee } from "@/lib/auth/current-employee";
import { employeeLogoutAction } from "../actions";
import { Button } from "@/components/ui/Button";
import { getTranslator } from "@/i18n";

const t = getTranslator();

export default async function EmployeeLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  const { employee } = await requireCurrentEmployee();

  return (
    <div className="flex min-h-screen flex-1 flex-col">
      <header className="border-b border-border bg-background">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between px-4 py-4">
          <div>
            <p className="text-sm font-semibold text-foreground">
              {t("common.appName")}
            </p>
            <p className="text-xs text-muted">
              {employee.first_name} {employee.last_name}
            </p>
          </div>
          <form action={employeeLogoutAction}>
            <Button type="submit" variant="secondary" className="px-3 py-1.5 text-xs">
              {t("nav.logout")}
            </Button>
          </form>
        </div>
      </header>
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-10">{children}</main>
    </div>
  );
}
