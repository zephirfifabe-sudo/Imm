-- KLOCK — Employés: champ métier + intégrité des pointages
--
-- `job_title` est une information descriptive libre (ex: "Vendeur",
-- "Mécanicien"), distincte du rôle d'accès applicatif (ADMIN/MANAGER) déjà
-- porté par `users.role`. Les employés n'ont pas de compte applicatif: ils
-- ne s'authentifient qu'au terminal (PIN/QR/NFC).

alter table employees add column job_title text;

-- Un employé n'est jamais supprimé (uniquement désactivé) précisément pour
-- éviter ce cas: la contrainte `on delete cascade` d'origine effacerait
-- silencieusement tout l'historique de pointage si une ligne `employees`
-- était malgré tout supprimée (suppression manuelle en base, script, bug).
-- On la remplace par `on delete restrict`: Postgres refuse la suppression
-- d'un employé qui a des pointages, ce qui force à désactiver plutôt que
-- détruire l'historique.
alter table time_entries drop constraint time_entries_employee_id_fkey;
alter table time_entries
  add constraint time_entries_employee_id_fkey
  foreign key (employee_id) references employees (id) on delete restrict;
