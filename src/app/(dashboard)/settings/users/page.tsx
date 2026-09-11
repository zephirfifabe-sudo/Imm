import { requireAdmin } from "@/lib/auth/current-user";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { RoleSelect } from "./RoleSelect";
import { InviteUserForm } from "./InviteUserForm";
import { updateUserRoleAction, removeUserAction } from "./actions";
import { getTranslator } from "@/i18n";

const t = getTranslator();

export default async function UsersSettingsPage() {
  const { user: currentUser, company } = await requireAdmin();

  const supabase = await createSupabaseServerClient();
  const { data: members } = await supabase
    .from("users")
    .select("*")
    .eq("company_id", company.id)
    .order("created_at", { ascending: true });

  const adminCount =
    members?.filter((member) => member.role === "ADMIN").length ?? 0;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-foreground">
        {t("settings.users.title")}
      </h1>

      <Card>
        {members && members.length > 0 ? (
          <ul className="divide-y divide-border">
            {members.map((member) => {
              const isSelf = member.id === currentUser.id;
              const isLastAdmin = member.role === "ADMIN" && adminCount <= 1;

              return (
                <li
                  key={member.id}
                  className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0"
                >
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      {member.first_name} {member.last_name}{" "}
                      {isSelf && (
                        <span className="text-xs text-muted">
                          {t("settings.users.you")}
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-muted">{member.email}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <form action={updateUserRoleAction.bind(null, member.id)}>
                      <RoleSelect
                        defaultValue={member.role}
                        disabled={isLastAdmin}
                      />
                    </form>
                    <form action={removeUserAction.bind(null, member.id)}>
                      <Button
                        type="submit"
                        variant="ghost"
                        className="text-danger"
                        disabled={isSelf || isLastAdmin}
                      >
                        {t("settings.users.remove")}
                      </Button>
                    </form>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-sm text-muted">{t("settings.users.empty")}</p>
        )}
      </Card>

      <Card>
        <h2 className="mb-4 text-sm font-medium text-foreground">
          {t("settings.users.inviteTitle")}
        </h2>
        <InviteUserForm />
      </Card>
    </div>
  );
}
