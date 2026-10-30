# FC27 Sniper Analyst : brief complet pour une autre IA

> **À toi, l'IA qui lis ce document.** Tu vas aider à améliorer un outil d'analyse du marché des transferts d'EA SPORTS FC 27 Ultimate Team (FUT). Ce document décrit ce qui existe, ce qui marche, ce qui ne marche pas, et surtout **comment pense un joueur FUT expérimenté**. Lis-le en entier avant de proposer quoi que ce soit.
>
> Ce qu'on attend de toi :
> 1. des pistes d'amélioration, d'ajouts et de simplification, **classées par impact**, et pensées comme un trader FUT qui joue depuis FIFA 12 ;
> 2. pour chaque piste, une explication concrète de **comment la faire**, à la fois pour le développeur (une autre IA, qui code) et pour le propriétaire (non-développeur, sur téléphone).
>
> Les contraintes de la section 2 ne sont **pas négociables**.

---

## 1. Le projet en une minute

- **Ce que c'est** : un bot Python qui tourne **24 h/24** sur un petit VPS. Il relève les prix d'environ 250 cartes FUT toutes les heures, apprend les habitudes du marché, et **dit quand acheter et quand vendre**.
- **Ce qu'il ne fait pas** : il **n'achète jamais tout seul**. C'est un analyste, pas un bot d'achat. L'utilisateur achète et vend lui-même dans le jeu.
- **Où arrivent les infos** :
  - **Discord** (webhook) : alertes, rapport de prix 2 fois par jour, résumé quotidien. Le salon est partagé avec 3 amis.
  - **Dashboard web** consulté sur iPhone et PC.
- **Le propriétaire** :
  - joueur FUT, **pas développeur** ;
  - fait presque tout **depuis son téléphone** : l'appli Termius pour le SSH, et GitHub sur mobile ;
  - les commandes doivent être **courtes et copiables** ; les longues commandes sur une ligne cassent au collage.
- **Budget visé** : il trade surtout entre **20 000 et 100 000 crédits**, et jusqu'à 200 000.

---

## 2. Contraintes non négociables

1. **Aucun achat ni vente automatique**, et **aucune automatisation de la Web App ou de la Companion App d'EA**. C'est contraire aux conditions d'utilisation d'EA et c'est un risque de **ban du compte**. Ça exclut les extensions de type autobuyer et le « Paletools en mode auto ».
2. **Aucun contournement des protections anti-bot.** Ça veut dire : pas de résolution de Cloudflare ou Turnstile, pas de navigateur « furtif » (Camoufox, undetected-chromedriver…), pas de rotation de proxys pour passer un blocage. FUT.GG et FUTBIN bloquent les serveurs volontairement, on respecte ce choix. Les sources doivent être lisibles **normalement**, dans le respect de leur `robots.txt` et de leurs conditions.
3. **Aucun secret dans le code ni dans GitHub.** Les secrets (webhook Discord, mot de passe du dashboard, identifiants du proxy) vivent uniquement dans `.env` sur le VPS. Le fichier `.env.example` sert de modèle vide.
4. **Ressources limitées** : VPS OVH de **4 Go de RAM** à environ 17 €/mois. On évite le navigateur headless permanent et les gros modèles de ML.
5. **Tout doit rester en français** : messages Discord, dashboard, logs utiles à l'utilisateur.

---

## 3. Architecture actuelle

### Stack
- **Python 3.11** dans **Docker** (`python:3.11-slim` + Playwright Chromium, rarement utilisé), avec `docker-compose` et `restart: always`.
- **Données** : SQLite en mode WAL (`data/market_history.db`), dans un volume `./data`.
- **Planification** : APScheduler, fuseau `Europe/Paris`.
- **Calcul** : pandas et numpy ; graphiques avec matplotlib (Discord) et Chart.js embarqué (dashboard).
- **Dashboard** : FastAPI + uvicorn sur le port 8000, protégé par un login HTTP Basic. HTML/CSS/JS faits main, **aucun CDN**.

