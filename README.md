# KLOCK

**Le temps de travail, simplement.**

KLOCK est conçu pour répondre aux besoins des entreprises belges en matière de suivi fiable du temps de travail. Ce dépôt contient l'application web (espace employeur) et, à terme, le terminal de pointage (PWA).

> KLOCK n'est pas un avis juridique et ne prétend pas être "conforme" à une réglementation dont les modalités définitives ne sont pas encore connues.

## Stack technique

- **Frontend** : Next.js (App Router), TypeScript strict, Tailwind CSS
- **Backend** : Supabase (PostgreSQL, Auth, Row Level Security)
- **Paiement** : Stripe (Checkout + Billing Portal hébergés)
- **Déploiement** : Vercel + Supabase
- **Tests** : Vitest

## Installation locale

```bash
npm install
cp .env.example .env.local
# renseigner NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY,
# SUPABASE_SERVICE_ROLE_KEY dans .env.local (jamais commité)
npm run dev
```

## Variables d'environnement

Voir `.env.example`. `SUPABASE_SERVICE_ROLE_KEY` ne doit jamais être exposée au
frontend (pas de préfixe `NEXT_PUBLIC_`) ni commitée.

## Base de données

Le schéma se trouve dans `supabase/migrations/`:

- `0001_init.sql` — tables métier (companies, users, sites, employees,
  terminals, time_entries, time_entry_corrections, audit_logs, plans,
  subscriptions)
- `0002_rls.sql` — Row Level Security: l'isolation multi-tenant est appliquée
  au niveau base de données, pas uniquement dans l'application

Pour appliquer les migrations sur un projet Supabase (CLI Supabase requise):

```bash
supabase link --project-ref <votre-projet>
supabase db push
```

## Configuration Stripe

1. Créer un produit + un prix récurrent mensuel dans le Dashboard Stripe
   pour chaque plan (STARTER, PME, BUSINESS)
2. Renseigner `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_PME`,
   `STRIPE_PRICE_BUSINESS` (les Price ID, pas les Product ID) dans
   `.env.local`
3. Renseigner `STRIPE_SECRET_KEY` (Dashboard > Développeurs > Clés API)
4. Créer un endpoint webhook pointant vers `<votre-domaine>/api/stripe/webhook`,
   écoutant au minimum `checkout.session.completed`,
   `customer.subscription.updated`, `customer.subscription.deleted`, puis
   renseigner `STRIPE_WEBHOOK_SECRET` avec le secret de signature affiché

En local, utiliser `stripe listen --forward-to localhost:3000/api/stripe/webhook`
(CLI Stripe) pour recevoir les événements.

## Architecture

- `src/app` — routes Next.js (App Router), groupées par contexte:
  `(auth)` pour la connexion, `(dashboard)` pour l'espace employeur
- `src/components/ui` — design system minimal (Button, Card, Input, Label,
  Badge)
- `src/lib/supabase` — clients Supabase:
  - `client.ts` : navigateur (soumis à RLS)
  - `server.ts` : Server Components / Server Actions (soumis à RLS)
  - `service-role.ts` : opérations serveur de confiance uniquement
    (contourne RLS — jamais importé côté client)
