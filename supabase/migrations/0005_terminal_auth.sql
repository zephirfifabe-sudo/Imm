-- KLOCK — Authentification des terminaux
--
-- Un terminal n'est pas un utilisateur Supabase Auth: il s'active une fois
-- avec un code court donné par l'employeur, puis conserve un token opaque
-- (id.secret) qu'il présente à chaque appel. Seul le hash du secret est
-- stocké (bcrypt), jamais le secret en clair.
--
-- L'activation_code doit être unique le temps où il est actif (avant
-- consommation), mais peut être réutilisé (NULL) une fois le terminal
-- activé — d'où l'index unique partiel plutôt qu'une contrainte unique
-- classique.

alter table terminals add column terminal_secret_hash text;

create unique index terminals_activation_code_idx
  on terminals (activation_code)
  where activation_code is not null;