### Arborescence (rôle de chaque module)
```
config.py              toutes les variables (.env) et leurs valeurs par défaut
main.py                interface en ligne de commande : run, watchlist, snapshot, analyze, backtest, learn, resume, price-report, diagnose, demo-seed…
database/db.py         tables players, price_snapshots (+ trend_7d), market_events, alerts, leaks, evolutions, bot_status… ; price_stats()
scrapers/
  base.py              « Fetcher » : httpx, avec délai minimal entre requêtes, circuit breaker, pause persistante si blocage,
                       détection des pages d'erreur ; FlareSolverr et Playwright existent mais ne servent plus
  futgenie.py          SOURCE ACTUELLE DES PRIX (futgenie.gg) : listes par tranche de prix + fiches joueur
  watchlist.py         construit la liste de ~250 joueurs par tranches de prix (quotas configurables)
  price_provider.py    relevé horaire des prix de la watchlist
  futgg.py / futbin.py ANCIENNES sources : FUT.GG et FUTBIN, bloquées depuis un serveur (Cloudflare)
  latest_players.py    nouvelles cartes de 19 h     ┐
  sbc.py, evolutions.py SBC et Évolutions           ├ dépendaient de FUT.GG : ne fonctionnent plus
  requirements_parser.py exigences des SBC/Évos     ┘
  leak_watcher.py      leaks via l'aperçu public des canaux Telegram (https://t.me/s/<canal>), mots-clés FUT
  backfill.py          import d'historique
utils/rarity.py        nom de rareté lisible (TOTW, POTM, Trailblazers, Héros, Icône, Evo, Or rare/non rare…) et couleur
utils/fut_ids.py       correspondance des ID EA vers les noms de ligue, nation et rareté
core/
  analyzer.py          le « cerveau » : 5 règles instantanées + habitude apprise -> Signal (action, confiance 1-10, risque)
  pattern_detector.py  cycle hebdomadaire : prix relatif à la moyenne 7 j, profil sur 168 heures, fenêtres connues
  learner.py           apprentissage chaque lundi à 05 h -> core/market_rules.json
  context.py           explique un mouvement (« baisse générale du marché » ou « propre au joueur », creux passager ou tendance de fond)
  signals.py           format des alertes Discord
  backtest.py          rejoue les signaux sur l'historique
  jobs.py              le planning (voir ci-dessous)
alerts/                discord.py, telegram.py (non utilisé), notifier.py (anti-spam, rapports, résumé 24 h), charts.py
dashboard/             app.py (API) + index.html + static/style.css
deploy.sh / install.sh installation en 3 questions et mise à jour sur le VPS
```

### Planning (heure de Paris)
| Quand | Tâche |
|---|---|
| chaque heure à :02 | relevé des prix de la watchlist, analyse, alertes |
| 08 h 00 | reconstruction de la watchlist |
| toutes les 20 min | veille des leaks (Telegram) |
| 18 h 45 | rapport « avant 19 h » |
| 18 h – 20 h toutes les 3 min | détection des nouvelles cartes *(cassé)* |
| 19 h 15 | rapport « après 19 h » |
| 10 h 10 et 22 h 10 | rapport de prix sur Discord (prix, moyenne 7 j, variation 24 h, écart à la moyenne) |
| 23 h 00 | **résumé des 24 dernières heures**, avec consignes, sur Discord et dans le dashboard |
| lundi 05 h 00 | apprentissage des habitudes |
| toutes les 5 min | signal de vie (« heartbeat ») |

### Le cerveau (`core/analyzer.py`)
- **R1 Concurrence** : une nouvelle carte très proche sort (même poste ou poste voisin, même ligue ou nation, note à ±1) → **VENTE** de la carte existante.
- **R2 SBC** : un SBC demande des notes 83-86 ou des liens ligue/nation → **ACHAT** de fodder ou des joueurs liés.
- **R3 Évolution** : une carte pas chère est éligible à une Évo qui ajoute des PlayStyles méta → **ACHAT FORT**.
- **R4 Technique** :
  - chute d'au moins 15 % en 48 h sans carte concurrente → **ACHAT** (panic sell) ;
  - hausse d'au moins 25-30 % en 24 h → **VENTE** (hype).
