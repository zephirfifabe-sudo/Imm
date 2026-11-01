# Bilan de l'étape 1 : fiabilisation (moteur v2 en observation)

*Commit `34c42fe`, branche `claude/fc27-sniper-analyst`. Fait suite à `docs/BILAN_ETAPE0.md`.*

## En bref
- **Le moteur actuel (v1) reste celui qui envoie les alertes.** Seuls ses 4 bugs ont été corrigés.
- **Le nouveau moteur (v2) tourne en parallèle, en observation** : il décide, journalise et s'évalue, mais n'envoie **rien** sur Discord.
- **Toutes les décisions des deux moteurs** sont désormais enregistrées, y compris les abstentions, puis évaluées automatiquement à 6 h, 24 h, 48 h et 7 j.
- **Aucune donnée historique supprimée.** Une sauvegarde automatique est faite avant la migration de la base.
- **Tests : 76 réussis, 2 ignorés** (navigateur), **4 échecs attendus**. Ces 4 échecs documentent les défauts que l'on garde volontairement dans v1, moteur de retour arrière.

---

## 1. Ce qui a été fait (ordre 1-A → 1-F)

### 1-A Hygiène : corrigé dans v1 **et** v2
| Problème | Correction | Preuve |
|---|---|---|
| B1 deux alertes pour le même joueur | `dedupe()` appliqué dans `job_snapshot` | `test_audit_b1_one_alert_per_player` ✅ |
| B2 relevés en double | index unique (joueur, heure) ; un 2ᵉ relevé dans la même heure **remplace** le premier ; migration v2 de la base (voir §3) | `test_audit_b2…` ✅, `test_migration_v2_archives_duplicates_and_backs_up` ✅ |
| B3 moyenne 7 j qui lisait le futur | `price_stats(now=)` utilisé par l'analyseur | `test_audit_b3…` ✅ |
| B4 vente conseillée sous le prix | arrondi **au palier EA** du prix observé (52 000 → « ≥ 52k », au lieu de 51k) | `test_audit_b4…` ✅ |

### 1-B Qualité des données (v2)
- `MarketAnalyzer.quality()` : âge du dernier relevé, nombre de relevés réels sur 48 h et 7 j, et un **score de qualité /100**.
- Aucune décision si le prix a plus de **2,5 h** (`MAX_PRICE_AGE_H`) ou s'il y a moins de **24 relevés sur 48 h** (`MIN_POINTS_48H`). Le joueur est alors journalisé en **AUCUNE ACTION**, règle `QUALITE_DONNEES`, avec la raison.
- `change_real()` : les variations s'appuient **uniquement sur des relevés réels**, à ±1,5 h de l'heure visée. Sinon : « indisponible », et aucune règle ne se déclenche dessus.

### 1-C Quatre décisions (v2)
**ACHAT / VENTE / SURVEILLANCE / AUCUNE ACTION**, toujours accompagnées d'une **raison** lisible. Exemples :
- « l'habitude suggère une vente mais n'est pas validée (confiance 0 %, 0 semaine observée) » ;
- « marge nette théorique +2,1 % après taxe (min 4 %) » ;
- « données insuffisantes : dernier prix relevé il y a 30 h ».

L'habitude n'influence la décision que si elle est **validée** : confiance ≥ 0,5 **et** au moins 3 semaines observées. Sinon, elle est affichée « non validée : n'influence pas la décision ».

**ACHAT FORT et VENTE URGENTE n'existent plus dans v2.** Ils ne reviendront qu'après validation statistique.

### 1-D Prix explicites (v2)
| Notion | Champ | Exemple |
|---|---|---|
| Prix **observé** (daté) | `observed_price`, `observed_at` | 36 569 relevé à 13h00 |
| Prix d'achat max (palier EA) | `buy_max` | 36 500 |
| Prix **théorique** de revente | `target_price` = moyenne 7 j observée → `sell_min` au palier | 42 000 |
| Net théorique par carte | `sell_min × 0,95 − buy_max` | 3 400 |
| Prix **exécutable** | `executable_price` | **inconnu** : la source ne fournit pas les ventes réalisées |

