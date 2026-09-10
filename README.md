# PréVisite

Application mobile (Android + iOS, React Native / Expo) qui aide à analyser
un bien immobilier **avant** de le visiter, pour éviter des déplacements
inutiles. Marché cible initial : Belgique (Wallonie en priorité).

**PréVisite ne remplace pas un expert immobilier.** L'outil donne une
première indication objective pour filtrer les biens qui ne valent
clairement pas le déplacement — ce rappel apparaît sur l'accueil, l'écran de
résultat et dans le footer de l'app.

## Architecture

Monorepo npm workspaces :

```
apps/
  mobile/    App Expo (React Native + TypeScript) — Android/iOS via Expo Go en dev
  backend/   API Node.js/Express + TypeScript, Prisma (SQLite dev / PostgreSQL prod)
packages/
  shared/    Types, schémas zod, moteur de scoring (règles explicites), cache Statbel mocké
docs/
  scoring-formula.md   Formule de scoring documentée en détail
```

Le moteur de scoring (`packages/shared/src/scoring`) est un ensemble de
fonctions pures, testées, indépendantes de l'IA : voir
[`docs/scoring-formula.md`](docs/scoring-formula.md). Le LLM (Claude) n'est
utilisé que pour (1) structurer l'analyse visuelle des photos et (2) rédiger
la synthèse finale à partir du score déjà calculé — jamais pour décider du
score lui-même.

## Prérequis

- Node.js ≥ 18
- Un compte [Anthropic](https://console.anthropic.com/) (clé API Claude, avec
  accès à un modèle vision)
- Un compte [Stripe](https://dashboard.stripe.com/) en mode test
- L'app [Expo Go](https://expo.dev/go) sur ton téléphone pour tester
  rapidement sans build natif
- Un téléphone et l'ordinateur de dev sur le **même réseau Wi-Fi**

## Installation

```bash
npm install
npm run build:shared
```

## Backend

```bash
cd apps/backend
cp .env.example .env   # renseigne ANTHROPIC_API_KEY, STRIPE_SECRET_KEY, JWT_SECRET...
npx prisma migrate dev --name init
npm run prisma:seed    # crée un utilisateur de démo (demo@previsite.be / previsite-demo)
npm run dev
```

L'API démarre sur `http://localhost:4000`. Vérifier : `GET /health`.

## Mobile

```bash
cd apps/mobile
npm run start
```

Scanner le QR code avec l'app Expo Go (Android) ou l'appareil photo (iOS).
L'app détecte automatiquement l'IP du poste de dev pour joindre l'API — si ça
ne fonctionne pas (réseau restrictif), renseigne `EXPO_PUBLIC_API_URL` dans
`apps/mobile/.env`.

## Tests

```bash
npm run test:shared    # moteur de scoring (règles explicites, cas limites)
npm run test:backend
```

## Modèle économique

- 3 analyses gratuites à vie par compte (pas par jour)
- Packs de crédits ensuite (5 / 15 analyses), paiement à l'acte via Stripe —
  pas d'abonnement

## État de l'intégration Stripe

Le backend crée bien un `PaymentIntent` Stripe en mode test et le webhook
`payment_intent.succeeded` crédite le compte. **L'écran de saisie de carte
natif (Stripe Payment Sheet)** nécessite un build de développement personnalisé
et n'est pas disponible dans Expo Go : il sera branché à l'étape du build EAS
(voir plus bas). Pour tester le flux serveur dès maintenant, utilise les
[cartes de test Stripe](https://stripe.com/docs/testing) directement via le
Dashboard ou un client HTTP.

## Données de marché (Statbel)

Le MVP démarre avec un cache local d'un échantillon de communes wallonnes
(`packages/shared/src/market/statbel-mock-data.ts`). Le point d'extension
pour brancher un vrai jeu de données ouvertes Statbel est documenté dans
`apps/backend/src/jobs/import-statbel.job.ts` — il remplace le cache sans
changer l'API utilisée par le moteur de scoring.

## Déploiement

- **Comptes développeur** : un compte Apple Developer Program et un compte
  Google Play Console sont nécessaires pour publier sur les stores (à créer
  par le porteur du projet — hors périmètre du code).
- **Build natif** : une fois les comptes créés, utiliser
  [EAS Build](https://docs.expo.dev/build/introduction/) (`eas build`) pour
  générer les binaires Android (`.aab`) et iOS (`.ipa`).
- **Backend** : à héberger indépendamment de l'app mobile (ex. Render,
  Railway, Fly.io...), avec PostgreSQL en production (la variable
  `DATABASE_URL` suffit à basculer de SQLite à PostgreSQL via Prisma).

## Sécurité — suivi

`npm audit` signale des vulnérabilités transitives connues (chaîne
`express → qs`, chaîne de build `vitest → vite → esbuild`, dépendances de
l'écosystème React Native). Aucune n'affecte directement le code applicatif
de ce MVP ; à surveiller et corriger au fil des mises à jour amont plutôt que
forcées maintenant (`npm audit fix --force` casserait des versions pinnées
pour la compatibilité Expo SDK 57 / React 19).
