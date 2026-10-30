# FC27 SNIPER ANALYST V4 FINAL

Analyseur de marché FUT (EA SPORTS FC 27) **auto-apprenant**. Il n'achète rien (zéro risque de ban) :
il observe le marché 24/7, apprend ses habitudes et envoie des alertes **ACHAT / VENTE / HOLD**.

> État : **Étapes 1 + 2 livrées** (BDD, scrapers, logger horaire, cerveau 5 règles, auto-apprentissage).
> Étapes 3 (Telegram + scheduler complet), 4 (dashboard) et 5 (Docker/VPS) à suivre.

## Démarrage rapide (local)

```bash
pip install -r requirements.txt && playwright install --with-deps chromium
python main.py demo-seed && python main.py learn && python main.py analyze   # test sans réseau
python main.py watchlist && python main.py logger                           # vraies données, H24
```

## Commandes

| Commande | Rôle |
|---|---|
| `python main.py watchlist` | Scrape les joueurs populaires FUT.GG, filtre 20k-400k, garde 150 → `data/watchlist.json` |
| `python main.py snapshot` | 1 prix par joueur → `price_snapshots` (la MÉMOIRE) |
| `python main.py logger` | Snapshot toutes les heures, 24/7 |
| `python main.py latest` | Détecte les nouvelles cartes → analyse R1 + R5 |
| `python main.py sbc` / `evos` / `leaks` | Sources R2 / R3 / leaks |
| `python main.py learn` | `learn_patterns()` sur 30 jours → `data/market_rules.json` |
| `python main.py analyze [--all]` | Scan complet de la watchlist, alertes formatées |
| `python main.py demo-seed` / `demo-reset` | 35 jours de données synthétiques (marquées `demo`) |
| `pytest -q` | Tests (parsing, cerveau, fallback Cloudflare réel via Chromium) |

## Architecture

```
config.py               variables d'env + seuils
main.py                 CLI (étape 3 : scheduler complet)
database/db.py          SQLite market_history.db (players, price_snapshots, market_events, ...)
scrapers/
  base.py               Fetcher anti-bot : httpx → Playwright Chromium → FlareSolverr
  parsing.py            extraction générique (JSON embarqué + liens /players/...)
  futgg.py / futbin.py  prix (FUT.GG prioritaire, FUTBIN en secours)
  price_provider.py     bascule auto + logger horaire
  watchlist.py          watchlist quotidienne
  latest_players.py     nouvelles cartes (fenêtre 19h)
  sbc.py / evolutions.py / requirements_parser.py
  leak_watcher.py       Telegram t.me/s/<canal> (plan A), Nitter RSS (plan B)
core/
  analyzer.py           5 règles + fusion avec l'habitude
  pattern_detector.py   profil hebdo 168h, crash dimanche, Rivals, remontée
  learner.py            learn_patterns() → market_rules.json
  signals.py            format de l'alerte
  market_rules.json     règles par défaut (connaissance experte) avant apprentissage
alerts/ dashboard/      étapes 3 et 4
```

## Comment le cerveau décide

1. **Instantané** (R1-R5) → score entre -1 (vendre) et +1 (acheter).
2. **Habitude** : le prix est ramené à sa moyenne 7 jours ; on compare l'heure actuelle au profil hebdo
   appris (168 heures) et on projette la hausse possible (96h) et la baisse possible (48h).
3. Fusion 65 % instantané / 35 % habitude. La confiance monte quand les deux vont dans le même sens.
   Sans déclencheur instantané, l'habitude seule plafonne à `ACHAT`/`VENTE` et 8/10.

## Sources et anti-bot

- **FUT.GG** : endpoints JSON internes (`/api/fut/player-prices/{année}/{id}/`, `/player-item-definitions/`),
  puis HTML de la page joueur. Les URL de listes sont surchargeables via `.env`
  (`FUTGG_POPULAR_URL`, `FUTGG_LATEST_URL`, `FUTGG_EVOS_URL`, `FUTGG_SBC_URL`).
- **Cloudflare** : si httpx reçoit un challenge, Chromium headless le résout, puis ses cookies
  (`cf_clearance`) sont réinjectés dans httpx. Si un captcha Turnstile interactif bloque même Chromium :
  définir `FLARESOLVERR_URL` (conteneur FlareSolverr, ajouté à l'étape 5).
- **FUTBIN** : utilisé seulement si FUT.GG échoue ; l'ID FUTBIN est trouvé par recherche et mis en cache.
- **Leaks** : l'aperçu public `https://t.me/s/<canal>` ne demande ni compte ni clé API.
  Nitter n'est qu'un plan B, car ses instances tombent souvent.