- **R5 Saturation** : 3 cartes ou plus du même groupe de postes en 7 jours → **VENTE**.
- **Habitude** : un profil hebdomadaire appris sur 168 heures. *Correction après audit : un profil « expert » existe dans le code (`prior_profile()`), mais il n'est utilisé qu'en mode démo. En production, le profil appris est utilisé dès 3-4 jours de données, même avec une confiance nulle. Voir `docs/AUDIT_CERVEAU.md`.*
- **Score final** = 65 % règle instantanée + 35 % habitude.
  - Une règle forte (R1, R4) garde sa direction quoi que dise l'habitude.
  - **La taxe EA de 5 % est déduite.** Un signal sans au moins 4 % de marge nette est rétrogradé.
  - Une alerte n'est envoyée qu'à partir d'une confiance de **7/10**, au maximum 8 par rapport, avec 6 h d'attente minimum par joueur.
- Chaque signal contient : la **moyenne, le min et le max sur 7 j**, l'**écart à la moyenne**, la **tendance sur 7 j**, et une **phrase d'explication**.

### État réel aujourd'hui
| Fonction | État |
|---|---|
| Prix horaires (~157 joueurs OK sur ~158) via futgenie.gg | ✅ |
| Alertes, rapport de prix, résumé 24 h sur Discord | ✅ |
| Dashboard (design épuré, fiche joueur, graphique, heure du dernier scan) | ✅ |
| Apprentissage des habitudes | ✅ mais **pas encore assez d'historique** : le bot tourne depuis quelques jours seulement |
| Nouvelles cartes de 19 h, SBC, Évolutions | ❌ dépendaient de FUT.GG (bloqué) : **il faut une source alternative légitime** |
| Leaks | 🟡 le code existe (Telegram public) mais **aucun canal n'est configuré** |

---

## 4. Les codes du jeu : penser comme un trader FUT de 15 ans

> Les horaires exacts changent un peu chaque année. **Vérifie-les pour FC 27** au lieu de les supposer, mais la logique reste la même depuis FIFA 17-18.

### 4.1 Le calendrier, c'est tout
- **18 h heure UK = 19 h heure de Paris** : contenu quotidien (nouvelles cartes, SBC, objectifs). Toute la vie du marché tourne autour de cette heure.
- **Mercredi 19 h** : nouvelle **TOTW** (équipe de la semaine). Les cartes in-form des joueurs concernés montent, et leurs cartes « or » montent parfois aussi par spéculation.
- **Vendredi 19 h** : début des **promos**. Il y a souvent une 2ᵉ équipe la semaine suivante.
  - Avant : **les prix chutent** avant une grosse promo, parce que tout le monde vend pour ouvrir des packs.
  - Après : **le marché est inondé** juste après l'arrivée des packs.
- **Week-end League / FUT Champions**, du jeudi au lundi :
  - **jeudi-vendredi** : les joueurs achètent leur équipe, donc **les prix méta montent** ;
  - **dimanche soir-lundi** : fin de la WL et récompenses, donc **les gros joueurs se revendent** et les prix plongent.
  - C'est le cycle de base : **acheter dimanche soir ou lundi, revendre jeudi ou vendredi**.
- **Récompenses Rivals** (chaque semaine) : des packs ouverts en masse, donc un **afflux de cartes** et une légère baisse.
- **Les grands événements de l'année** : sortie et accès anticipé (septembre), Halloween / Fright Nights (fin octobre), **Black Friday** (fin novembre), Winter Wildcards / Noël, **TOTY** (janvier, *le* crash de l'année), Future Stars / Fantasy FC (février-mars), **TOTS** (avril-juin), Futties (été).
  - Les traders vendent **avant**, rachètent **pendant**, et revendent **après**.
- **Les Flash SBC et les SBC Icône/Héros** gonflent **brutalement** les prix des fodders. Les leaks permettent de l'anticiper.

