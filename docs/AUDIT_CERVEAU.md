# Audit du cerveau de Sniper Analyst (phase 0, aucune modification du code)

*Réponse au brief « Refonte de l'intelligence » rédigé par ChatGPT. Code audité : branche `claude/fc27-sniper-analyst`, commit `553ed72`.*

> **Limite de l'audit.** Je n'ai **pas accès à la base de données du VPS**. Tout ce qui concerne le code est vérifié. La profondeur réelle de l'historique, elle, doit être mesurée sur le serveur (commandes en §5). Pour illustrer certains constats, j'ai lancé des scénarios avec le mode démo (données synthétiques). Ils sont signalés par 🧪.

---

## 1. Flux de décision réel (de la collecte à l'alerte)

```
[futgenie.gg] ── scrapers/futgenie.py  FutGenie.current_prices()
      │            relit les listes par tranche de prix (+ fiche joueur si absent, 40 max)
      ▼
scrapers/price_provider.py  _snapshot_futgenie()      chaque heure à :02 (core/jobs.py job_snapshot)
      │  INSERT price_snapshots(player_id, timestamp arrondi à l'heure, price, source, trend_7d)
      │  aucun volume, aucun min/max 24 h (colonnes NULL)
      ▼
core/analyzer.py  MarketAnalyzer.__init__()
      │  pdt.load_frame(10 jours) → pdt.hourly_series() : ré-échantillonnage horaire
      │  + interpolation linéaire des trous jusqu'à 30 h
      ▼
  ┌─ instant_crashes(24)      variation 24 h ≤ -15 % → CRASH_INSTANT
  └─ full_scan()              par joueur : rule4_technical() sinon build_signal("HABITUDE", None)
      │
      ▼
build_signal()  score = 0,65 × instantané + 0,35 × habitude      (habitude seule : bornée à ±0,59)
      │  confiance = 10 × (0,30 + 0,35·|score|/0,8 + 0,20·conf_règle + 0,15·conf_habitude·accord)
      │  filtre taxe : revente attendue = prix × (1 + rebond_appris, 10 % par défaut)
      │  context() : moyenne/min/max 7 j, écart à la moyenne, tendance, explain_move()
      ▼
core/jobs.py job_snapshot : urgent = instant_crashes + [signaux R4 de full_scan]
      ▼
alerts/notifier.py dispatch() → select() : action ≠ HOLD, confiance ≥ 7, 6 h d'attente par (joueur, action), 8 maximum
      ▼
Discord (webhook) + table alerts ; le dashboard recalcule full_scan() à chaque appel (cache 60 s)
```

Autres flux :
- `job_latest` (R1/R5), `job_sbc_evo` (R2/R3) et `job_leaks` existent, mais **leurs sources sont hors service** : FUT.GG est bloqué et aucun canal Telegram n'est configuré.
- `job_learn` (lundi 05 h) → `core/learner.py learn_patterns()` → `data/market_rules.json`.
- Rapports : `notifier.price_report`, `report_pre19`, `report_post19` et `daily_summary` réutilisent `full_scan()`.

**Conséquence directe : en production, seules la règle R4 et l'habitude produisent des signaux.** R1, R2, R3 et R5 ne reçoivent aucune donnée.

---

## 2. Règles R1 à R5 telles qu'elles sont codées

