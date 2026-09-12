import { createSupabaseServerClient } from "@/lib/supabase/server";

/**
 * Point d'entrée unique pour les liens envoyés par Supabase Auth
 * (invitation employeur ou employé): échange le code contre une session,
 * puis renvoie vers l'écran de création de mot de passe. Sans cette route,
 * le lien reçu par e-mail n'établit aucune session côté application.
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");

  if (code) {
    const supabase = await createSupabaseServerClient();
    await supabase.auth.exchangeCodeForSession(code);
  }

  return Response.redirect(new URL("/set-password", request.url));
}
