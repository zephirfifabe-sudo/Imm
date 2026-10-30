# Bilan de l'étape 0 : caractérisation (aucune règle de décision modifiée)

*Suite de `docs/AUDIT_CERVEAU.md`. Branche `claude/fc27-sniper-analyst`.*

## Ce qui a été modifié dans le dépôt
| Fichier | Nature | Impact sur le bot en production |
|---|---|---|
| `tests/test_characterization.py` | **nouveau** : 13 tests de caractérisation et de migration, 8 reproductions de problèmes | aucun (tests) |
| `core/baseline.py` + commande `python main.py baseline` | **nouveau** : rapport de référence **en lecture seule** | aucun : ne s'exécute qu'à la main, n'écrit rien |
| `docs/BILAN_ETAPE0.md` | ce document | aucun |

**Aucune ligne de `core/analyzer.py`, `pattern_detector.py`, `learner.py`, `signals.py`, `notifier.py` ni `db.py` n'a changé.**

---

## 1. Tests ajoutés et résultats

Suite complète : **57 réussis, 2 ignorés** (ils exigent un navigateur), **8 échecs attendus (xfail)**. Avant l'étape 0 : 44 réussis.

### 1a. Caractérisation : comportement actuel figé (tous ✅)
Les séries de prix sont synthétiques et horodatées à une **date fixe**. Les tests ne dépendent donc ni de l'heure réelle ni du jour de la semaine.

| Test | Comportement figé |
|---|---|
| `test_carac_score_to_action_thresholds` | seuils score → action : ±0,3 et ±0,6 |
| `test_carac_r4_drop_48h_buy` | -20 % en 48 h → R4_CHUTE_48H, **ACHAT 7/10**, score 0,52, « ACHETER 38k-40.4k, revente 44k+ », profit annoncé 1 800 (rebond par défaut 10 %) |
| `test_carac_r4_drop_just_below_threshold_is_ignored` | -14 % → aucun signal |
| `test_carac_r4_pump_24h_sell` | +30 % en 24 h → **VENTE 6/10**, « VENDRE ≥ 51k » |
| `test_carac_confidence_formula` | calcul exact de la confiance ; une habitude seule est plafonnée à ACHAT/VENTE |
| `test_carac_crash_instant_and_full_scan` | -18 % en 24 h → CRASH_INSTANT **et** R4_CHUTE_48H |
| `test_carac_similarity_uses_plus_minus_two` | R1 : une note à ±2 compte encore (0,91), à ±3 non (0,70) |
| `test_carac_select_filters_hold_threshold_and_cooldown` | anti-spam : 2ᵉ envoi bloqué pendant 6 h |
| `test_carac_market_change_needs_five_players` | « mouvement du marché » indisponible sous 5 joueurs |

### 1b. Migration SQLite et sauvegarde (tous ✅)
| Test | Vérifie |
|---|---|
| `test_migration_init_db_is_idempotent_and_keeps_rows` | `init_db()` lancé plusieurs fois ne perd ni ne modifie aucune ligne |
| `test_migration_adds_trend_column_without_losing_history` | une base à l'ancien schéma garde ses 7 relevés intacts quand la colonne `trend_7d` est ajoutée |
| `test_backup_procedure_under_wal_is_complete` | la sauvegarde prévue (API `backup` de SQLite) est complète et intègre en mode WAL |
| `test_baseline_report_is_read_only` | le rapport de référence compte bien les doublons et **ne modifie rien** |

---

## 2. Problèmes reproduits (8 sur 8)

Chaque problème a un test `xfail(strict=True)` qui décrit le **comportement attendu**. Lancés avec `--runxfail`, tous échouent pour la raison prévue :

| # | Test | Résultat obtenu aujourd'hui |
|---|---|---|
| **B1** | `test_audit_b1_one_alert_per_player` | **2 alertes « ACHAT FORT »** pour le même joueur dans le même envoi. *Précision : ça n'arrive que si les deux signaux dépassent 7/10, c'est-à-dire quand l'habitude va dans le même sens. Avec une habitude neutre, CRASH_INSTANT reste à 6/10 et seul R4 part.* |
| **B2** | `test_audit_b2_duplicate_snapshot_counted_once` | 2 relevés à la même heure → `price_stats n = 2` |
| **B3** | `test_audit_b3_context_does_not_read_the_future` | moyenne 7 j vue depuis le passé = **4 958** au lieu de 1 000 : elle inclut les prix futurs |
| **B4** | `test_audit_b4_sell_advice_not_below_observed_price` | prix 52k → « VENDRE ≥ **51k** » |
| **S1** | `test_audit_s1_unproven_habit_does_not_trigger_trades` | prix parfaitement stable, habitude de confiance **0** → **ACHAT** |
| **S3** | `test_audit_s3_no_buy_without_justified_target` | aucun rebond appris → ACHAT accepté, profit annoncé 2 250 calculé sur les 10 % par défaut |
| **S5a** | `test_audit_s5_no_signal_on_stale_price` | dernier prix vieux de **72 h** → signal ACHAT quand même |
| **S5b** | `test_audit_s5_change_not_computed_on_interpolated_point` | variation 48 h calculée à **-25 %** sur un point **jamais relevé** (interpolé). La vraie comparaison (dernier relevé réel) donnerait -40 % |

