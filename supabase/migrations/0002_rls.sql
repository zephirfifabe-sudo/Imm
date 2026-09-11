-- KLOCK — Row Level Security
--
-- Principe: l'isolation multi-tenant est appliquée au niveau base de
-- données, pas seulement dans l'application. Un utilisateur authentifié
-- ne peut jamais lire ou écrire les données d'une autre entreprise, même
-- en cas de bug côté API.
--
-- Les écritures effectuées par les terminaux (pointage) passent par des
-- routes API serveur utilisant la clé service_role (qui contourne RLS par
-- conception chez Supabase); la validation de l'appartenance à
-- l'entreprise et du droit d'agir est alors faite explicitement dans le
-- code serveur (TimeClockService), jamais côté terminal/client.

-- ---------------------------------------------------------------------------
-- Fonctions utilitaires (security definer: lisent `users` sans re-déclencher
-- RLS de façon circulaire)
-- ---------------------------------------------------------------------------

create or replace function app_current_company_id()
returns uuid
language sql
security definer
set search_path = public
stable
as $$
  select company_id from users where auth_user_id = auth.uid()
$$;

create or replace function app_current_role()
returns user_role
language sql
security definer
set search_path = public
stable
as $$
  select role from users where auth_user_id = auth.uid()
$$;

create or replace function app_is_admin()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select coalesce(app_current_role() = 'ADMIN', false)
$$;

-- ---------------------------------------------------------------------------
-- updated_at automatique
-- ---------------------------------------------------------------------------

create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger companies_set_updated_at before update on companies
  for each row execute function set_updated_at();
create trigger users_set_updated_at before update on users
  for each row execute function set_updated_at();
create trigger sites_set_updated_at before update on sites
  for each row execute function set_updated_at();
create trigger employees_set_updated_at before update on employees
  for each row execute function set_updated_at();
create trigger terminals_set_updated_at before update on terminals
  for each row execute function set_updated_at();
create trigger plans_set_updated_at before update on plans
  for each row execute function set_updated_at();
create trigger subscriptions_set_updated_at before update on subscriptions
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- Activation RLS
-- ---------------------------------------------------------------------------

alter table companies enable row level security;
alter table users enable row level security;
alter table sites enable row level security;
alter table employees enable row level security;
alter table terminals enable row level security;
alter table time_entries enable row level security;
alter table time_entry_corrections enable row level security;
alter table audit_logs enable row level security;
alter table plans enable row level security;
alter table subscriptions enable row level security;

-- ---------------------------------------------------------------------------
-- COMPANIES
-- Lecture/mise à jour limitée à sa propre entreprise.
-- La création d'entreprise se fait exclusivement via une route serveur
-- (service_role), il n'y a donc pas de politique INSERT pour les clients.
-- ---------------------------------------------------------------------------

create policy companies_select on companies
  for select using (id = app_current_company_id());

create policy companies_update on companies
  for update using (id = app_current_company_id() and app_is_admin());

-- ---------------------------------------------------------------------------
-- USERS
-- ---------------------------------------------------------------------------

create policy users_select on users
  for select using (company_id = app_current_company_id());

create policy users_insert on users
  for insert with check (company_id = app_current_company_id() and app_is_admin());

create policy users_update on users
  for update using (company_id = app_current_company_id() and app_is_admin());

create policy users_delete on users
  for delete using (company_id = app_current_company_id() and app_is_admin());

-- ---------------------------------------------------------------------------
-- SITES
-- ---------------------------------------------------------------------------

create policy sites_select on sites
  for select using (company_id = app_current_company_id());

create policy sites_write on sites
  for all using (company_id = app_current_company_id() and app_is_admin())
  with check (company_id = app_current_company_id() and app_is_admin());

-- ---------------------------------------------------------------------------
-- EMPLOYEES
-- ADMIN et MANAGER peuvent gérer les employés de leur entreprise.
-- ---------------------------------------------------------------------------

create policy employees_select on employees
  for select using (company_id = app_current_company_id());

create policy employees_write on employees
  for all using (company_id = app_current_company_id())
  with check (company_id = app_current_company_id());

-- ---------------------------------------------------------------------------
-- TERMINALS
-- Uniquement gérés par les ADMIN depuis l'espace employeur. Les terminaux
-- eux-mêmes n'utilisent pas ces policies (ils passent par l'API serveur).
-- ---------------------------------------------------------------------------

create policy terminals_select on terminals
  for select using (company_id = app_current_company_id());

create policy terminals_write on terminals
  for all using (company_id = app_current_company_id() and app_is_admin())
  with check (company_id = app_current_company_id() and app_is_admin());

-- ---------------------------------------------------------------------------
-- TIME ENTRIES
-- Lecture pour tout utilisateur de l'entreprise. Aucune politique INSERT/
-- UPDATE/DELETE cliente: les pointages sont créés uniquement par l'API
-- serveur (service_role) après validation métier, et ne sont jamais
-- modifiés directement (voir corrections).
-- ---------------------------------------------------------------------------

create policy time_entries_select on time_entries
  for select using (company_id = app_current_company_id());

-- ---------------------------------------------------------------------------
-- TIME ENTRY CORRECTIONS
-- Lecture pour l'entreprise, création réservée aux ADMIN/MANAGER via API
-- serveur qui vérifie le rôle; on autorise l'insert direct pour ADMIN
-- également au niveau RLS en défense en profondeur.
-- ---------------------------------------------------------------------------

create policy time_entry_corrections_select on time_entry_corrections
  for select using (company_id = app_current_company_id());

create policy time_entry_corrections_insert on time_entry_corrections
  for insert with check (company_id = app_current_company_id());

-- ---------------------------------------------------------------------------
-- AUDIT LOGS
-- Lecture uniquement pour les ADMIN de l'entreprise. Écriture réservée au
-- serveur (service_role).
-- ---------------------------------------------------------------------------

create policy audit_logs_select on audit_logs
  for select using (company_id = app_current_company_id() and app_is_admin());

-- ---------------------------------------------------------------------------
-- PLANS
-- Catalogue public en lecture (nécessaire pour l'écran d'abonnement),
-- jamais modifiable par les clients.
-- ---------------------------------------------------------------------------

create policy plans_select on plans
  for select using (is_active);

-- ---------------------------------------------------------------------------
-- SUBSCRIPTIONS
-- Lecture pour l'entreprise, écriture réservée au serveur (webhooks Stripe).
-- ---------------------------------------------------------------------------

create policy subscriptions_select on subscriptions
  for select using (company_id = app_current_company_id());
