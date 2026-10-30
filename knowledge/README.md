# Base de connaissances Ultimate Team

C'est ce que le bot « sait » du jeu avant même d'avoir analysé le marché. Il y a deux couches.

1. **La théorie** : les fichiers `*.yaml` de ce dossier, écrits à la main et sourcés.
   - `01_marche.yaml` : taxe, durées d'annonce, paliers, fourchettes de prix, accès, interdits, offre et demande.
   - `02_calendrier.yaml` : rythme de la semaine (contenu à 19h, TOTW, Rivals, Squad Battles, Champions) et **événements datés** (promos, Black Friday, TOTY…).
   - `03_cartes_sbc_evos.yaml` : SBC à points (Item Score), Évolutions, PlayStyles, nouveautés FC 27, ce qui fait la valeur d'une carte.
   - `04_strategies.yaml` : comportements du marché décrits par la communauté. **Ce sont des hypothèses**, et la plupart sont testées automatiquement.
2. **Ce que le bot a observé** : `data/knowledge_observed.json`.
   - Chaque lundi à 05h20, le bot confronte chaque hypothèse testable aux prix qu'il a relevés.
   - Il rend un verdict : *confirmée*, *contredite*, *mitigée* ou *données insuffisantes*.
   - Il calcule aussi son propre profil de prix par jour de la semaine.

## Règles de qualité
Chaque connaissance a obligatoirement :
- une **source** (URL), sauf pour le `consensus_historique`, qui doit alors être expliqué dans `note` ;
- une date de vérification, une version du jeu et une **fiabilité de 1 à 5** ;
- un **statut** :

| Statut | Signification |
|---|---|
| `confirme` | Source officielle EA ou fait établi. Exige une fiabilité ≥ 4 |
| `probable` | Plusieurs sources concordantes, pas de confirmation officielle |
| `hypothese` | Avis ou méthode de la communauté. **Jamais présenté comme un fait** |
| `a_verifier` | Sources contradictoires, ou règle d'une édition précédente pas encore vérifiée pour FC 27 |
| `obsolete` | N'est plus vrai (changement d'EA). L'entrée est gardée pour l'historique |

**Ce qui est interdit :**
- inventer un chiffre ;
- mélanger l'officiel et l'hypothèse ;
- réutiliser une règle d'une ancienne édition sans la marquer `a_verifier`.

La base est **en lecture seule pour le cerveau**. Elle explique et donne du contexte (calendrier, consignes, alertes), mais **elle ne change aucune décision**. Une hypothèse ne pourra peser dans les décisions qu'une fois confirmée par les données **et** validée par un humain.

## Mettre à jour (depuis GitHub sur téléphone)
1. Ouvre le fichier `.yaml` sur GitHub, puis touche le crayon ✏️.
2. Modifie ou ajoute une entrée, en copiant une entrée existante comme modèle.
3. Si EA confirme une date de promo, change `statut: a_verifier` en `probable` ou `confirme`, et remplace la source par le lien officiel.
4. Enregistre (*Commit changes*), puis fais la mise à jour habituelle sur le VPS.
5. Vérifie le format :
   ```
   cd /root/sniper && docker compose exec bot python main.py knowledge
   ```
   La dernière ligne doit afficher « format OK ».
6. Pour voir la théorie confrontée aux données à tout moment :
   ```
   docker compose exec bot python main.py knowledge-verify
   ```