### 4.2 Ce qui fait bouger le prix d'une carte
- **Le méta** : vitesse (AcceleRATE *Explosive* ou *Controlled*), **PlayStyles+** (Finesse Shot+, Power Shot+, Rapid+, Quick Step+, Trivela+, Incisive Pass+, Press Proven+, Bruiser+, Intercept+, Anticipate+…), gestes techniques 5★, pied faible 4-5★, taille et morphologie.
- **Les liens** : une carte d'une ligue ou nation **populaire** (Premier League, Liga, France, Brésil…) vaut plus cher. Une carte « pont » qui relie bien une équipe est recherchée.
- **Les SBC** : une demande de notes (fodders **83-91**) ou de ligue/nation précise fait monter les cartes en question.
- **Les Évolutions** : une carte bon marché éligible à une bonne Évo est **raflée**.
- **La concurrence** : une nouvelle carte meilleure au même poste et dans la même ligue fait **chuter** l'ancienne.
- **La rareté et l'offre** : pack weight, nombre de cartes dans les packs, cartes disponibles **en packs ou non**. Une carte retirée des packs devient plus rare.
- **Les restrictions d'EA** : **fourchettes de prix** min/max imposées sur certaines cartes, **cartes non échangeables** (récompenses d'objectifs, SBC) qui n'impactent pas le marché.

### 4.3 Les règles d'or du trader
- **Toujours raisonner après la taxe de 5 %.** Un gain affiché de +5 % est **nul**. Formule : vente × 0,95 − achat.
- **Paliers d'enchère** : les incréments de prix changent selon la tranche (de 50 en 50 à de 1 000 en 1 000 selon le prix). Un conseil doit donner des **prix exacts** qui existent sur le marché.
- **La liquidité compte** : une carte qui se vend 30 fois par heure est plus sûre qu'une carte rare au même profit.
- **Ne jamais investir à l'aveugle avant une promo.** Le risque de crash domine.
- **Diversifier** : ne pas mettre tout le club sur une seule carte.
- **Les méthodes que la commu connaît** :
  - « sniping » de BIN sous le prix (filtres ciblés, prix max) ;
  - **mass bidding** (enchères en masse sur des cartes bon marché) ;
  - « investissements » liés aux leaks ;
  - **fodder trading** avant les SBC ;
  - achat au **crash du dimanche**.
  - Le bot est utile s'il aide à appliquer ces méthodes **manuellement**, avec des prix précis et le bon timing.

### 4.4 Ce que la communauté aime (et utilise déjà)
- **Les sites de référence** : FUTBIN, FUT.GG, futgenie, EasySBC (solutions SBC au moins cher).
- **La communauté** : les leakers (par exemple **FUT Sheriff** sur X), les YouTubeurs trading, les subreddits r/EASportsFC et r/fut.
- **Les formats appréciés** :
  - un **tableau « le moins cher par note »** (fodders 81 à 91) mis à jour ; *c'est LA donnée la plus consultée par la commu* ;
  - des **prix exacts** d'achat et de revente (pas « environ 30k ») ;
  - le **profit net** après taxe, en crédits ;
  - une explication **en une phrase** : « pourquoi ça monte » ;
  - un **calendrier** des événements à venir et des promos probables ;
  - des **graphiques sur 7 et 30 jours** avec min et max ;
  - des alertes **peu nombreuses mais fiables**. Le spam tue la confiance.
- **Le vocabulaire à utiliser** : BIN, fodder, in-form, TOTW, SBC, Évo, méta, PlayStyle+, WL, Rivals, packs, crash, « sniper », marché inondé, carte non échangeable, taxe EA.

---

## 5. Pistes d'amélioration (notre première liste, à challenger)

### A. Valeur pour le trader (le plus important)
1. **Tracker des fodders « le moins cher par note » (81-91)**, avec historique et alerte en cas de hausse brutale. C'est un signal précoce de SBC qui arrive.
2. **Calendrier des événements** (promos, TOTW, WL, Black Friday, TOTY…) intégré au modèle. Le bot saurait qu'**une promo commence vendredi**, et pas seulement « c'est dimanche ».
3. **Portefeuille / suivi de profit** : l'utilisateur note ses achats et ses ventes depuis le dashboard ou une commande Discord. Le bot suit le profit net après taxe, le prix de revente conseillé et le seuil de stop.
4. **Prix exacts sur les paliers EA**, plus une **estimation de liquidité** : nombre de ventes et vitesse.
5. **Alertes personnalisées par budget** : par exemple « j'ai 80k », « seulement des cartes PL », « seulement des spéciales ».
6. **Retrouver une source légitime** pour les nouvelles cartes de 19 h, les SBC et les Évos : une API publique, un flux RSS, une page accessible normalement, ou une saisie manuelle rapide via le dashboard.
7. **Leaks** : configurer les canaux Telegram publics à suivre. Étudier aussi d'autres sources accessibles normalement (flux RSS, comptes X par leur API officielle si le budget le permet).
8. **Backtest visible dans le dashboard** : « sur les 30 derniers jours, les signaux ACHAT ont rapporté X % net ». C'est ce qui crée la confiance.

