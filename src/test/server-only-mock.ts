// Stub pour les tests Vitest: le vrai package `server-only` lève une erreur
// à l'import pour empêcher toute fuite de code serveur vers le client. Ce
// comportement n'a pas de sens hors du bundler Next.js — Vitest exécute ce
// module en Node pur — donc on le neutralise ici uniquement pour les tests.
export {};
