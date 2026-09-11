/**
 * Types générés à la main en attendant la connexion à un vrai projet Supabase.
 * À régénérer avec `supabase gen types typescript --local` une fois le projet
 * lié, puis à remplacer par le fichier généré.
 */

export type UserRole = "ADMIN" | "MANAGER";
export type EmployeeStatus = "ACTIVE" | "INACTIVE";
export type TimeEntryType =
  | "CLOCK_IN"
  | "CLOCK_OUT"
  | "BREAK_START"
  | "BREAK_END";
export type TimeEntrySource = "PIN" | "QR" | "NFC" | "WEB" | "ADMIN";
export type TerminalStatus = "ACTIVE" | "INACTIVE" | "PENDING_ACTIVATION";

export type Company = {
  id: string;
  name: string;
  vat_number: string | null;
  address: string | null;
  locale: string;
  created_at: string;
  updated_at: string;
}

export type AppUser = {
  id: string;
  auth_user_id: string;
  company_id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: UserRole;
  created_at: string;
  updated_at: string;
}

export type Site = {
  id: string;
  company_id: string;
  name: string;
  address: string | null;
  created_at: string;
  updated_at: string;
}

export type Employee = {
  id: string;
  company_id: string;
  site_id: string | null;
  internal_code: string;
  first_name: string;
  last_name: string;
  email: string | null;
  job_title: string | null;
  status: EmployeeStatus;
  pin_hash: string | null;
  qr_token: string | null;
  nfc_token: string | null;
  created_at: string;
  updated_at: string;
}

export type Terminal = {
  id: string;
  company_id: string;
  site_id: string | null;
  name: string;
  terminal_code: string;
  status: TerminalStatus;
  activation_code: string | null;
  terminal_secret_hash: string | null;
  software_version: string | null;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
}

export type TimeEntry = {
  id: string;
  event_id: string;
  company_id: string;
  site_id: string | null;
  employee_id: string;
  terminal_id: string | null;
  type: TimeEntryType;
  source: TimeEntrySource;
  occurred_at: string;
  created_at: string;
}

export type TimeEntryCorrection = {
  id: string;
  company_id: string;
  time_entry_id: string;
  previous_occurred_at: string;
  new_occurred_at: string;
  reason: string;
  corrected_by: string;
  created_at: string;
}

export type AuditLog = {
  id: string;
  company_id: string;
  actor_user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export type Plan = {
  id: string;
  code: string;
  name: string;
  price_cents: number;
  max_employees: number;
  features: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type Subscription = {
  id: string;
  company_id: string;
  plan_id: string;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  status: string;
  current_period_end: string | null;
  created_at: string;
  updated_at: string;
}

type GeneratedColumns = "id" | "created_at" | "updated_at";

/** Insert/Update dérivés du Row: les colonnes générées par la base restent optionnelles. */
type TableDef<Row> = {
  Row: Row;
  Insert: Omit<Row, GeneratedColumns> &
    Partial<Pick<Row, Extract<keyof Row, GeneratedColumns>>>;
  Update: Partial<Row>;
  Relationships: [];
};

export type Database = {
  public: {
    Tables: {
      companies: TableDef<Company>;
      users: TableDef<AppUser>;
      sites: TableDef<Site>;
      employees: TableDef<Employee>;
      terminals: TableDef<Terminal>;
      time_entries: TableDef<TimeEntry>;
      time_entry_corrections: TableDef<TimeEntryCorrection>;
      audit_logs: TableDef<AuditLog>;
      plans: TableDef<Plan>;
      subscriptions: TableDef<Subscription>;
    };
    Views: Record<string, never>;
    Functions: {
      create_company_with_admin: {
        Args: {
          p_auth_user_id: string;
          p_email: string;
          p_company_name: string;
          p_first_name: string;
          p_last_name: string;
        };
        Returns: { company_id: string; user_id: string }[];
      };
    };
    Enums: Record<string, never>;
    CompositeTypes: Record<string, never>;
  };
}
