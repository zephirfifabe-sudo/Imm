-- KLOCK — Index de performance
--
-- `time_entries` filtré par company_id + plage de occurred_at est le motif
-- de requête le plus fréquent de l'application (dashboard, historique,
-- exports). Les index existants sur company_id et occurred_at séparément
-- fonctionnent mais un index composite sert directement ce filtre combiné
-- sans repasser par une intersection de bitmap.

create index time_entries_company_occurred_idx
  on time_entries (company_id, occurred_at desc);
