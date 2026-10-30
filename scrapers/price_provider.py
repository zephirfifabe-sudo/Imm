"""Prix avec bascule automatique FUT.GG -> FUTBIN + logger horaire (la MÉMOIRE)."""
from __future__ import annotations

import config
from database import db
from scrapers.base import FetchError, Fetcher
from scrapers.futbin import FutbinScraper
from scrapers.futgg import FutGGScraper
from utils.helpers import utcnow
from utils.logger import get_logger

log = get_logger("prices")


class PriceProvider:
    def __init__(self, fetcher: Fetcher):
        self.futgg = FutGGScraper(fetcher)
        self.futbin = FutbinScraper(fetcher)
        self.futgg_failures = 0

    def get_price(self, player: dict) -> dict | None:
        # Si FUT.GG a échoué 5 fois d'affilée pendant ce run, on passe directement à FUTBIN
        if self.futgg_failures < 5:
            try:
                res = self.futgg.player_prices(player["player_id"], player.get("url"))
                if res:
                    self.futgg_failures = 0
                    return res
            except FetchError as e:
                log.warning("FUT.GG KO pour %s : %s", player.get("name"), e)
            self.futgg_failures += 1
        try:
            return self.futbin.player_prices(player)
        except FetchError as e:
            log.warning("FUTBIN KO pour %s : %s", player.get("name"), e)
        return None


def snapshot_watchlist(players: list[dict], fetcher: Fetcher | None = None) -> dict:
    """Enregistre le prix actuel de chaque joueur de la watchlist (job horaire 24/7)."""
    if config.PRICE_SOURCE == "futgenie":
        return _snapshot_futgenie(players)
    own = fetcher is None
    fetcher = fetcher or Fetcher()
    provider = PriceProvider(fetcher)
    ts = utcnow().replace(minute=0, second=0, microsecond=0)  # aligné à l'heure -> séries propres
    ok, ko = 0, []
    try:
        # 1) prix par tranches (une passe pour toute la watchlist) ; 2) méthode par joueur seulement
        #    si les tranches n'ont rien donné (sinon chaque joueur manquant coûterait ~10 s pour rien)
        from scrapers.price_buckets import bucket_prices

        buckets = bucket_prices(fetcher, wanted={str(p["player_id"]) for p in players})
        for p in players:
            b = buckets.get(str(p["player_id"]))
            if b:
                res = {"price": b["price"], "min_24h": None, "max_24h": None, "volume": None,
                       "history": [], "source": "futgg-tranches"}
            elif buckets:
                res = None
            else:
                res = provider.get_price(p)
            if not res or not res.get("price"):
                ko.append(p.get("name"))
                continue
            with db.get_conn() as c:
                db.insert_snapshot(p["player_id"], res["price"], ts, res.get("min_24h"), res.get("max_24h"),
                                   res.get("volume"), res.get("source", "?"), conn=c)
                if res.get("history"):
                    db.insert_history(p["player_id"], res["history"], conn=c)
            ok += 1
    finally:
        if own:
            fetcher.close()
    summary = {"timestamp": ts.isoformat(), "ok": ok, "failed": len(ko), "failed_names": ko[:20]}
    db.set_status("last_snapshot", summary)
    log.info("Snapshot horaire : %d OK / %d KO", ok, len(ko))
    return summary


def _snapshot_futgenie(players: list[dict]) -> dict:
    """Relevé horaire depuis futgenie : prix exacts lus dans les listes (fiche en secours)."""
    from scrapers.futgenie import FutGenie
    from scrapers.price_buckets import parse_bands

    ts = utcnow().replace(minute=0, second=0, microsecond=0)
    fg = FutGenie()
    try:
        prices = fg.current_prices(players, parse_bands(config.WATCHLIST_BANDS))
        fg.fill_missing(players, limit=20)  # rattrapage progressif des fiches manquantes
    finally:
        fg.close()
    ok, ko = 0, []
    with db.get_conn() as c:
        for p in players:
            price = prices.get(str(p["player_id"]))
            if not price:
                ko.append(p.get("name"))
                continue
            db.insert_snapshot(p["player_id"], price, ts, source="futgenie", conn=c,
                               trend_7d=getattr(fg, "trends", {}).get(str(p["player_id"])))
            ok += 1
    summary = {"timestamp": ts.isoformat(), "ok": ok, "failed": len(ko), "failed_names": ko[:20], "source": "futgenie"}
    db.set_status("last_snapshot", summary)
    log.info("Snapshot horaire futgenie : %d OK / %d KO", ok, len(ko))
    return summary