**S3 corrigé** : plus de rebond « par défaut » de 10 %. Sans au moins 72 relevés sur 7 jours, il n'y a pas de cible justifiable, donc **SURVEILLANCE**. Les messages disent « théorique, non garanti ».

### 1-E Journal de toutes les décisions
- Table `decision_log` : moteur, joueur, décision, règle, score, opportunité, qualité, prix observé et heure, cible, raison, données d'entrée.
- Table `decision_outcomes` : à 6 h, 24 h, 48 h et 7 j, on retrouve le **relevé réel** le plus proche (±1,5 h). Verdicts possibles :
  - **ACHAT** : favorable si (prix × 0,95) − prix observé > 0 ;
  - **VENTE** : favorable si le prix a baissé ;
  - **SURVEILLANCE / AUCUNE ACTION** : « occasion manquée » si un achat aurait rapporté au moins 4 % net, sinon « abstention justifiée » ;
  - « sans donnée » si aucun relevé n'existe 24 h après l'échéance.
- Journalisation à chaque relevé horaire (:02) pour le moteur actif **et** le moteur en observation. Évaluation à :35.
- Commande `python main.py performance`, et section « Résultats des décisions » du dashboard. Elles sont toujours libellées **« théoriques, prix observés, pas des ventes réelles »**.

### 1-F Score, qualité et probabilité séparés (v2)
- **Opportunité /100** : force du signal.
- **Qualité des données /100** : fraîcheur et couverture.
- **Probabilité** : « **non disponible** » tant que moins de **100** décisions comparables (même règle, même action, à 24 h) ont été évaluées. Au-delà, on affiche une **fréquence historique favorable** avec n et un intervalle de confiance à 95 % (Wilson), libellée « théorique ».
- Pour rester compatibles avec l'anti-spam, les signaux v2 ont encore une note /10. Elle est dérivée de opportunité × qualité, plafonnée à 4 pour SURVEILLANCE et AUCUNE ACTION, et n'est **pas affichée** en v2.

---

## 2. Effet mesuré (données démo)