---

## 3. Référence actuelle (outil `python main.py baseline`)

**Sur le VPS** (à lancer par le propriétaire, après la mise à jour) :
```
cd /root/sniper && docker compose exec sniper python main.py baseline
```
Le rapport donne : profondeur de l'historique, relevés par source, **doublons existants**, fraîcheur par joueur, **trous** (≤ 30 h, donc interpolés, ou plus de 30 h), alertes des 7 derniers jours, confiance de l'habitude, répartition des signaux actuels, et **nombre d'ACHAT/VENTE dus à l'habitude seule**.

**En démo** (35 jours synthétiques), à titre d'exemple de sortie seulement :
- 7 « HABITUDE VENTE » sur 12 joueurs, 10 signaux envoyables, dont 8 dus à l'habitude seule.
- Le backtest sur 14 jours annonce 44 trades, 82 % gagnants, +2 % de ROI moyen.
- ⚠️ **Ce chiffre n'a aucune valeur** : les données démo sont générées à partir du même profil hebdomadaire que le cerveau utilise. Le test est circulaire. Il prouve seulement que la mécanique tourne.

**La vraie référence de performance n'existe pas encore.** Le bot n'a jamais enregistré l'issue de ses signaux (c'est l'objet de l'étape 1-E), et l'historique réel est trop court.

---

## 4. Risques identifiés

| Risque | Gravité | Parade |
|---|---|---|
| **Doublons déjà présents** dans la base du VPS (B2) : une contrainte d'unicité **échouerait** à sa création | moyenne | mesurer d'abord avec `baseline`. Les doublons sont **déplacés dans une table d'archive**, jamais supprimés (voir §6) |
| Corriger S1 va **vider le dashboard** de la plupart des ACHAT/VENTE (habitude non prouvée) | attendu | c'est voulu, mais il faut **expliquer** l'abstention à l'écran (« SURVEILLANCE : habitude non validée ») |
| Corriger S5 (fraîcheur) peut faire **taire** des joueurs mal relevés par futgenie | faible | afficher la raison de l'abstention ; le point coloré « scanné il y a » existe déjà |
| Ajouter SURVEILLANCE / AUCUNE ACTION touche **Discord, dashboard, rapports et résumé** (`action.startswith("ACHAT")` est utilisé à plusieurs endroits) | moyenne | une seule fonction de correspondance ; tests de non-régression sur `price_report`, `daily_summary` et l'API |
| Le nom de la base est **`market_history.db`**, pas `sniper.db` comme écrit dans l'audit | info | corrigé ici ; les commandes utilisent `config.DB_PATH` |
| La base est utilisée en continu par le bot pendant une migration | faible | migration au démarrage du conteneur, **après** une sauvegarde automatique, en une transaction |

---

## 5. Modifications envisagées pour l'étape 1 (non commencées)

Toutes restent **derrière un réglage `BRAIN_VERSION`** : `v1` = moteur actuel, `v2` = moteur corrigé. Par défaut, v2 tourne **en observation seulement** (journalisé, non envoyé) jusqu'à validation.

**1-A. Hygiène (corrige B1 à B4)**
- `dedupe()` appliqué dans `job_snapshot` ;
- unicité (joueur, heure) avec `INSERT OR IGNORE` ;
- `price_stats(..., now=)` ;
- prix de vente jamais sous le prix observé.

**1-B. Qualité des données (S5)**
- par joueur : âge du dernier relevé, nombre de points sur 24 h, 48 h et 7 j, part interpolée ;
- `change()` ne s'appuie plus que sur des **relevés réels** et renvoie « indisponible » sinon ;
- pas de recommandation si le dernier prix a plus de 2 h (réglable).

