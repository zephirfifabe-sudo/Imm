-- KLOCK — Durcissement: retrait de l'insert direct sur time_entry_corrections
--
-- Cette policy INSERT date d'avant l'implémentation réelle des corrections
-- (Phase 6): `correct_time_entry` (security definer, service_role) met à
-- jour le pointage ET écrit la ligne de correction ET l'entrée d'audit
-- dans une seule transaction — l'application n'insère jamais directement
-- dans `time_entry_corrections`.
--
-- Or cette policy restait active et permettait à n'importe quel membre de
-- l'entreprise d'insérer directement une ligne de correction fabriquée
-- (previous/new_occurred_at, motif arbitraires) SANS que le pointage
-- correspondant soit réellement modifié et SANS entrée d'audit — ce qui
-- compromet l'intégrité même de la table censée servir de trace d'audit
-- fiable. Les corrections ne doivent plus pouvoir être écrites que via
-- `correct_time_entry` (service_role, RLS ignorée par sécurité définisseur).

drop policy if exists time_entry_corrections_insert on time_entry_corrections;
