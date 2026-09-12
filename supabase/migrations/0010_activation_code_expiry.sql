-- KLOCK — Expiration des codes d'activation de terminal
--
-- Le code d'activation (6 chiffres, 1 000 000 de combinaisons) n'avait
-- jusqu'ici aucune date d'expiration: un terminal en attente restait
-- indéfiniment activable par quiconque devinerait son code, sans limite de
-- débit possible côté application (infrastructure de rate limiting hors
-- scope de ce durcissement). Une expiration courte réduit drastiquement la
-- fenêtre d'attaque exploitable, en plus de rester une bonne pratique
-- produit (un code "à usage unique" qui traîne indéfiniment n'en est pas
-- vraiment un).

alter table terminals add column activation_code_expires_at timestamptz;