**Avec 5 jours de données synthétiques** (le cas réel du bot aujourd'hui), au même instant :

| | v1 | v2 |
|---|---|---|
| ACHAT / ACHAT FORT | 1 | 1 (chute de -20 %, cible = moyenne 7 j) |
| VENTE / VENTE URGENTE | 7 | 1 (hausse de +35 %) |
| SURVEILLANCE | — | 6 (« habitude non validée ») |
| AUCUNE ACTION / HOLD | 4 | 4 |

Les 6 ventes de v1 dues au bruit deviennent de la surveillance expliquée.

Avec 35 jours démo (habitude « validée » par le learner), v2 suit l'habitude comme v1. **Limite connue** : la validation de l'habitude repose sur les propres statistiques du learner, mesurées sur l'échantillon d'apprentissage. Le journal permettra de la vérifier hors échantillon (étape 2).

Les chiffres de performance démo ne sont **pas** interprétables : les données démo sont générées à partir du même profil que le cerveau.

---

## 3. Base de données
- **Migration v2**, au premier démarrage, via `python main.py init` dans `start.sh` :
  1. **sauvegarde** `data/backups/market_history-AAAAMMJJ-HHMMSS.db`, avec contrôle d'intégrité. Si elle échoue, rien n'est migré ;
  2. dans **une transaction verrouillée** (`BEGIN IMMEDIATE`, car le bot et le dashboard démarrent en même temps) : les doublons sont **copiés** dans `price_snapshots_duplicates`, retirés de la table principale (le relevé le plus récent est conservé), puis l'index unique est créé ;
  3. `schema_version = 2`, avec une note : nombre de doublons archivés et chemin de la sauvegarde.
- Test de concurrence réalisé : 2 processus lancés en même temps sur 60 001 lignes, dont 1 doublon. Résultat : **une seule migration**, 60 000 lignes conservées, 1 doublon archivé, aucune erreur.
- **Ajouts uniquement** : `decision_log`, `decision_outcomes`, `price_snapshots_duplicates`, `schema_version`. Aucune table ni colonne supprimée.
- Volume du journal : environ 320 décisions par heure (2 moteurs), soit environ 230 000 lignes par mois, quelques dizaines de Mo par an.

## 4. Retour arrière
- **Moteur** : déjà sur v1 par défaut. Pour couper l'observation : `BRAIN_SHADOW=` dans `.env`.
- **Code et base** : `docker compose down`, puis copier la sauvegarde de `data/backups/` vers `data/market_history.db`, puis `git checkout <commit précédent>` et `./deploy.sh`.

## 5. Ce que l'étape 1 ne fait pas (volontairement)
- Les seuils de R4 (-15 % / +30 %) sont **inchangés** (seuils adaptatifs : étape 7 du plan).
- R1, R2, R3 et R5 restent inactives (pas de source légitime) et **non refondues**.
- Aucun ML, aucune nouvelle règle, pas de R6.
- Il n'existe toujours **aucune performance réelle mesurée** : le journal commence à se remplir au déploiement.

## 6. Proposition pour la suite (à valider)
1. **Déployer et laisser tourner 2 à 3 semaines** sans rien changer au cerveau, pour accumuler des décisions évaluées des deux moteurs.
2. Pendant ce temps, faire les chantiers qui ne touchent pas aux décisions :
   - base de connaissances légère (calendrier des promos, taxe et paliers, raretés : YAML sourcés) ;
   - tracker des fodders (après vérification de ce que futgenie permet) ;
   - supervision (« plus de prix depuis 2 h »).
3. Ensuite, **comparer v1 et v2 sur les résultats réels du journal**, et décider de la bascule `BRAIN_VERSION=v2`.

---

## Mise à jour du 01/11/2026 : bascule vers le moteur v2

**Données réelles du VPS après 2,4 jours** (17 675 relevés, 163 joueurs suivis, aucun doublon) :

| Décision | Horizon | n | Favorables | Variation médiane |
|---|---|---|---|---|
| v1 ACHAT | 24 h | 984 | **8 %** | −4,0 % |
| v1 VENTE | 24 h | 428 | 89 % | −7,9 % |
| v1 AUCUNE ACTION | 24 h | 1 954 | 100 % | −6,6 % |
| v2 SURVEILLANCE | 24 h | 157 | 99 % | −4,9 % |
| v2 AUCUNE ACTION | 24 h | 3 209 | 99 % (24 occasions manquées) | −6,1 % |

**Lecture des résultats :**
- Le marché était en baisse générale (début de saison, promo Ultimate Scream).
- La règle R4 de v1 (−15 % en 48 h → ACHAT) s'est déclenchée sur des chutes **générales**, et non propres aux joueurs. 92 % de ses achats auraient été perdants à 24 h, et elle a produit environ 210 alertes d'achat en 2,4 jours.
- v2 s'est abstenu, à juste titre dans 99 % des cas.

**Limites connues :**
- La période est courte et ne couvre qu'un seul régime de marché.
- Les observations ne sont pas indépendantes : un même joueur est compté à chaque relevé.
- v2 n'a encore **aucun achat évalué**.

**Décision (validée par le propriétaire) :**
- `BRAIN_VERSION=v2` (actif) et `BRAIN_SHADOW=v1` (observation).
- Retour arrière : inverser les deux valeurs dans `.env`, puis `docker compose up -d --force-recreate`.

**Suite prioritaire :** étape 7, R4 en force relative. Une chute n'est plus traitée comme une opportunité quand elle suit le mouvement général du marché (`market_change`) ; seul l'écart propre au joueur compte.

### Étape 7 (01/11/2026) : R4 en force relative, moteur v2 uniquement
- **ACHAT** seulement si la chute sur 48 h dépasse celle du marché suivi d'au moins 10 points (`R4_EXCESS_BUY`) **et** si elle s'est stabilisée, c'est-à-dire pas plus de −2 % sur les 3 dernières heures (`R4_STABLE_3H`).
- Sinon → **SURVEILLANCE**, avec la raison : « chute alignée sur le marché », « chute encore en cours » ou « marché inconnu ».
- **VENTE sur hausse** seulement si la hausse sur 24 h dépasse celle du marché d'au moins 15 points (`R4_EXCESS_SELL`).
- La force du signal repose sur l'**écart au marché**, plus sur la variation brute.
- v1 est inchangé (moteur de comparaison). L'effet sera mesuré dans le journal (v2 contre v1) sur les prochains jours.
