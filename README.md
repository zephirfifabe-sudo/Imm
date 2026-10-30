# FC27 SNIPER ANALYST V4 FINAL

Analyseur de marché FUT (EA SPORTS FC 27) **auto-apprenant**. Il n'achète rien (zéro risque de ban) :
il observe le marché 24/7, apprend ses habitudes et t'envoie des alertes **ACHAT / VENTE / HOLD**
sur Telegram/Discord, avec un dashboard consultable depuis ton téléphone.

## 🚀 Lancer sur le VPS (Hetzner Ubuntu) — 3 commandes

```bash
git clone https://github.com/zephirfifabe-sudo/imm.git sniper && cd sniper
cp .env.example .env && nano .env        # TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, DASHBOARD_PASSWORD...
./deploy.sh                              # installe Docker si besoin, build, lance (restart: always)
```

Dashboard : `http://IP_DU_VPS:8000` · Logs : `tail -f data/logs/bot.log` · Mise à jour : `./deploy.sh`

Puis, une fois, pour donner de la mémoire au bot dès le 1er jour et vérifier Telegram :
```bash
docker compose exec sniper python main.py backfill && docker compose exec sniper python main.py learn
docker compose exec sniper python main.py test-alert
```

> ⚠️ Le dashboard est exposé sur Internet : remplis `DASHBOARD_USER` / `DASHBOARD_PASSWORD` dans `.env`
> (authentification HTTP Basic) et ouvre le port 8000 dans le pare-feu Hetzner seulement si besoin.

### Telegram en 2 minutes
1. Sur Telegram, écris à **@BotFather** → `/newbot` → copie le token dans `TELEGRAM_TOKEN`.
2. Envoie un message à ton bot, puis ouvre `https://api.telegram.org/bot<TOKEN>/getUpdates` :
   le champ `"chat":{"id": ...}` est ton `TELEGRAM_CHAT_ID`.
3. Discord (optionnel) : Salon → Intégrations → Webhooks → copie l'URL dans `DISCORD_WEBHOOK_URL`.

## 🗓️ Ce que fait le bot (heure de Paris)

| Quand | Quoi |
|---|---|
| Toutes les heures (:02) | Prix des 150 joueurs → mémoire + alerte instantanée si crash >15 % ou règle R4 |
| 08:00 | Nouvelle watchlist : joueurs populaires/meta entre 20k et 400k |
| Toutes les 20 min | Leaks (alerte immédiate si un joueur de ta watchlist est cité) |
| :20 (toutes les 15 min de 18h à 21h) | Nouveaux SBC (R2) et Evos (R3) |
| **18:45** | Rapport PRÉ-19H : leaks + ventes à sécuriser |
| 18:55 → 20:30, toutes les 3 min | Nouvelles cartes → analyse d'impact immédiate (R1 concurrence, R5 saturation) |
| **19:15** | Rapport POST-19H |
| **23:00** | Récap : humeur du marché, top achats/ventes, habitudes apprises |
| Lundi 05:00 | `learn_patterns()` : ré-apprentissage sur 30 jours |

Anti-spam : confiance ≥ 7/10, max 8 alertes par envoi, pas deux fois la même alerte sur un joueur en 6h
(réglable dans `.env`).

## 🧠 Comment le cerveau décide

1. **Instantané** (R1-R5) → score entre -1 (vendre) et +1 (acheter).
2. **Habitude** : prix ramené à sa moyenne 7 jours, comparé au profil hebdo appris (168 heures),
   projection de la hausse possible (96h) et de la baisse possible (48h).
3. Fusion 65 % instantané / 35 % habitude. L'habitude seule plafonne à `ACHAT`/`VENTE` et 8/10.
4. **Taxe EA 5 %** : un ACHAT n'est conseillé que si le rebond attendu laisse ≥ 4 % net après taxe
   (`MIN_NET_MARGIN`). L'alerte affiche le bénéfice net par carte.

Règles : R1 nouvelle carte similaire >85 % (poste ±1, ligue/nation, note ±2) → VENTE · R2 SBC qui
demande une ligue / des notes → ACHAT fodders · R3 Evo qui rend meta des joueurs <20k → ACHAT MASSIF ·
R4 -15 %/48h sans concurrent → ACHAT, +30 %/24h → VENTE · R5 ≥3 cartes du même poste en 7 jours → poste baissier.

## 🧰 Commandes

| Commande | Rôle |
|---|---|
| `python main.py` | Bot H24 (planificateur complet + alertes) |
| `python main.py watchlist` / `snapshot` | Watchlist du jour / prix maintenant |
| `python main.py backfill` | Importe l'historique de prix FUT.GG (mémoire dès le 1er jour) |
| `python main.py learn` | Auto-apprentissage → `data/market_rules.json` |
| `python main.py analyze [--all]` | Scan de la watchlist, alertes formatées dans le terminal |
| `python main.py backtest --days 14` | Les signaux auraient-ils rapporté ? (taxe incluse, sans tricher sur le futur) |
| `python main.py latest` / `sbc` / `evos` / `leaks` | Chaque source à la main |
| `python main.py test-alert` | Alerte de test Telegram/Discord |
| `python main.py demo-seed` / `demo-reset` | 35 jours de données synthétiques pour tester sans réseau |
| `pytest -q` | Tests |

En local sans Docker : `pip install -r requirements.txt && playwright install --with-deps chromium`.

## 🏗️ Architecture

```
main.py                 CLI + `run` (bot H24)
config.py               variables d'env + seuils
start.sh                bot + dashboard dans le conteneur
database/db.py          SQLite data/market_history.db
scrapers/
  base.py               anti-bot : httpx → Chromium headless → FlareSolverr, coupe-circuit par site
  parsing.py            extraction générique (JSON embarqué + liens /players/...)
  futgg.py / futbin.py  prix (FUT.GG prioritaire, FUTBIN en secours)
  price_provider.py     bascule auto + snapshot horaire
  backfill.py           import de l'historique
  watchlist.py, latest_players.py, sbc.py, evolutions.py, requirements_parser.py, leak_watcher.py
core/
  analyzer.py           5 règles + fusion avec l'habitude + taxe
  pattern_detector.py   profil hebdo, crash dimanche, Rivals, remontée
  learner.py            learn_patterns() → market_rules.json
  backtest.py           rejoue le passé
  jobs.py               planificateur
  signals.py            format des alertes
alerts/                 telegram.py, discord.py, notifier.py (anti-spam + rapports), charts.py
dashboard/              FastAPI + index.html (Tailwind compilé + Chart.js embarqués, aucun CDN)
```

## 🌐 Sources et anti-bot

- **FUT.GG** : endpoints JSON internes puis HTML. Si le site change ses URL, surcharge-les dans `.env`
  (`FUTGG_POPULAR_URL`, `FUTGG_LATEST_URL`, `FUTGG_EVOS_URL`, `FUTGG_SBC_URL`).
- **Cloudflare** : challenge résolu par Chromium headless, puis cookies réutilisés par httpx.
  Si un captcha interactif bloque même Chromium :
  `docker compose --profile flaresolverr up -d` + `FLARESOLVERR_URL=http://flaresolverr:8191/v1`.
- **FUTBIN** : secours automatique quand FUT.GG échoue.
- **Leaks** : aperçu public `https://t.me/s/<canal>` (sans compte). Nitter = plan B.

## Dashboard : modifier le style

Le style est dans `dashboard/static/style.css` (CSS simple, aucune compilation). Les couleurs sont regroupées en variables en haut du fichier (`:root`).
