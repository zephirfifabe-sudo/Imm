import Link from "next/link";
import type { ReactNode } from "react";
import { requireCurrentUser } from "@/lib/auth/current-user";
import { logoutAction } from "./actions";
import { Button } from "@/components/ui/Button";
import { getTranslator } from "@/i18n";

const t = getTranslator();

export default async function DashboardLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  const { user, company } = await requireCurrentUser();
  const isAdmin = user.role === "ADMIN";

  return (
    <div className="flex min-h-screen flex-1 flex-col">
      <header className="border-b border-border bg-background">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between px-4 py-4">
          <div>
            <p className="text-sm font-semibold text-foreground">
              {t("common.appName")}
            </p>
            <p className="text-xs text-muted">{company.name}</p>
          </div>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/dashboard" className="text-foreground hover:text-primary">
              {t("nav.dashboard")}
            </Link>
            <Link href="/employees" className="text-foreground hover:text-primary">
              {t("nav.employees")}
            </Link>
            <Link href="/history" className="text-foreground hover:text-primary">
              {t("nav.history")}
            </Link>
            {isAdmin && (
              <>
                <Link
                  href="/settings/company"
                  className="text-foreground hover:text-primary"
                >
                  {t("nav.settingsCompany")}
                </Link>
                <Link
                  href="/settings/sites"
                  className="text-foreground hover:text-primary"
                >
                  {t("nav.settingsSites")}
                </Link>
                <Link
                  href="/settings/users"
                  className="text-foreground hover:text-primary"
                >
                  {t("nav.settingsUsers")}
                </Link>
                <Link
                  href="/settings/terminals"
                  className="text-foreground hover:text-primary"
                >
                  {t("nav.settingsTerminals")}
                </Link>
              </>
            )}
            <form action={logoutAction}>
              <Button type="submit" variant="secondary" className="px-3 py-1.5 text-xs">
                {t("nav.logout")}
              </Button>
            </form>
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-10">{children}</main>
    </div>
  );
}
