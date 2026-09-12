import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { env } from "@/lib/config/env";

// /terminal a sa propre authentification (token de terminal, pas de session
// Supabase): il ne doit jamais être redirigé vers /login. /auth/callback et
// /set-password font partie du flux d'invitation (employeur ou employé) et
// doivent rester accessibles avant qu'une session applicative n'existe.
const PUBLIC_PATHS = [
  "/login",
  "/signup",
  "/terminal",
  "/employee/login",
  "/auth/callback",
  "/set-password",
];

export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(env.supabaseUrl, env.supabaseAnonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        for (const { name, value } of cookiesToSet) {
          request.cookies.set(name, value);
        }
        response = NextResponse.next({ request });
        for (const { name, value, options } of cookiesToSet) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });

  // Les routes API (ex: le webhook Stripe) gèrent leur propre authentification
  // (signature Stripe, token de terminal...) — jamais une session utilisateur,
  // et ne doivent donc jamais être redirigées vers /login.
  if (request.nextUrl.pathname.startsWith("/api")) {
    return response;
  }

  const { data } = await supabase.auth.getUser();
  const isPublicPath = PUBLIC_PATHS.some((path) =>
    request.nextUrl.pathname.startsWith(path),
  );

  if (!data.user && !isPublicPath && request.nextUrl.pathname !== "/") {
    const loginPath = request.nextUrl.pathname.startsWith("/employee")
      ? "/employee/login"
      : "/login";
    const loginUrl = new URL(loginPath, request.url);
    return NextResponse.redirect(loginUrl);
  }

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};