**1-C. Quatre décisions**
- ACHAT / VENTE / **SURVEILLANCE** / **AUCUNE ACTION**, chacune avec une **raison** lisible (« données trop anciennes », « habitude non validée », « marge nette insuffisante »…) ;
- l'habitude seule ne peut plus produire que SURVEILLANCE tant qu'elle n'est pas validée (S1).

**1-D. Prix explicites**
- trois notions séparées partout :
  - **prix observé** (relevé futgenie, avec son heure) ;
  - **prix théorique** (cible calculée) ;
  - **prix exécutable** : « non connu », car la source ne donne pas les ventes réalisées ;
- **arrondi aux paliers EA** (50 / 100 / 250 / 500 / 1 000) ;
- S3 : plus d'ACHAT sans cible de revente **justifiée par des données** (par exemple max ou percentile observé sur 7 j). Sinon → SURVEILLANCE.

**1-E. Journal de toutes les décisions** (exigence n°3 de ChatGPT)
- nouvelle table `decision_log` : **chaque** décision, y compris SURVEILLANCE et AUCUNE ACTION, avec ses entrées (prix observé et heure, qualité des données, règle, score, version du moteur) ;
- table `decision_outcomes` : évaluation automatique à **6 h, 24 h, 48 h et 7 j** :
  - variation du prix observé ;
  - résultat **théorique** net de taxe ;
  - indicateur « occasion manquée » pour les abstentions suivies d'une forte hausse ;
- **toujours libellé « théorique, basé sur des prix observés »**, jamais « gagné ».

**1-F. Confiance**
- le « x/10 » est remplacé par **score d'opportunité** + **qualité des données** ;
- **probabilité = « non disponible »** tant que les résultats évalués sont insuffisants.

Ordre proposé : **1-A → 1-B → 1-E → 1-C → 1-D → 1-F**. Le journal (1-E) passe tôt pour commencer à accumuler des résultats le plus vite possible, d'abord avec le moteur v1.

---

## 6. Conséquences sur la base de données et le dashboard

**Base de données**
- **Ajouts uniquement** : tables `decision_log`, `decision_outcomes`, `price_snapshots_duplicates` (archive), `schema_version`, et un index unique sur `price_snapshots(player_id, timestamp)`.
- **Aucune table supprimée, aucune colonne retirée, aucune ligne effacée.** Les éventuels doublons sont **copiés** dans l'archive avant d'être retirés de la table principale. Ils sont identiques à la ligne conservée, donc aucune information n'est perdue, et ils restent restaurables.
- Volume estimé du journal : environ 160 décisions par heure, soit environ 115 000 lignes par mois, quelques dizaines de Mo par an. C'est sans souci pour SQLite et le VPS.

**Dashboard et Discord**
- badges SURVEILLANCE / AUCUNE ACTION, et raison de l'abstention dans la fiche joueur ;
- « Confiance x/10 » remplacé par « Opportunité » + « Qualité des données » ; « Probabilité : non disponible » ;
- mention « prix observé à HH:MM, non garanti à l'achat » ;
- « Meilleur moment d'achat appris » masqué tant que l'habitude n'est pas validée ;
- Discord : **moins d'alertes** (abstentions non envoyées), et chaque alerte dit sur quelles données elle s'appuie.

---

## 7. Sauvegarde, migration et retour arrière

1. **Sauvegarde automatique avant toute migration** : `sqlite3.Connection.backup()` vers `data/backups/market_history-AAAAMMJJ-HHMM.db`, suivie d'un `PRAGMA integrity_check`. Si la sauvegarde échoue, la migration est **annulée** et le bot démarre sur l'ancien schéma. *(Procédure testée : `test_backup_procedure_under_wal_is_complete`.)*
2. **Migrations versionnées** (`schema_version`), chacune dans **une transaction** : tout ou rien.
3. **Contrôle après migration** : nombre de relevés après = nombre avant − doublons archivés ; `baseline` relancé et comparé.
4. **Retour arrière, deux niveaux :**
   - **moteur** : `BRAIN_VERSION=v1` dans `.env`, puis `docker compose up -d`. Les nouvelles tables sont simplement ignorées par v1 ;
   - **code et base** : revenir au commit précédent, puis restaurer la sauvegarde :
     ```
     cd /root/sniper && docker compose down
     cp data/backups/market_history-AAAAMMJJ-HHMM.db data/market_history.db
     git checkout <commit> && ./deploy.sh
     ```
5. Les sauvegardes sont conservées 14 jours (rotation). Une copie hors du VPS reste à prévoir (étape « confort »).

---

**Je m'arrête ici.** L'étape 1 ne commencera qu'après validation explicite.
