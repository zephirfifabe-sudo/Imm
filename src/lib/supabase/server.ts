import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import type { Database } from "@/types/database";
import { env } from "@/lib/config/env";

/**
 * Client Supabase pour Server Components / Route Handlers / Server Actions.
 * Porte la session de l'utilisateur connecté: soumis à RLS, jamais la clé
 * service_role.
 */
export async function createSupabaseServerClient() {
  const cookieStore = await cookies();

  return createServerClient<Database>(env.supabaseUrl, env.supabaseAnonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch {
          // Appelé depuis un Server Component: la session sera rafraîchie
          // par le middleware, cette écriture peut être ignorée sans risque.
        }
      },
    },
  });
}
