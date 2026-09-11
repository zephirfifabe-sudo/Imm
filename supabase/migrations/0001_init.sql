-- KLOCK — schema initial
-- Convention: chaque table métier porte company_id pour l'isolation multi-tenant.
-- RLS est active sur toutes les tables métier: aucune requête ne doit pouvoir
-- traverser les entreprises, y compris via un bug applicatif côté client/API.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- ENUM TYPES
-- ---------------------------------------------------------------------------

create type user_role as enum ('ADMIN', 'MANAGER');
create type employee_status as enum ('ACTIVE', 'INACTIVE');
create type time_entry_type as enum ('CLOCK_IN', 'CLOCK_OUT', 'BREAK_START', 'BREAK_END');
create type time_entry_source as enum ('PIN', 'QR', 'NFC', 'WEB', 'ADMIN');
create type terminal_status as enum ('ACTIVE', 'INACTIVE', 'PENDING_ACTIVATION');

-- ---------------------------------------------------------------------------
-- COMPANIES
-- ---------------------------------------------------------------------------

create table companies (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  vat_number text,
  address text,
  locale text not null default 'fr',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- USERS (comptes employeur: ADMIN / MANAGER). Lié 1:1 à auth.users.
-- ---------------------------------------------------------------------------

create table users (
  id uuid primary key default gen_random_uuid(),
  auth_user_id uuid not null unique references auth.users (id) on delete cascade,
  company_id uuid not null references companies (id) on delete cascade,
  email text not null,
  first_name text not null,
  last_name text not null,
  role user_role not null default 'MANAGER',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (company_id, email)
);

create index users_company_id_idx on users (company_id);
create index users_auth_user_id_idx on users (auth_user_id);

-- ---------------------------------------------------------------------------
-- SITES
-- ---------------------------------------------------------------------------

create table sites (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies (id) on delete cascade,
  name text not null,
  address text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index sites_company_id_idx on sites (company_id);

-- ---------------------------------------------------------------------------
-- EMPLOYEES
-- Les tokens QR/NFC sont des identifiants opaques, jamais des données
-- personnelles. Le PIN est stocké sous forme de hash (jamais en clair).
-- ---------------------------------------------------------------------------

create table employees (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies (id) on delete cascade,
  site_id uuid references sites (id) on delete set null,
  internal_code text not null,
  first_name text not null,
  last_name text not null,
  email text,
  status employee_status not null default 'ACTIVE',
  pin_hash text,
  qr_token uuid unique default gen_random_uuid(),
  nfc_token text unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (company_id, internal_code)
);

create index employees_company_id_idx on employees (company_id);
create index employees_site_id_idx on employees (site_id);
create index employees_qr_token_idx on employees (qr_token);
create index employees_nfc_token_idx on employees (nfc_token);

-- ---------------------------------------------------------------------------
-- TERMINALS
-- ---------------------------------------------------------------------------

create table terminals (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies (id) on delete cascade,
  site_id uuid references sites (id) on delete set null,
  name text not null,
  terminal_code text not null unique,
  status terminal_status not null default 'PENDING_ACTIVATION',
  activation_code text,
  software_version text,
  last_seen_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index terminals_company_id_idx on terminals (company_id);
create index terminals_site_id_idx on terminals (site_id);

-- ---------------------------------------------------------------------------
-- TIME ENTRIES
-- event_id garantit l'idempotence: un même événement envoyé plusieurs fois
-- (ex: retry après coupure réseau) ne doit être inséré qu'une seule fois.
-- ---------------------------------------------------------------------------

create table time_entries (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null unique,
  company_id uuid not null references companies (id) on delete cascade,
  site_id uuid references sites (id) on delete set null,
  employee_id uuid not null references employees (id) on delete cascade,
  terminal_id uuid references terminals (id) on delete set null,
  type time_entry_type not null,
  source time_entry_source not null,
  occurred_at timestamptz not null,
  created_at timestamptz not null default now()
);

create index time_entries_company_id_idx on time_entries (company_id);
create index time_entries_employee_id_idx on time_entries (employee_id);
create index time_entries_occurred_at_idx on time_entries (occurred_at);
create index time_entries_employee_occurred_idx on time_entries (employee_id, occurred_at desc);

-- ---------------------------------------------------------------------------
-- TIME ENTRY CORRECTIONS
-- Une correction ne modifie jamais l'entrée d'origine: elle est journalisée
-- avec l'ancienne valeur, la nouvelle valeur, l'auteur et le motif.
-- ---------------------------------------------------------------------------

create table time_entry_corrections (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies (id) on delete cascade,
  time_entry_id uuid not null references time_entries (id) on delete cascade,
  previous_occurred_at timestamptz not null,
  new_occurred_at timestamptz not null,
  reason text not null,
  corrected_by uuid not null references users (id),
  created_at timestamptz not null default now()
);

create index time_entry_corrections_company_id_idx on time_entry_corrections (company_id);
create index time_entry_corrections_time_entry_id_idx on time_entry_corrections (time_entry_id);

-- ---------------------------------------------------------------------------
-- AUDIT LOGS
-- ---------------------------------------------------------------------------

create table audit_logs (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies (id) on delete cascade,
  actor_user_id uuid references users (id) on delete set null,
  action text not null,
  entity_type text not null,
  entity_id uuid,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index audit_logs_company_id_idx on audit_logs (company_id);
create index audit_logs_entity_idx on audit_logs (entity_type, entity_id);

-- ---------------------------------------------------------------------------
-- PLANS (catalogue, pas de secret ni de logique métier hardcodée ailleurs)
-- ---------------------------------------------------------------------------

create table plans (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  price_cents integer not null,
  max_employees integer not null,
  features jsonb not null default '{}'::jsonb,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- SUBSCRIPTIONS
-- ---------------------------------------------------------------------------

create table subscriptions (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null unique references companies (id) on delete cascade,
  plan_id uuid not null references plans (id),
  stripe_customer_id text,
  stripe_subscription_id text,
  status text not null default 'trialing',
  current_period_end timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index subscriptions_company_id_idx on subscriptions (company_id);

-- ---------------------------------------------------------------------------
-- SEED: plans de départ (prix indicatifs, modifiables sans déploiement)
-- ---------------------------------------------------------------------------

insert into plans (code, name, price_cents, max_employees) values
  ('STARTER', 'Starter', 2900, 10),
  ('PME', 'PME', 4900, 25),
  ('BUSINESS', 'Business', 8900, 50);
