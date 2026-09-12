import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          // Empêche le clickjacking (une page tierce qui embarquerait KLOCK
          // dans une iframe invisible pour piéger un clic sur une action
          // réelle — correction de pointage, invitation, etc.).
          { key: "X-Frame-Options", value: "DENY" },
          // Empêche le navigateur de deviner un type MIME différent de
          // celui déclaré (protection contre certaines classes de XSS).
          { key: "X-Content-Type-Options", value: "nosniff" },
          // N'envoie l'URL complète comme referrer qu'en navigation
          // same-origin; jamais le chemin complet vers un site tiers.
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
