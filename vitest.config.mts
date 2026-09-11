import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
      "server-only": path.resolve(
        import.meta.dirname,
        "./src/test/server-only-mock.ts",
      ),
    },
  },
  test: {
    environment: "node",
    // env.ts lit ces variables au chargement du module: sans valeur ici,
    // tout test qui importe (même transitivement) un module serveur
    // échouerait avant même de démarrer.
    env: {
      NEXT_PUBLIC_SUPABASE_URL: "https://placeholder.supabase.co",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "placeholder-anon-key",
    },
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
