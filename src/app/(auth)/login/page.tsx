import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { LoginForm } from "./LoginForm";
import { getTranslator } from "@/i18n";

const t = getTranslator();

export default function LoginPage() {
  return (
    <main className="flex min-h-screen flex-1 items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold text-foreground">
            {t("common.appName")}
          </h1>
          <p className="mt-1 text-sm text-muted">{t("common.tagline")}</p>
        </div>
        <Card>
          <h2 className="mb-6 text-lg font-medium text-foreground">
            {t("auth.loginTitle")}
          </h2>
          <LoginForm />
          <p className="mt-4 text-center text-sm text-muted">
            {t("auth.noAccountYet")}{" "}
            <Link href="/signup" className="text-primary hover:underline">
              {t("auth.goToSignup")}
            </Link>
          </p>
        </Card>
      </div>
    </main>
  );
}
