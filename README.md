# KLOCK

**Le temps de travail, simplement.**

KLOCK est conçu pour répondre aux besoins des entreprises belges en matière de suivi fiable du temps de travail. Ce dépôt contient l'application web (espace employeur) et, à terme, le terminal de pointage (PWA).

> KLOCK n'est pas un avis juridique et ne prétend pas être "conforme" à une réglementation dont les modalités définitives ne sont pas encore connues.

## Stack technique

- **Frontend** : Next.js (App Router), TypeScript strict, Tailwind CSS
- **Backend** : Supabase (PostgreSQL, Auth, Row Level Security)
- **Paiement** : Stripe (à intégrer en Phase 9)
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

Les phases suivantes (NFC, abonnements,
exports, hardening) sont décrites dans le plan de développement du projet.