| Règle | Fonction | Ce que fait vraiment le code | Constats |
|---|---|---|---|
| **R1 Concurrence** | `analyzer.py rule1_competition()`, `similarity()` | Score de similarité : poste 40 %, lien 30 %, note 30 %. Au-delà de 0,85 → score instantané **fixe de -0,85** (VENTE). | La note est comparée à **±2** (docstring et brief disent ±1). Le prix, la disponibilité, le statut échangeable, les PlayStyles et la qualité de la nouvelle carte sont **ignorés**. Une carte d'objectif non échangeable déclenche la même vente qu'une carte en pack. **Inactive en production** (pas de flux de nouvelles cartes). |
| **R2 SBC** | `rule2_sbc()` | Toute note trouvée dans les exigences → **Signal ACHAT « Fodders » avec confiance 7 et risque « Faible » codés en dur**, sans passer par `build_signal()`. Les liens ligue/nation → `build_signal(0,55)`. | La note **d'équipe** (`min_team_rating` 84) est traitée comme une note **de joueur** à acheter. Pas de prix, pas de joueur précis, pas de calcul de marge : le filtre taxe ne s'applique pas. Le message promet « discard +10-15 % » sans aucune donnée. **Inactive.** |
| **R3 Évo** | `rule3_evo()` | Candidats ≤ 20 000 éligibles, score = OVR final + 2,5 × PlayStyles méta − prix/10k → **ACHAT FORT, confiance 6-7 fixe**. | Le texte promet « **revente +30-80 % dans 2-12 h** » sans aucune mesure. Cette promesse n'est pas validée. Le statut échangeable n'est pas vérifié. **Inactive.** |
| **R4 Technique** | `rule4_technical()` | Variation 48 h ≤ **-15 %** et aucun concurrent récent → ACHAT (force |c48|/0,25). Sinon variation 24 h ≥ **+30 %** → VENTE. | Seuils **universels** : une carte volatile à 25k et une carte stable à 150k sont traitées pareil. Aucune recherche de stabilisation : on achète **pendant** la chute. `recent_competitor()` dépend du flux nouvelles cartes : il **renvoie toujours False en production**, donc le garde-fou est inopérant. |
| **R5 Saturation** | `rule5_saturation()` | 3 nouvelles cartes ou plus dans un **groupe de postes** en 7 jours → VENTE (-0,5) de **tous** les joueurs de la watchlist de ce groupe. | Granularité trop grossière (« tous les attaquants »), aucune notion de ligue, de note ou de prix. **Inactive.** |
| *(hors liste)* **CRASH_INSTANT** | `instant_crashes()` | Variation 24 h ≤ -15 % → +0,7 (ACHAT), ou **-0,3 (vente) si concurrent**. | Il double R4 (voir bug B1). |
| *(hors liste)* **HABITUDE** | `build_signal(..., None)` + `pattern_detector.habit_assessment()` | Score = (0,6 × hausse max du profil sur 96 h + 0,4 × baisse min sur 48 h) / 10 %. | Voir faiblesse S1 : c'est **la source n°1 des signaux affichés**. |

---

## 3. Faiblesses statistiques démontrées par le code

