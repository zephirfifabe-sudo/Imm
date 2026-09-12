-- KLOCK — Planificateur d'horaires
--
-- Trois tables, volontairement séparées de `employees`: ces données ne
-- servent qu'à la planification (aucun rapport avec l'identification au
-- terminal ou le pointage), donc une entreprise qui n'active jamais le
-- planificateur garde une table `employees` inchangée.
--
-- Générique dès le départ: aucune règle ni aucun champ ici ne référence une
-- commission paritaire ou un secteur précis. Les seuils par défaut posés
-- côté application (repos, jours consécutifs...) sont des recommandations
-- générales de droit du travail belge, jamais une certification légale.
--
-- Réservé aux ADMIN pour l'écriture (comme sites/terminals/users) — pas de
-- notion de MANAGER scopé par site pour l'instant.

create table employee_scheduling_profiles (
  id uuid primary key default gen_random_uuid(),
  employee_id uuid not null unique references employees (id) on delete cascade,
  company_id uuid not null references companies (id) on delete cascade,
  contract_hours_per_week numeric(5,2) not null default 38,
  contract_type text not null default 'CDI',
  day_only boolean not null default false,
  night_only boolean not null default false,
  min_nights_per_period integer not null default 0,
  max_nights_per_period integer not null default 8,
  color text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint employee_scheduling_profiles_not_both_only
    check (not (day_only and night_only)),
  constraint employee_scheduling_profiles_nights_range
    check (min_nights_per_period >= 0 and min_nights_per_period <= max_nights_per_period)
);

create index employee_scheduling_profiles_company_id_idx
  on employee_scheduling_profiles (company_id);

-- ---------------------------------------------------------------------------
-- SCHEDULE PERIODS
-- Un "horaire" est un cycle de 28 jours (4 semaines). `settings` regroupe les
-- réglages du générateur (effectifs min/max par créneau, règles d'enchaînement
-- des nuits, quotas week-end...) en JSON plutôt qu'en colonnes: ce sont des
-- paramètres d'algorithme consultés/modifiés ensemble, jamais filtrés
-- individuellement en base.
-- ---------------------------------------------------------------------------

create table schedule_periods (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies (id) on delete cascade,
  name text not null,
  period_start date not null,
  period_end date not null,
  settings jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint schedule_periods_dates check (period_end > period_start)
);

create index schedule_periods_company_id_idx on schedule_periods (company_id);

-- ---------------------------------------------------------------------------
-- SCHEDULE SHIFTS
-- Une ligne par case non vide (jour de repos = aucune ligne, pas une ligne
-- avec un code vide). day_index va de 0 à 27 depuis period_start.
-- ---------------------------------------------------------------------------

create table schedule_shifts (
  id uuid primary key default gen_random_uuid(),
  schedule_period_id uuid not null references schedule_periods (id) on delete cascade,
  employee_id uuid not null references employees (id) on delete cascade,
  company_id uuid not null references companies (id) on delete cascade,
  day_index integer not null check (day_index >= 0 and day_index <= 27),
  code text not null,
  locked boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (schedule_period_id, employee_id, day_index)
);

create index schedule_shifts_period_id_idx on schedule_shifts (schedule_period_id);
create index schedule_shifts_company_id_idx on schedule_shifts (company_id);

-- ---------------------------------------------------------------------------
-- updated_at automatique (réutilise set_updated_at définie en 0002_rls.sql)
-- ---------------------------------------------------------------------------

create trigger employee_scheduling_profiles_set_updated_at
  before update on employee_scheduling_profiles
  for each row execute function set_updated_at();
create trigger schedule_periods_set_updated_at
  before update on schedule_periods
  for each row execute function set_updated_at();
create trigger schedule_shifts_set_updated_at
  before update on schedule_shifts
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------

alter table employee_scheduling_profiles enable row level security;
alter table schedule_periods enable row level security;
alter table schedule_shifts enable row level security;

create policy employee_scheduling_profiles_select on employee_scheduling_profiles
  for select using (company_id = app_current_company_id());

create policy employee_scheduling_profiles_write on employee_scheduling_profiles
  for all using (company_id = app_current_company_id() and app_is_admin())
  with check (company_id = app_current_company_id() and app_is_admin());

create policy schedule_periods_select on schedule_periods
  for select using (company_id = app_current_company_id());

create policy schedule_periods_write on schedule_periods
  for all using (company_id = app_current_company_id() and app_is_admin())
  with check (company_id = app_current_company_id() and app_is_admin());

create policy schedule_shifts_select on schedule_shifts
  for select using (company_id = app_current_company_id());

create policy schedule_shifts_write on schedule_shifts
  for all using (company_id = app_current_company_id() and app_is_admin())
  with check (company_id = app_current_company_id() and app_is_admin());