- `src/lib/config` — configuration centralisée (plans/prix, variables
  d'environnement). Aucun prix n'est codé en dur dans l'UI.
- `src/types/database.ts` — types générés à la main en attendant la
  connexion à un vrai projet Supabase (à remplacer par
  `supabase gen types typescript`)
- `src/i18n` — système de traduction minimal. Le français est la seule
  langue livrée pour le MVP; le néerlandais et l'anglais sont préparés.
- `src/proxy.ts` — Proxy Next.js (anciennement "middleware"): rafraîchit la
  session Supabase et protège les routes non publiques.

## Sécurité

- RLS activée sur toutes les tables métier; chaque requête est filtrée par
  `company_id` dérivé de la session (jamais transmis en clair par le client)
- La clé `service_role` n'est utilisée que côté serveur, pour les opérations
  qui doivent volontairement contourner RLS (ex: écriture de pointage depuis
  un terminal, après validation métier explicite)
- Aucun secret dans le code ou le frontend

## Tests

```bash
npm run test        # tests unitaires (Vitest)
npm run typecheck    # TypeScript strict
npm run lint          # ESLint
```

## Statut du projet

- **Phase 1 (Foundation)** ✅ — projet initialisé, schéma DB + RLS,
  authentification Supabase, design system minimal, layout de base.
- **Phase 2 (Entreprise)** ✅ — onboarding self-serve (création entreprise +
  premier ADMIN), profil entreprise, gestion des sites, gestion des
  utilisateurs (invitation, rôles, retrait d'accès) avec la règle "toujours
  au moins un ADMIN" appliquée côté serveur.
- **Phase 3 (Employés)** ✅ — CRUD employés (matricule auto-suggéré, site,
  rôle/fonction), PIN à 4 chiffres hashé (bcrypt) et vérifié unique par
  entreprise, token QR régénérable, activation/désactivation. La
  suppression d'un employé n'est jamais exposée dans l'UI — seule la
  désactivation, et l'intégrité est renforcée en base (`ON DELETE
  RESTRICT` sur `time_entries.employee_id`) pour empêcher toute perte
  silencieuse de l'historique de pointage.
- **Phase 4 (Time Clock)** ✅ — terminal de pointage (`/terminal`), activation
  par code à usage unique, identification PIN (clavier numérique) ou QR
  (saisie compatible douchette USB — pas encore de scan caméra),
  arrivée/départ/pauses avec validation serveur de chaque transition
  (`TimeClockService`), idempotence par `event_id`, administration des
  terminaux (`/settings/terminals`), historique du jour sur le tableau de
  bord.
- **Phase 5 (Dashboard)** ✅ — tableau de bord de présence (présents/en
  pause/absents, bannière d'anomalies, liste de présence, derniers
  pointages) recalculé à chaque chargement de page (pas de push temps
  réel pour l'instant). Page `/history` avec filtres employé/période,
  reconstruction du temps travaillé et des pauses par jour
  (`summarizeDay`), détection d'anomalies (départ sans arrivée, pause non
  refermée, journée non clôturée, etc.).
- **Phase 6 (Corrections + Audit)** ✅ — correction d'un pointage
  (`/corrections/[id]`) avec motif obligatoire; l'opération
  (`correct_time_entry`) met à jour le pointage, journalise la correction
  (valeur précédente, nouvelle valeur, auteur, motif) et écrit une entrée
  d'audit dans une seule transaction — jamais d'écrasement silencieux.
  `/history` signale les pointages corrigés. `/settings/audit-log`
  (ADMIN) liste les entrées d'audit.
- **Phase 7 (Hors-ligne)** ✅ — périmètre assumé: la résilience hors-ligne
  couvre l'enregistrement du pointage, pas l'identification (PIN/QR
  nécessite toujours le serveur, aucune donnée d'identification n'est mise
  en cache sur le terminal). Une fois l'employé identifié, une coupure
  réseau au moment de pointer met l'événement en file (localStorage, avec
  son heure réelle de capture, pas l'heure de synchronisation) et le
  resynchronise automatiquement (retour réseau, montage, relance toutes
  les 20s), un par un et dans l'ordre pour préserver la validité des
  transitions. Un événement devenu invalide au moment du rejeu (conflit) est
  abandonné plutôt que retenté indéfiniment.
- **Phase 8 (NFC)** ✅ — abstraction `IdentificationProvider` (PIN/QR/NFC
  implémentent tous la même interface `isValidInput` + `identify`,
  résolue via `getIdentificationProvider()`); le terminal ne contient plus
  aucune logique spécifique à un moyen d'identification. NFC ajouté au
  terminal: scan Web NFC natif quand disponible (Chrome sur Android),
  sinon lecteur USB en mode clavier ou saisie manuelle — aucun
  verrouillage à un fabricant.
- **Phase 9 (Abonnement)** ✅ — Stripe Checkout (page hébergée) pour
  souscrire, Billing Portal (hébergé) pour gérer paiement/factures/
  résiliation — pas de formulaire carte ni de UI de facturation maison.
  Le webhook (`/api/stripe/webhook`) est la seule source de vérité pour
  l'état réel de l'abonnement après le paiement (statut, plan, date de
  fin de période). Nouvelle entreprise = abonnement d'essai STARTER par
  défaut, pour que la limite d'employés soit réelle dès le premier jour.
  Limite appliquée à la création **et** à la réactivation d'un employé
  (sinon contournable en désactivant/réactivant). Correctif au passage:
  le proxy redirigeait `/api/**` vers `/login` faute de session — cela
  aurait cassé le webhook Stripe en production.
- **Phase 10 (Exports)** ✅ — export CSV (séparateur `;`, BOM UTF-8 — pensé
  pour Excel en locale belge/française) et Excel (.xlsx réel via
  `exceljs`) de l'historique des pointages depuis `/history`, filtrable
  par employé/site/période. Une ligne par employé et par jour: temps
  travaillé en H:MIN et en décimal (utilisable directement pour un calcul
  de paie), pauses, anomalies. PDF volontairement laissé de côté pour
  l'instant (CSV/Excel couvrent le besoin immédiat).
- **Phase 11 (Hardening)** ✅ — audit systématique sur les 10 dimensions du
  cahier des charges. Résultat détaillé ci-dessous: § [Audit de
  durcissement (Phase 11)](#audit-de-durcissement-phase-11).
- **Phase 12 (Planificateur d'horaires)** ✅ — nouveau module `/scheduling`
  (réservé aux ADMIN), généré à partir d'un outil existant repris et
  adapté: générateur automatique de planning sur un cycle de 28 jours
  (nuits enchaînées par blocs, repos minimum, jours de travail consécutifs,
  quota de week-ends), édition manuelle case par case, contrôle de
  conformité, export CSV. Volontairement générique dès le départ: **aucune
  référence à une commission paritaire ou à un secteur précis** — les
  seuils par défaut (repos 11h, max 6 jours/semaine...) sont présentés
  comme des recommandations générales de droit du travail belge à ajuster,
  jamais comme une certification légale. Deux nouvelles tables séparées de
  `employees` (`employee_scheduling_profiles`, `schedule_periods`,
  `schedule_shifts`) — un employé sans heures contractuelles renseignées
  reste simplement hors du planificateur. Champs de planification
  (heures/semaine, type de contrat, jour/nuit uniquement, quota de nuits)
  ajoutés directement au formulaire employé existant plutôt que dans un
  écran séparé. **Non repris dans cette v1** (laissé pour une itération
  suivante): horaire de base récurrent, congés/indisponibilités
  jour-par-jour, règles personnalisées (incompatibilités entre employés),
  rapprochement avec les vrais pointages, scoring/alertes intelligentes,
  glisser-déposer — l'outil d'origine les avait tous, mais le v1 se
  concentre sur le moteur de génération + l'édition + la conformité.

- **Phase 13 (Compte personnel employé)** ✅ — un employé peut désormais,
  en plus de son identification anonyme au terminal (PIN/QR/NFC,
  inchangée), avoir un compte personnel (e-mail + mot de passe) pour
  consulter **en lecture seule** son horaire depuis son téléphone
  (`/employee/schedule`, avec un login dédié `/employee/login` — totalement
  séparé de `/login`, réservé aux comptes employeur). Strictement
  optionnel: sans invitation explicite depuis sa fiche (`/employees/[id]/edit`
  → "Accès application"), l'employé n'a aucun compte. Nouvelle colonne
  `employees.auth_user_id` (nullable, unique) + deux nouvelles fonctions
  `security definer` et policies RLS additives strictement scopées à "ses
  propres données" (`employees_select_own`,
  `schedule_periods_select_own_employee`,
  `schedule_shifts_select_own_employee`) — aucune policy d'écriture pour ce
  type de session, un employé ne peut rien modifier depuis son compte.
  Au passage, complété le flux d'invitation employeur (`/settings/users`),
  qui envoyait déjà l'e-mail Supabase mais n'avait jamais eu de page pour
  que l'invité y définisse son mot de passe: nouvelle route
  `/auth/callback` (échange le code contre une session) + `/set-password`
  (pose le mot de passe puis redirige vers `/dashboard` ou
  `/employee/schedule` selon le type de compte), utilisée par les deux
  flux d'invitation. **Prérequis pour que les e-mails d'invitation
  fonctionnent réellement**: `{NEXT_PUBLIC_APP_URL}/auth/callback` doit
  être ajouté aux "Redirect URLs" autorisées dans Supabase (Authentication
  → URL Configuration), sinon Supabase refuse ou ignore le `redirectTo`.
  **Non fait dans cette v1**: messagerie d'équipe (délibérément traitée
  comme un chantier séparé, après l'authentification), écran de gestion
  centralisé des accès employé (aujourd'hui: un par un, depuis chaque
  fiche), et aucune app mobile native — c'est une page web responsive.

Toutes les phases du plan de développement initial sont maintenant
couvertes, plus ces deux nouveaux modules (planification, compte employé).
Les prochaines étapes dépendent des retours d'usage réel (voir l'audit
ci-dessous pour ce qui reste ouvert côté phases 1-11).

## Audit de durcissement (Phase 11)

Audit mené sur le code existant (aucun projet Supabase/Stripe réel n'étant
connecté à cet environnement, rien n'a pu être vérifié en conditions
réelles — seulement au niveau code, schéma et typage). Les problèmes réels
trouvés ont été corrigés; ce qui nécessite une décision produit/juridique
ou une infrastructure non encore en place est listé comme tel, sans
prétendre que c'est réglé.

### Corrigé pendant cet audit

- **RLS** : la policy `time_entry_corrections_insert` permettait à
  n'importe quel membre de l'entreprise d'insérer directement une ligne de
  correction fabriquée, sans passer par `correct_time_entry` — donc sans
  mise à jour réelle du pointage ni entrée d'audit. Supprimée
  (`0008_harden_corrections_insert.sql`); les corrections ne passent plus
  que par la fonction atomique.
- **Terminal — code d'activation** : 6 chiffres (1M de combinaisons), sans
  expiration, sans limitation de débit possible côté application, et
  l'index d'unicité est **global** (pas par entreprise) — un attaquant
  distant aurait pu, à terme, détourner l'activation d'un terminal de
  n'importe quelle entreprise cliente. Les codes expirent maintenant après
  24h (`0010_activation_code_expiry.sql`). Une vraie limitation de débit
  nécessite une infrastructure dédiée (Upstash/Redis) — non ajoutée ici
  pour éviter un faux correctif (un compteur en mémoire serait silencieusement
  inefficace sur un déploiement serverless multi-instance).
- **Défense en profondeur** : `getLastEntryType` ne filtrait que par
  `employee_id` côté service_role (RLS ignorée) — aucune fuite exploitable
  aujourd'hui (les deux appelants vérifient déjà l'entreprise avant), mais
  un futur appelant qui oublierait cette vérification aurait pu lire le
  dernier pointage d'une autre entreprise. `company_id` est maintenant un
  paramètre obligatoire.
- **Observabilité** : plusieurs chemins critiques avalaient une erreur
  Postgres/Stripe sans rien logger. Le pire cas: le webhook Stripe
  renvoyait 200 même quand l'écriture en base échouait, donc Stripe ne
  réessayait jamais — un abonnement aurait pu rester désynchronisé
  silencieusement pour toujours. Renvoie maintenant 500 (Stripe réessaie)
  et journalise systématiquement.
- **En-têtes de sécurité** : `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy` ajoutés. Pas de CSP complète pour l'instant — impossible
  à valider sans navigateur réel contre l'app déployée, et une CSP mal
  réglée casse silencieusement l'app plutôt que d'échouer bruyamment.
- **Index de performance** : `(company_id, occurred_at desc)` sur
  `time_entries`, le motif de requête le plus fréquent (dashboard,
  historique, exports).
- `server-only` ajouté explicitement sur `lib/auth/current-user` et
  `lib/supabase/server` (défense en profondeur).

### Vérifié sans problème trouvé

- **Permissions** : chaque page et chaque server action du dashboard
  utilise `requireAdmin()` ou `requireCurrentUser()` de façon cohérente
  avec le rôle attendu (vérifié fichier par fichier).
- **Isolation multi-tenant (au niveau code)** : chaque usage du
  service_role (qui ignore RLS) filtre explicitement par `company_id`,
  sauf les lookups légitimes d'un enregistrement précis par son propre id
  (terminal par id/code d'activation).
- **Injections** : aucune requête SQL construite par concaténation de
  chaîne côté application (uniquement le query builder Supabase);
  `dangerouslySetInnerHTML` jamais utilisé (React échappe tout par
  défaut).
- **Secrets** : aucun secret en dur trouvé dans le code; `.env*` non
  suivi par git; aucune variable sensible préfixée `NEXT_PUBLIC_`.
- **Validation des entrées** : chaque server action lisant un `FormData`
  passe par un schéma Zod (`safeParse`) avant utilisation.
- **Dépendance `exceljs`** : avis de sécurité modéré sur `uuid` en
  dépendance transitive — vérifié dans le code source d'`exceljs`
  qu'il n'appelle que `uuid.v4()`, pas le chemin concerné par l'avis
  (v3/v5/v6 avec un buffer fourni). Pas de downgrade forcé.

### Gaps documentés (décision produit/juridique/infra requise — non résolus ici)

- **RGPD** : pas de mécanisme d'anonymisation d'un employé (le schéma
  interdit volontairement la suppression pour préserver l'historique de
  pointage — voir Phase 3 — mais rien ne permet aujourd'hui de répondre à
  un droit à l'effacement autrement qu'en gardant les données). Pas de
  politique de rétention configurable. Aucune durée n'a été inventée
  (conforme à la consigne), donc rien n'est automatiquement purgé.
- **Isolation MANAGER par site** : un MANAGER peut aujourd'hui gérer les
  employés de toute l'entreprise, pas seulement "ses" sites comme
  l'envisage le cahier des charges — limitation déjà documentée depuis la
  Phase 3, nécessiterait une table d'association utilisateur↔site.
- **Rate limiting** : aucune limitation de débit nulle part (connexion,
  PIN au terminal, invitations) — nécessite une infrastructure dédiée non
  encore choisie.
- **Tests d'intégration automatisés** : les 52 tests couvrent toute la
  logique pure (transitions de pointage, calcul du temps travaillé,
  anomalies, échappement CSV, limite d'employés, abstraction
  d'identification, file hors-ligne). Aucun test automatisé ne touche
  encore une vraie base de données — le parcours ci-dessous a été validé
  **manuellement**, pas par une suite de tests reproductible. Écrire de
  vrais tests d'intégration (contre un projet Supabase de test, avec
  seed/teardown) reste à faire avant un premier client réel.
- **Conformité légale** : rien dans KLOCK n'a été validé par un juriste;
  le produit continue de se présenter comme "conçu pour répondre aux
  besoins" plutôt que "conforme", conformément à la consigne initiale.

### Validation manuelle en conditions réelles (post-audit)

Un vrai projet Supabase a été créé et lié (schéma des 10 migrations
appliqué via son SQL Editor — cette session de développement n'a pas
d'accès réseau sortant vers `supabase.co`, donc l'application des
migrations et tout le test ci-dessous ont été faits par l'utilisateur en
local, pas depuis cette session). Parcours validé de bout en bout, pour
de vrai, contre cette base:

signup (création entreprise + premier ADMIN) → dashboard → création d'un
employé avec PIN → création et activation d'un terminal → identification
PIN sur `/terminal` → pointage ARRIVÉE enregistré → visible dans le
dashboard.

Cela confirme en conditions réelles: Supabase Auth (`admin.createUser`),
la fonction atomique `create_company_with_admin`, les policies RLS (accès
via la session authentifiée), l'authentification du terminal par token, et
`recordClockEvent` (identification + validation de transition +
écriture). **Non testé pour l'instant**: deuxième entreprise pour
vérifier l'isolation croisée, corrections de pointage, journal d'audit,
mode hors-ligne, exports, et tout le flux Stripe (aucune clé Stripe
configurée).