**S1. L'habitude produit des signaux à partir de bruit, dès quelques jours de données.**
- `learner.learn_patterns()` crée un profil GLOBAL dès qu'il y a 72 points relatifs. Avec `relative()` (min_periods=48), **3 à 4 jours suffisent**.
- La confiance de ce profil vaut **0,0** (aucune semaine complète observée). Mais `build_signal()` utilise quand même `hs` (le score d'habitude) pour décider de l'action. La confiance n'agit que sur la note sur 10, pas sur la direction.
- 🧪 Avec 5 jours de données démo et un apprentissage : `GLOBAL confidence 0.0`, `best_buy "Lun 0h-4h"`, et **6 joueurs sur 12 affichés VENTE** (confiance 5-6) **uniquement à cause de l'habitude**.
- Ces signaux n'atteignent pas Discord (seuil 7), mais ils **remplissent le dashboard** (badges VENTE, bloc « Meilleures opportunités », compteurs).
- Le dashboard affiche aussi « Meilleur moment d'achat appris » calculé sur ces quelques jours.

**S2. Le « profil expert » annoncé n'est pas utilisé en production.**
- `pattern_detector.prior_profile()` n'est appelé **que par `core/demo.py`**.
- Le fichier par défaut `core/market_rules.json` n'a **pas de clé `profile`**, donc `rule_for()` renvoie `{}` et l'habitude vaut 0 tant que le premier apprentissage n'a pas tourné. Ensuite, c'est le profil appris (bruité, voir S1) qui est utilisé.
- Le brief initial (et l'ancienne doc) affirment le contraire. **C'était une erreur de ma part dans la documentation.**

**S3. Le filtre taxe est neutralisé par sa valeur par défaut.**
- `build_signal()` calcule `rec = avg_recovery_value or 0.10`, puis une marge = 1,10 × 0,95 − 1 = **+4,5 %**. C'est juste au-dessus de `MIN_NET_MARGIN = 4 %`.
- Résultat : **tant qu'aucun rebond n'a été appris, aucun ACHAT n'est jamais bloqué par la taxe.**
- Le rebond appris (`avg_recovery_value`) mesure « creux du dimanche → jeudi ». Il est appliqué **quel que soit le jour** du signal, y compris un jeudi où le rebond est déjà fait.

**S4. Score, confiance et probabilité sont confondus.**
- La confiance a un **plancher de 3/10** (terme constant 0,30) et monte avec |score|. C'est donc surtout une **reformulation du score**.
- R2 et R3 fixent la confiance à la main (6-7).
- Aucune de ces « confiances » n'est calibrée sur des résultats passés.
- Le libellé « Risque : Faible » de R2 est codé en dur.

**S5. Données manquantes interpolées sans le dire, et aucun contrôle de fraîcheur.**
- `hourly_series()` interpole linéairement les trous **jusqu'à 30 h**. `change(pid, 48)` peut donc comparer à un point **inventé**.
- Après un trou de plus de 30 h, `change()` prend le dernier point avant la date visée. Une « variation 48 h » peut alors porter sur 4 ou 5 jours.
- `price_now()` renvoie le dernier prix connu **sans vérifier son âge**. Un joueur sorti des listes futgenie depuis 3 jours garde son ancien prix, et peut recevoir un signal ACHAT ou VENTE sur une donnée périmée.
- Le dashboard montre désormais l'âge du scan, mais le cerveau, lui, n'en tient pas compte.

**S6. Prix « exécutable » inconnu.**
- Le prix stocké est celui qu'affiche futgenie dans ses listes. Plusieurs points ne sont **ni vérifiés ni documentés** : est-ce le plus petit BIN ? Pour quelle plateforme (console ou PC) ? Avec quel délai ?
- Il n'y a **aucun volume** (`volume` toujours NULL), donc aucune mesure de liquidité.
- Les conseils « ACHETER 31.2k-33.2k » sont calculés en `prix × 0,95 / × 1,01`, **sans arrondi aux paliers EA**.

**S7. Le « marché » est la watchlist.**
- `market_change()` prend la médiane des variations de la watchlist. Celle-ci est biaisée : 20k-200k, triée par note futgenie (`grade-desc`), et donc sur-pondérée en cartes populaires.
- C'est utile pour distinguer « mouvement général » et « mouvement individuel », mais ce n'est pas un indice de marché.

**S8. Signaux d'habitude corrélés entre tous les joueurs.**
- Le score d'habitude dépend surtout de **l'heure de la semaine**. Le profil GLOBAL est le même pour tous les joueurs qui n'ont pas de profil personnel fiable.
- Résultat : **beaucoup de joueurs reçoivent le même signal en même temps** (tous VENTE le vendredi, tous ACHAT le dimanche). Ce n'est pas de la diversification, c'est un seul pari répété N fois.

---

## 4. Bugs, doublons et incohérences

| # | Fichier / fonction | Constat | Exemple |
|---|---|---|---|
| **B1** | `core/jobs.py job_snapshot` + `notifier.select()` | `instant_crashes(24)` et les signaux R4 sont **concaténés sans dédoublonnage**. `_in_cooldown()` lit la base **avant** l'enregistrement : les deux passent. | Un joueur à -16 % sur 24 h et -18 % sur 48 h reçoit **deux alertes ACHAT dans le même message** (CRASH_INSTANT et R4_CHUTE_48H). `analyzer.dedupe()` existe mais n'est pas appelé ici. |
| **B2** | `database/db.py` schéma `price_snapshots` | Pas de contrainte `UNIQUE(player_id, timestamp)`. Lancer `python main.py snapshot` à la main pendant l'heure crée des **doublons**. | `hourly_series()` les écrase (keep last), mais `price_stats()` (AVG/COUNT) les compte deux fois. |
| **B3** | `database/db.py price_stats()` et `analyzer.context()` | `price_stats()` utilise `utcnow()` et non `analyzer.now`. | En **backtest**, la moyenne, le min, le max et l'écart à la moyenne regardent **le futur**. C'est sans effet sur la décision aujourd'hui (affichage seulement), mais c'est un **piège** si l'on s'en sert demain pour décider. |
| **B4** | `analyzer.build_signal()` | Le texte VENTE dit « VENDRE maintenant ≥ prix × 0,98 », soit **en dessous du prix observé**, et sans arrondi aux paliers. | Prix 78 200 → « ≥ 76.6k ». |
| **B5** | `analyzer.similarity()` | Docstring et brief : note **±1** ; code : **±2** (score 0,7 à ±2). | — |
| **B6** | `analyzer.rule2_sbc()` | Les notes d'équipe et les notes de joueur sont mélangées dans `ratings`. | « SBC demande des notes 84 » pour une équipe notée 84, qui se fait en réalité avec un mélange de 82 à 86. |
| **B7** | `dashboard/app.py api_status` / UI | « Meilleur moment d'achat appris » et « crash WL moyen » sont affichés **même quand la confiance vaut 0**. | Voir S1. |
| **B8** | `core/backtest.py` | Cible de revente fixe (`MIN_NET_MARGIN`) **différente** de la cible annoncée par le signal (`rebond appris`). | Le backtest ne mesure donc pas ce que dit l'alerte. |

---

## 5. Qualité et profondeur des données

**Ce que le code garantit :**
- un point par heure (arrondi à l'heure pile), source `futgenie` ;
- environ 157 joueurs sur 158 réussis par relevé (dernier log connu) ;
- `trend_7d`, la tendance 7 jours affichée par futgenie, est stockée à chaque relevé ;
- **aucun** volume, min ou max 24 h, nombre de ventes ou plateforme.

**Ce qui reste à mesurer sur le VPS** (je ne peux pas le voir d'ici). Commande à lancer :
```
cd /root/sniper && docker compose exec bot python -c "
from database import db
with db.get_conn() as c:
  print(c.execute('select min(timestamp), max(timestamp), count(*), count(distinct player_id) from price_snapshots').fetchone())
  print(c.execute('select source, count(*) from price_snapshots group by source').fetchall())"
```

**Ordre de grandeur attendu** : le bot tourne sur futgenie depuis **quelques jours**. Avec si peu d'historique :
- **0 semaine complète** : aucun cycle hebdomadaire n'est mesurable ;
- **0 promo observée** ;
- **0 signal évalué**.

Aucune statistique de réussite n'est donc possible aujourd'hui. **ChatGPT a raison sur ce point** : le moteur doit le dire et s'abstenir.

---

## 6. Pertinence du backtest actuel (`core/backtest.py run_backtest`)

**Bon :**
- les règles sont apprises **uniquement avant** la période de test (`learn_patterns(now=start)`) ;
- l'analyseur ne voit que les prix ≤ t (`load_frame(now=t)`) ;
- la taxe de 5 % est appliquée ;
- une seule position à la fois par joueur.

**Insuffisant :**
- Il ne teste que `full_scan()`, donc R4 et l'habitude. **Ni R1/R2/R3/R5 ni CRASH_INSTANT.**
- Achat **au prix observé**, revente **au premier relevé horaire ≥ cible**. C'est optimiste (prix affiché ≠ prix exécuté, aucune liquidité).
- **Aucune référence de comparaison** : ni « ne rien faire », ni achat aléatoire au même moment, ni « acheter dimanche, revendre jeudi » en mécanique simple.
- Aucun résultat par horizon (6 h, 24 h, 48 h, 7 j), aucun drawdown, aucune distribution, aucun intervalle d'incertitude.
- Un pas de 6 h et un seul apprentissage pour toute la période (pas de « walk-forward » hebdomadaire).
- Ce que le backtest mesure n'est pas ce que dit l'alerte (B8).
- **Avec quelques jours de données, il n'a aucune valeur statistique.**

---

## 7. À conserver absolument

1. **Le principe « analyste, pas acheteur »**, ainsi que la discipline réseau (`scrapers/base.py` : délais, circuit breaker, pause persistante, aucun contournement).
2. **Le stockage brut** `price_snapshots` horaire. C'est le capital de données : à ne jamais écraser.
3. **`core/context.py explain_move()`** : la séparation entre mouvement général et mouvement individuel, et entre creux passager et tendance de fond. C'est le germe de la « force relative » demandée.
4. **La prise en compte de la taxe** et le principe d'un seuil de marge nette (à corriger, voir S3).
5. **L'anti-spam** (`notifier.select` : seuil, attente minimale, plafond) et la règle « une règle forte garde sa direction ».
6. **L'architecture du backtest sans fuite des règles**, à étendre plutôt que réécrire.
7. **Le mode démo et les 44 tests**, qui permettent de changer le cerveau sans risque.

---

## 8. À corriger, remplacer ou supprimer

| Élément | Décision |
|---|---|
| Habitude utilisée pour décider alors que sa confiance est faible (S1, S2, S8) | **Corriger** : en dessous de N semaines observées ou d'une confiance minimale, l'habitude **n'influence plus l'action**. Elle reste affichée comme « information ». Les signaux qui ne reposent que sur elle deviennent **SURVEILLANCE** ou **AUCUNE ACTION**. |
| Profil expert jamais chargé (S2) | **Décider** : soit on l'utilise **explicitement étiqueté « prior »** avec un poids faible, soit on le retire. Il faut corriger la doc dans les deux cas. |
| Rebond par défaut à 10 % (S3) | **Remplacer** par une cible fondée sur des données (moyenne 7 j, percentile, max récent), **ou** bloquer l'achat si aucune cible n'est justifiable. |
| Confiance /10 (S4) | **Séparer** en *score d'opportunité* (classement), *qualité des données* (fraîcheur, nombre de points, trous) et *probabilité* (« non disponible » tant que N signaux évalués < seuil). |
| Fraîcheur et interpolation (S5) | **Ajouter** un garde-fou : pas de signal si le dernier prix a plus de 2 h, ou si le point de comparaison est interpolé ou trop ancien. Limiter l'interpolation au **calcul du profil** et ne plus l'utiliser dans `change()`. |
| Seuils fixes de R4 (-15 %, +30 %) | **Rendre adaptatifs** (z-score robuste sur la volatilité propre à la carte), tout en **gardant** les seuils fixes comme garde-fou quand l'historique est insuffisant. Ajouter la séquence chute → ralentissement → stabilisation avant tout ACHAT. |
| Prix conseillés | **Arrondir aux paliers EA** et ne jamais proposer de vendre sous le prix observé (B4). |
| B1 doublons d'alertes | **Corriger** : appliquer `dedupe()` dans `job_snapshot`. |
| B2 doublons de relevés | **Corriger** : index `UNIQUE(player_id, timestamp)` + `INSERT OR REPLACE`. La migration doit d'abord dédoublonner (sauvegarde avant). |
| B3 `price_stats` qui lit le futur | **Corriger** : passer `now` en paramètre. |
| R1/R2/R3/R5 | **Geler** tant qu'aucune source légitime n'existe. Ensuite, refondre selon le brief (score de menace pour R1, R2 sans confiance codée en dur, R3 sans promesse chiffrée, R5 transformée en mesure d'exposition). |
| CRASH_INSTANT | **Fusionner** avec la nouvelle R4 : c'est un doublon conceptuel. |
| Libellés « appris » au dashboard (B7) | **Masquer** ou afficher « données insuffisantes » tant que la confiance est trop basse. |
| Décisions | **Ajouter** SURVEILLANCE et AUCUNE ACTION. ACHAT FORT et VENTE URGENTE ne seront accessibles qu'après validation statistique. |

---

## 9. Plan de migration en petites étapes

Chaque étape fait l'objet d'un commit séparé, testé, et réversible. L'ancien moteur reste disponible derrière un réglage (`BRAIN_VERSION=v1|v2`) jusqu'à validation.

| Étape | Contenu | Risque | Effet visible |
|---|---|---|---|
| **0. Tests de caractérisation** | Figer le comportement actuel (voir §10) avant de toucher quoi que ce soit. | nul | aucun |
| **1. Hygiène** | B1 (dédoublonnage des alertes), B2 (index unique + migration avec sauvegarde), B3 (`now` passé à `price_stats`), B4 (pas de vente sous le prix), B5 (aligner ±1 ou ±2 et documenter). | faible | moins de doublons |
| **2. Fraîcheur et qualité des données** | Module `core/data_quality.py` : âge du dernier point, nombre de points sur 24 h, 48 h et 7 j, trous, part interpolée. Pas de signal si la qualité est insuffisante. `change()` n'utilise plus de points interpolés. | faible | signaux en moins sur les joueurs mal relevés |
| **3. Décisions à 4 états** | ACHAT / VENTE / SURVEILLANCE / AUCUNE ACTION. L'habitude seule ne donne plus que SURVEILLANCE tant qu'elle n'est pas validée. Dashboard et Discord adaptés. | moyen (côté interface) | dashboard beaucoup plus calme et honnête |
| **4. Trois indicateurs séparés** | Score d'opportunité / qualité des données / probabilité (« non disponible »). Remplace « confiance x/10 » partout. | moyen | — |
| **5. Journal des signaux** | Tables `strategy_signals` et `signal_outcomes` : chaque signal est enregistré avec ses données d'entrée, puis évalué automatiquement à 6 h, 24 h, 48 h et 7 j (net de taxe). **C'est l'étape la plus importante** : sans elle, aucun apprentissage n'est possible. | faible | page « performance » (vide au début, et c'est normal) |
| **6. Indicateurs statistiques** | `core/market_features.py` : volatilité, z-score robuste, percentile, variations multi-horizons sans interpolation. Plus force relative vs watchlist et vs groupe (même poste, même tranche de prix), en étendant `context.py`. | faible | explications plus fines |
| **7. Nouvelle R4** | Seuils adaptatifs et séquence chute → stabilisation → ACHAT. Cibles de revente justifiées par les données et arrondies aux paliers EA. | moyen | moins d'achats « au couteau qui tombe » |
| **8. Backtest v2** | Toutes les règles, horizons multiples, comparaison avec les références (ne rien faire, achat aléatoire, cycle dimanche/jeudi naïf), apprentissage walk-forward, drawdown. | faible | rapport de performance |
| **9. Contexte événementiel** | `event_history` horodaté (date de publication de l'info ≠ date de l'événement), statut CONFIRMÉ / ANNONCÉ / PROBABLE / SPÉCULATIF, saisie manuelle possible depuis le dashboard. | moyen | calendrier des promos |
| **10. Régime de marché, puis ML** | Seulement après plusieurs semaines de signaux évalués, en mode « shadow » d'abord. | — | — |

**Ordre de priorité réaliste** : 0 → 1 → 2 → 3 → 5. Ces étapes sont faisables tout de suite et apportent le plus de fiabilité. Les étapes 6 à 8 viendront quand il y aura 3 à 4 semaines de données. L'étape 10 ne viendra pas avant plusieurs mois.

---

## 10. Tests à écrire avant toute modification

1. **Caractérisation de `build_signal()`** : pour quelques entrées fixes (score instantané, habitude, confiance), on fige l'action, la confiance et le texte actuels. Ça permet de voir exactement ce qui change ensuite.
2. **B1** : scénario démo avec une chute de -16 % en 24 h et de -18 % en 48 h, puis `job_snapshot`. On vérifie le nombre d'alertes par joueur (aujourd'hui 2, attendu 1).
3. **B2** : deux `insert_snapshot` à la même heure. On vérifie `price_stats()["n"]`.
4. **B3** : `MarketAnalyzer(now=passé)`. `context()` ne doit pas utiliser de prix postérieurs à `now`.
5. **S5 fraîcheur** : un joueur dont le dernier relevé date de 3 jours ne doit produire aucun signal ACHAT/VENTE.
6. **S5 interpolation** : un trou de 20 h juste avant le point « il y a 48 h ». `change(48)` ne doit pas s'appuyer sur un point inventé.
7. **S1** : 5 jours de données, apprentissage, `full_scan()`. Aucun ACHAT/VENTE ne doit être dû à l'habitude seule.
8. **S3** : sans rebond appris, un ACHAT ne doit pas passer le filtre taxe « par défaut ».
9. **Paliers EA** : `round_to_tier(prix)` sur chaque tranche de prix.
10. **Backtest sans fuite** : en injectant un prix futur extrême, les signaux émis avant cette date ne doivent pas changer.

---

## Réponse au brief de ChatGPT (en une phrase par point)

- **Le diagnostic général est juste**, et confirmé par le code : seuils fixes, confusion score/confiance, historique trop court, pas d'abstention, pas d'évaluation des résultats.
- **Deux choses sont pires que ce que supposait le brief** : l'habitude décide déjà avec une confiance de 0 (S1), et le filtre taxe ne bloque rien par défaut (S3).
- **Une chose est meilleure** : le backtest est déjà sans fuite pour les règles apprises, et `explain_move` fait déjà une forme de force relative.
- **Aucun des 10 nouveaux modules ne doit être créé tel quel tout de suite.** Plusieurs responsabilités existent déjà : `context.py` ↔ relative_strength, `pattern_detector.py` ↔ player_behavior, `backtest.py` ↔ strategy_learner. Le plan ci-dessus les fait évoluer au lieu de les dupliquer.

**Aucun fichier de code n'a été modifié.** J'attends la validation avant de commencer l'étape 0.