### B. Facilité d'utilisation
1. **Mises à jour sans mettre le dépôt en public** : une **deploy key** GitHub en lecture seule sur le VPS, ou mieux une **GitHub Action** qui déploie en SSH à chaque modification de `main`. *Aujourd'hui, l'utilisateur doit passer le dépôt en public, lancer `./deploy.sh`, puis le remettre en privé : c'est pénible et risqué.*
2. **HTTPS avec un vrai nom de domaine**, ou un sous-domaine gratuit type DuckDNS, via Caddy. Le cadenas est plus propre et le mot de passe n'est plus envoyé en clair.
3. **Dashboard installable** (PWA) sur l'écran d'accueil de l'iPhone, éventuellement avec notifications push.
4. **Bot Discord interactif** (commandes slash : `/prix Mbappé`, `/top achats`, `/fodder 86`) au lieu du simple webhook.
5. **Page « Réglages » dans le dashboard** (budget, tranches de prix, seuil de confiance, heures des rapports), sans éditer `.env` en SSH.
6. **Sauvegarde automatique** de `data/sniper.db` (chaque nuit, et de façon chiffrée hors du VPS).
7. **Supervision** : une alerte Discord si le bot ne relève plus de prix depuis 2 h, ou si la source change de format.

### C. Qualité technique
1. Validation de la qualité des données : les prix aberrants et les fiches mal lues doivent être exclus.
2. Le modèle d'habitude devra gérer **les événements exceptionnels** (TOTY, Black Friday) au lieu de les apprendre comme une habitude normale.
3. Supprimer le code mort lié à FUT.GG, FUTBIN et FlareSolverr une fois qu'une source de remplacement est en place.

---

## 6. Ce qu'on te demande concrètement

1. **Classe les pistes** de la section 5 (et ajoute les tiennes) selon **impact pour le trader / effort / risque**. Le tout doit tenir dans les contraintes de la section 2.
2. Pour les 5 meilleures, donne :
   - l'**idée côté joueur** (pourquoi un trader FUT l'adorerait) ;
   - le **plan technique** : quels fichiers toucher, quelles données, quelle source légitime ;
   - les **étapes pour le propriétaire**, en commandes courtes à copier sur téléphone.
3. Dis ce qui, dans notre logique de marché (règles R1 à R5, fenêtres horaires, seuils), te paraît **faux ou daté pour FC 27**, et pourquoi.
4. Propose **des sources de données légitimes** pour les prix, les nouvelles cartes, les SBC, les Évos et les leaks, en vérifiant `robots.txt`, les conditions d'utilisation et l'existence d'une API officielle.

**Ne propose pas** : un autobuyer, de l'automatisation de la Web App EA, du contournement de Cloudflare, ou du scraping « furtif ».

---

## 7. Infos pratiques

- **Déploiement** : le code est sur GitHub (dépôt privé). Sur le VPS, dans `/root/sniper`, la commande `./deploy.sh` récupère le code et reconstruit le conteneur Docker.
- **Logs** : `docker compose logs -f --tail 50`.
- **Diagnostic** : `docker compose exec bot python main.py futgenie-test`, `… snapshot`, `… resume`.
- **Tests** : `pytest` (environ 44 tests). Un **mode démo** (`python main.py demo-seed` / `demo-reset`) remplit la base avec des données synthétiques pour essayer le dashboard.
- **Variables utiles** (`.env.example`) : `PRICE_SOURCE`, `WATCHLIST_BANDS`, `ALERT_MIN_CONFIDENCE`, `PRICE_REPORT_HOURS`, `SUMMARY_HOUR`, `DASHBOARD_USER/PASSWORD`, `DISCORD_WEBHOOK_URL`, `PROXY_URL`.
