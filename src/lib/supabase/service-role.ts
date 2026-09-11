import "server-only";
import { createClient } from "@supabase/supabase-js";
import type { Database } from "@/types/database";
import { env } from "@/lib/config/env";
import { serverEnv } from "@/lib/config/env";

/**
 * Client Supabase avec la clé service_role: contourne RLS.
 *
 * À utiliser UNIQUEMENT dans du code serveur de confiance (routes API,
 * TimeClockService) qui applique lui-même les contrôles d'appartenance à
 * l'entreprise et de permission. Ne jamais importer ce module depuis un
 * composant client — `server-only` fait échouer le build si c'est le cas.
 */
export function createSupabaseServiceRoleClient() {
  return createClient<Database>(
    env.supabaseUrl,
    serverEnv.supabaseServiceRoleKey(),
    { auth: { persistSession: false } },
  );
}
