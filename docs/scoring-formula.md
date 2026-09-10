# Formule de scoring — PréVisite

Le score n'est **jamais** calculé ou deviné par un LLM. Il est calculé par des
règles explicites, déterministes et testées, dans
`packages/shared/src/scoring/scoring-engine.ts`. Le LLM de synthèse
(`apps/backend/src/services/synthesis`) reçoit ce résultat déjà calculé et se
contente de l'expliquer en français — il ne peut ni le recalculer ni le
contredire (voir le prompt système dédié).

## Formule

```
score = 10 + pointsPrix + pointsEnergie + pointsTravaux     (borné à [0, 10])
```

| Verdict          | Condition       |
| ---------------- | --------------- |
| Bonne affaire    | score ≥ 7       |
| À creuser        | 4.5 ≤ score < 7 |
| À éviter         | score < 4.5     |

## Facteur 1 — Écart de prix vs marché local

- Source : prix moyen au m² par commune (Statbel), voir
  `packages/shared/src/market/statbel-mock-data.ts`.
- `askingPricePerM2 = prixDemandé / surfaceHabitable`
- `deviationPercent = (askingPricePerM2 - marketPricePerM2) / marketPricePerM2 × 100`
- `pointsPrix = clamp(-deviationPercent / 10, -3, +3)`
  → chaque tranche de 10% d'écart au marché vaut 1 point, plafonné à ±3 points.
- Si la surface habitable n'est pas renseignée, `pointsPrix = 0` (on ne
  pénalise pas une donnée absente).
- Si la commune n'est pas dans le jeu de données local, on retombe sur une
  moyenne nationale de repli (`STATBEL_NATIONAL_FALLBACK`).

## Facteur 2 — Impact PEB/DPE

Grille de pondération fixe par classe énergétique
(`packages/shared/src/scoring/energy-weights.ts`), échelle A→G commune au PEB
belge et au DPE français pour ce MVP :

| Classe | Pénalité (pts) | Rénovation énergétique estimée |
| ------ | --------------- | ------------------------------- |
| A / B  | 0               | 0 €                              |
| C      | -0.5            | 0 – 3 000 €                      |
| D      | -1              | 3 000 – 8 000 €                  |
| E      | -2              | 8 000 – 15 000 €                 |
| F      | -3.5            | 15 000 – 30 000 €                |
| G      | -5              | 30 000 – 50 000 €                |

Si la classe n'est pas renseignée, `pointsEnergie = 0`.

Ces montants sont des ordres de grandeur pour une maison de taille moyenne en
Wallonie (itération à venir : pondérer par surface réelle).

## Facteur 3 — Étendue des travaux détectée en photo

Grille fixe (`packages/shared/src/scoring/work-weights.ts`), appliquée au
champ `estimation_travaux` renvoyé par l'IA vision :

| Étendue   | Pénalité (pts) |
| --------- | --------------- |
| Léger     | -0.5            |
| Modéré    | -2              |
| Important | -4              |

## Pourquoi ces bornes ?

- Le facteur prix est plafonné à ±3 points pour éviter qu'un écart de prix
  extrême (donnée aberrante ou commune mal renseignée) n'écrase à lui seul
  tout le reste de l'analyse.
- Le facteur énergie va jusqu'à -5 points parce qu'une classe G implique un
  budget de rénovation qui peut représenter une part significative du prix
  d'achat — c'est l'un des postes de coût les plus prévisibles pour un
  acheteur.
- Le facteur travaux est plafonné à -4 points : l'analyse photo estime
  l'état général visible, pas un diagnostic — elle doit peser dans le score
  sans jamais, à elle seule, transformer un bien par ailleurs très
  intéressant en "à éviter".

## Modifier la formule

Toute évolution de ces règles doit rester dans
`packages/shared/src/scoring/` (fonctions pures, testées dans
`__tests__/scoring-engine.test.ts`) — jamais dans le prompt du LLM de
synthèse.
