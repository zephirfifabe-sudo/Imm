-- KLOCK — Compte personnel employé (app mobile/web)
--
-- Un employé peut désormais, en plus de son identification anonyme au
-- terminal (PIN/QR/NFC, inchangée), avoir un compte personnel (email +
-- mot de passe) pour consulter son horaire depuis son téléphone. C'est
-- strictement optionnel: `auth_user_id` reste nul pour la grande majorité
-- des employés, qui continuent à ne jamais avoir de compte.
--
-- Ce compte est entièrement séparé des comptes employeur (`users`):
-- `app_current_company_id()`/`app_is_admin()` lisent `users`, donc une
-- session employé ne matche jamais les policies existantes (qui exigent
-- une ligne `users`) — nouvelles policies additives ci-dessous, scopées
-- strictement à "ses propres données".

alter table employees
  add column auth_user_id uuid unique references auth.users (id) on delete set null;

create or replace function app_current_employee_id()
returns uuid
language sql
security definer
set search_path = public
stable
as $$
  select id from employees where auth_user_id = auth.uid()
$$;

create or replace function app_current_employee_company_id()
returns uuid
language sql
security definer
set search_path = public
stable
as $$
  select company_id from employees where auth_user_id = auth.uid()
$$;

-- ---------------------------------------------------------------------------
-- Lecture seule pour l'employé sur ses propres données. Aucune policy
-- d'écriture: un employé ne peut rien modifier depuis son compte personnel.
-- ---------------------------------------------------------------------------

create policy employees_select_own on employees
  for select using (auth_user_id = auth.uid());

create policy schedule_periods_select_own_employee on schedule_periods
  for select using (company_id = app_current_employee_company_id());

create policy schedule_shifts_select_own_employee on schedule_shifts
  for select using (employee_id = app_current_employee_id());
