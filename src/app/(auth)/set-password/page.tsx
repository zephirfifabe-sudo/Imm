import { Card } from "@/components/ui/Card";
import { Logo } from "@/components/ui/Logo";
import { SetPasswordForm } from "./SetPasswordForm";
import { getTranslator } from "@/i18n";

const t = getTranslator();

export default function SetPasswordPage() {
  return (
    <main className="flex min-h-screen flex-1 items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <Logo
            className="justify-center"
            markClassName="h-9 w-9"
            textClassName="text-2xl"
          />
          <p className="mt-1 text-sm text-muted">{t("common.tagline")}</p>
        </div>
        <Card>
          <h2 className="mb-2 text-lg font-medium text-foreground">
            {t("auth.setPasswordTitle")}
          </h2>
          <p className="mb-6 text-sm text-muted">{t("auth.setPasswordHint")}</p>
          <SetPasswordForm />
        </Card>
      </div>
    </main>
  );
}
