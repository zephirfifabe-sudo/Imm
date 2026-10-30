"""Fetcher robuste anti-bot : httpx -> Playwright (Chromium headless) -> FlareSolverr.

Stratégie :
1. httpx avec des en-têtes de vrai navigateur (rapide, peu coûteux).
2. Si la réponse ressemble à un challenge Cloudflare (403/503 + "Just a moment", "cf-chl"...),
   on ouvre la page dans Chromium headless (Playwright), on attend que le challenge JS se résolve,
   puis on RÉCUPÈRE LES COOKIES (cf_clearance) pour les réinjecter dans httpx -> les requêtes
   suivantes repassent par httpx (même User-Agent obligatoire, d'où l'UA partagé).
3. Si Playwright échoue aussi (challenge Turnstile interactif), et que FLARESOLVERR_URL est défini,
   on délègue à FlareSolverr (conteneur docker dédié).

IMPORTANT : les objets Playwright "sync" sont liés au thread qui les a créés.
-> Créer un Fetcher par job/thread et appeler close() à la fin (ou utiliser `with Fetcher() as f`).
"""
from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

import config
from utils.logger import get_logger

log = get_logger("fetcher")

CF_MARKERS = (
    "just a moment...", "cf-browser-verification", "cf-chl", "challenge-platform",
    "attention required! | cloudflare", "checking your browser", "cf_chl_opt", "enable javascript and cookies",
)


def page_title(html: str) -> str:
    """Titre de la page : 'Just a moment...' = challenge (passable), 'Attention Required' = IP bannie."""
    import re

    m = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
    return (m.group(1).strip() if m else (html or "")[:60].strip())[:60]


def playwright_proxy(url: str) -> dict:
    u = urlparse(url)
    out = {"server": f"{u.scheme}://{u.hostname}:{u.port}"}
    if u.username:
        out.update(username=u.username, password=u.password or "")
    return out


SESSION_MAX_AGE_S = 3 * 3600
BACKOFF_STEPS_S = [3600, 7200, 14400, 21600]  # 1h, 2h, 4h, puis 6h max


def SESSION_FILE():  # noqa: N802 (chemin dépendant de config.DATA_DIR, modifiable en test)
    config.ensure_dirs()
    return config.DATA_DIR / "cf_session.json"


def _backoff_file():
    config.ensure_dirs()
    return config.DATA_DIR / "cf_backoff.json"


def _read_backoff() -> dict:
    try:
        return json.loads(_backoff_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def blocked_until(host: str) -> float | None:
    b = _read_backoff().get(host)
    return b["until"] if b and b["until"] > time.time() else None


def register_block(host: str) -> float:
    data = _read_backoff()
    level = min(data.get(host, {}).get("level", -1) + 1, len(BACKOFF_STEPS_S) - 1)
    until = time.time() + BACKOFF_STEPS_S[level]
    data[host] = {"until": until, "level": level}
    _backoff_file().write_text(json.dumps(data), encoding="utf-8")
    log.warning("%s nous bloque : pause anti-blocage de %d h", host, BACKOFF_STEPS_S[level] // 3600)
    return until


def clear_block(host: str) -> None:
    data = _read_backoff()
    if host in data:
        del data[host]
        _backoff_file().write_text(json.dumps(data), encoding="utf-8")


class FetchError(RuntimeError):
    pass


@dataclass
class FetchResult:
    url: str
    status: int
    text: str
    via: str

    def json(self):
        return json.loads(self.text)


# Page d'erreur du navigateur (FlareSolverr la renvoie avec un statut 200)
BROWSER_ERROR_MARKERS = ("err_timed_out", "err_proxy", "err_tunnel", "err_connection", "this site can’t be reached",
                         "this site can't be reached", "err_name_not_resolved")


def looks_blocked(status: int, text: str) -> bool:
    full = (text or "").lower()
    low = full[:20000]
    if any(m in low for m in CF_MARKERS):
        return True
    if len(full) < 400_000 and any(m in full for m in BROWSER_ERROR_MARKERS) and "/players/" not in full:
        return True
    return status in (403, 429, 503) and ("cloudflare" in low or len(low) < 2000)


class Fetcher:
    def __init__(self, mode: str | None = None, min_delay: float | None = None, timeout: float = 25.0):
        self.mode = mode or config.FETCH_MODE
        self.min_delay = config.REQUEST_MIN_DELAY if min_delay is None else min_delay
        self.timeout = timeout
        self.headers = {
            "User-Agent": config.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Upgrade-Insecure-Requests": "1",
        }
        self.client = httpx.Client(headers=self.headers, follow_redirects=True, timeout=timeout,
                                   proxy=config.PROXY_URL or None)
        self.pw_failed_hosts: set[str] = set()  # Chromium bloqué -> ne plus perdre 30 s par page
        self._fs_cookies: list[dict] = []  # "laissez-passer" Cloudflare obtenu par FlareSolverr
        self._fs_ua: str | None = None
        self._cap_ctx = None
        self._last_hit: dict[str, float] = {}
        self._lock = threading.Lock()
        self._pw = None
        self._browser = None
        self._context = None
        self.blocked_hosts: set[str] = set()  # hosts où httpx est bloqué même avec cookies
        # Coupe-circuit : après 3 échecs complets d'affilée, le site est ignoré jusqu'à la fin du job
        self.host_failures: dict[str, int] = {}
        self.max_host_failures = 3
        self.ignore_backoff = False  # True pour les diagnostics manuels
        self._load_session()

    # ------------------------------------------------------------------ context manager
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:  # noqa: BLE001
            pass
        for obj in (self._cap_ctx, self._context, self._browser):
            try:
                if obj is not None:
                    obj.close()
            except Exception:  # noqa: BLE001
                pass
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:  # noqa: BLE001
                pass
        self._pw = self._browser = self._context = self._cap_ctx = None

    # ------------------------------------------------------------------ public API
    def get(self, url: str, expect: str = "html", retries: int = 2) -> FetchResult:
        host = urlparse(url).netloc
        until = blocked_until(host)
        if until and not self.ignore_backoff:
            raise FetchError(f"{host} en pause anti-blocage jusqu'à {time.strftime('%H:%M', time.localtime(until))}")
        if self.host_failures.get(host, 0) >= self.max_host_failures:
            raise FetchError(f"{host} ignoré (coupe-circuit : {self.max_host_failures} échecs d'affilée)")
        try:
            res = self._get(url, host, expect, retries)
        except FetchError:
            self.host_failures[host] = self.host_failures.get(host, 0) + 1
            if self.host_failures[host] >= self.max_host_failures and not self.ignore_backoff:
                register_block(host)  # le site nous bloque : pause de 1h, 2h, 4h puis 6h max
            raise
        self.host_failures[host] = 0
        clear_block(host)
        return res

    # ------------------------------------------------------------------ session Cloudflare persistante
    def _load_session(self) -> None:
        """Réutilise le laissez-passer Cloudflare d'un job précédent (repasser le challenge à chaque
        relevé est un signal de robot)."""
        try:
            data = json.loads(SESSION_FILE().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if time.time() - data.get("at", 0) > SESSION_MAX_AGE_S or not data.get("cookies"):
            return
        self._fs_cookies, self._fs_ua = data["cookies"], data.get("ua")
        for ck in self._fs_cookies:
            self.client.cookies.set(ck["name"], ck["value"], domain=ck.get("domain", ""))
        if self._fs_ua:
            self.client.headers["User-Agent"] = self._fs_ua

    def _save_session(self) -> None:
        try:
            SESSION_FILE().write_text(json.dumps({"at": time.time(), "cookies": self._fs_cookies, "ua": self._fs_ua}),
                                      encoding="utf-8")
        except OSError:
            pass

    def _get(self, url: str, host: str, expect: str, retries: int) -> FetchResult:
        self._throttle(host)
        errors: list[str] = []

        if self.mode != "playwright" and host not in self.blocked_hosts:
            for attempt in range(retries + 1):
                try:
                    r = self.client.get(url, headers=self._accept(expect))
                    if r.status_code == 404:
                        return FetchResult(url, 404, r.text, "httpx")
                    if not looks_blocked(r.status_code, r.text) and r.status_code < 400:
                        return FetchResult(url, r.status_code, r.text, "httpx")
                    errors.append(f"httpx {r.status_code} (bloqué={looks_blocked(r.status_code, r.text)})")
                    if looks_blocked(r.status_code, r.text):
                        break
                except httpx.HTTPError as e:
                    errors.append(f"httpx {type(e).__name__}: {e}")
                time.sleep(2 ** attempt + random.random())

        # FlareSolverr configuré : on l'essaie AVANT Chromium (bloqué par Cloudflare sur FUT.GG/FUTBIN,
        # il ferait perdre 30 s par job)
        if config.FLARESOLVERR_URL and self.mode == "auto":
            try:
                return self._flaresolverr_get(url, expect)
            except Exception as e:  # noqa: BLE001
                errors.append(f"flaresolverr {type(e).__name__}: {e}")
            raise FetchError(f"Impossible de récupérer {url} : " + " | ".join(errors))

        skip_pw = host in self.pw_failed_hosts and bool(config.FLARESOLVERR_URL)
        if self.mode in ("auto", "playwright") and not skip_pw:
            try:
                res = self._playwright_get(url, expect)
                if not looks_blocked(res.status, res.text):
                    return res
                self.pw_failed_hosts.add(host)
                errors.append(f"playwright toujours bloqué ({res.status}, page « {page_title(res.text)} »)")
            except Exception as e:  # noqa: BLE001
                errors.append(f"playwright {type(e).__name__}: {e}")

        if config.FLARESOLVERR_URL:
            try:
                return self._flaresolverr_get(url, expect)
            except Exception as e:  # noqa: BLE001
                errors.append(f"flaresolverr {type(e).__name__}: {e}")

        raise FetchError(f"Impossible de récupérer {url} : " + " | ".join(errors))

    def get_json(self, url: str, retries: int = 2):
        res = self.get(url, expect="json", retries=retries)
        if res.status == 404:
            return None
        txt = res.text.strip()
        if not txt.startswith(("{", "[")):
            # Chromium affiche le JSON dans un <pre>
            from bs4 import BeautifulSoup

            txt = BeautifulSoup(txt, "html.parser").get_text().strip()
        return json.loads(txt)

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _accept(expect: str) -> dict:
        if expect == "json":
            return {"Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest"}
        return {}

    def _throttle(self, host: str) -> None:
        with self._lock:
            wait = self._last_hit.get(host, 0) + self.min_delay + random.uniform(0, self.min_delay / 2) - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last_hit[host] = time.time()

    def _ensure_browser(self):
        if self._context is not None:
            return self._context
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        launch_kwargs = {
            "headless": True,
            "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"],
        }
        if config.PLAYWRIGHT_CHROMIUM_PATH:
            launch_kwargs["executable_path"] = config.PLAYWRIGHT_CHROMIUM_PATH
        if config.PROXY_URL:
            launch_kwargs["proxy"] = playwright_proxy(config.PROXY_URL)
        self._browser = self._pw.chromium.launch(**launch_kwargs)
        self._context = self._browser.new_context(
            user_agent=config.USER_AGENT, locale="fr-FR", timezone_id=config.TZ,
            viewport={"width": 1366, "height": 900},
        )
        # Masquer les traces d'automatisation les plus évidentes
        self._context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            "window.chrome={runtime:{}};"
            "Object.defineProperty(navigator,'languages',{get:()=>['fr-FR','fr','en-US','en']});"
            "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});"
        )
        log.info("Chromium headless démarré (fallback anti-bot)")
        return self._context

    def _playwright_get(self, url: str, expect: str, max_wait: float = 30.0) -> FetchResult:
        ctx = self._ensure_browser()
        page = ctx.new_page()
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=int(self.timeout * 1000) + 20000)
            status = resp.status if resp else 0
            deadline = time.time() + max_wait
            content = page.content()
            while looks_blocked(status, content) and time.time() < deadline:
                page.wait_for_timeout(1000)
                try:
                    content = page.content()
                except Exception:  # noqa: BLE001  (navigation en cours après challenge)
                    continue
                if not looks_blocked(200, content):
                    status = 200
                    break
            if expect == "html":
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:  # noqa: BLE001
                    pass
                content = page.content()
            else:
                content = page.evaluate("() => document.body ? document.body.innerText : ''") or content
            self._sync_cookies_to_httpx()
            if looks_blocked(status, content):
                log.warning("Playwright bloqué %s (status=%s, page « %s »)", url, status, page_title(content))
            else:
                log.info("Playwright OK %s (status=%s)", url, status)
            return FetchResult(url, status or 200, content, "playwright")
        finally:
            page.close()

    def _sync_cookies_to_httpx(self) -> None:
        if self._context is None:
            return
        for ck in self._context.cookies():
            self.client.cookies.set(ck["name"], ck["value"], domain=ck.get("domain", ""), path=ck.get("path", "/"))

    def flaresolverr_render(self, url: str, wait_s: int = 6) -> FetchResult:
        """Page rendue par le navigateur de FlareSolverr, après `wait_s` s (contenu chargé en JavaScript)."""
        self._throttle(urlparse(url).netloc)
        return self._flaresolverr_get(url, "html", wait_s=wait_s)

    def _flaresolverr_get(self, url: str, expect: str, wait_s: int = 0) -> FetchResult:
        payload = {"cmd": "request.get", "url": url, "maxTimeout": 60000}
        if wait_s:
            payload["waitInSeconds"] = wait_s  # FlareSolverr >= 3.3 : attend le contenu dynamique
        if config.PROXY_URL:
            payload["proxy"] = flaresolverr_proxy(config.PROXY_URL)
        r = httpx.post(config.FLARESOLVERR_URL, json=payload, timeout=90 + wait_s)
        try:
            body = r.json()
        except ValueError:
            r.raise_for_status()
            raise
        # FlareSolverr renvoie HTTP 500 + {"status": "error", "message": "..."} : on garde la raison
        if body.get("status") != "ok":
            raise FetchError(f"FlareSolverr : {body.get('message', '?')[:150]}")
        sol = body.get("solution") or {}
        if sol.get("cookies"):
            self._fs_cookies, self._fs_ua = sol["cookies"], sol.get("userAgent")
            self._cap_ctx = None  # le prochain capture_api repartira avec les nouveaux cookies
            self._save_session()
        for ck in sol.get("cookies", []):
            self.client.cookies.set(ck["name"], ck["value"], domain=ck.get("domain", ""))
        # cf_clearance est lié au User-Agent du navigateur qui a passé le challenge
        if sol.get("userAgent"):
            self.client.headers["User-Agent"] = sol["userAgent"]
        text = sol.get("response", "")
        if looks_blocked(int(sol.get("status", 200)), text):
            raise FetchError(f"FlareSolverr bloqué (page « {page_title(text)} »)")
        if expect == "json" and not text.strip().startswith(("{", "[")):
            from bs4 import BeautifulSoup

            text = BeautifulSoup(text, "html.parser").get_text()
        log.info("FlareSolverr OK %s", url)
        return FetchResult(url, int(sol.get("status", 200)), text, "flaresolverr")

    # ------------------------------------------------------------------ capture des API (prix)
    def _ensure_capture_context(self):
        """Chromium avec le User-Agent + cookies de FlareSolverr : il passe Cloudflare comme un visiteur."""
        if self._cap_ctx is not None:
            return self._cap_ctx
        self._ensure_browser()
        ctx = self._browser.new_context(user_agent=self._fs_ua or config.USER_AGENT, locale="fr-FR",
                                        timezone_id=config.TZ, viewport={"width": 1366, "height": 900})
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        if self._fs_cookies:
            ctx.add_cookies(pw_cookies(self._fs_cookies))
        self._cap_ctx = ctx
        return ctx

    def capture_api(self, page_url: str, stop_on: str | None = None, wait_s: float = 15.0) -> dict:
        """Ouvre la page dans Chromium et récupère les réponses JSON des appels /api/ faits par le site.

        Sert quand une API (ex: prix FUT.GG) refuse les requêtes directes mais accepte celles
        de sa propre page, chargée par un vrai navigateur.
        """
        if not self._fs_cookies and config.FLARESOLVERR_URL:
            self._flaresolverr_get(page_url, "html")
        self._throttle(urlparse(page_url).netloc)
        page = self._ensure_capture_context().new_page()
        responses = []
        page.on("response", lambda r: responses.append(r) if "/api/" in r.url else None)
        try:
            resp = page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
            deadline = time.time() + wait_s
            while time.time() < deadline:
                if stop_on and any(stop_on in r.url for r in responses):
                    page.wait_for_timeout(500)
                    break
                page.wait_for_timeout(500)
            html = page.content()
            status = resp.status if resp else 0
            api = {}
            for r in responses:
                try:
                    body = r.json()
                except Exception:  # noqa: BLE001
                    body = None
                api[r.url] = (r.status, body)
        finally:
            page.close()
        return {"status": status, "blocked": looks_blocked(status, html), "title": page_title(html), "api": api}


def flaresolverr_proxy(url: str) -> dict:
    """FlareSolverr veut l'identifiant et le mot de passe à part : {"url", "username", "password"}."""
    u = urlparse(url)
    out = {"url": f"{u.scheme}://{u.hostname}:{u.port}"}
    if u.username:
        out.update(username=u.username, password=u.password or "")
    return out


def pw_cookies(fs_cookies: list[dict]) -> list[dict]:
    """Cookies FlareSolverr (Selenium) -> format Playwright."""
    out = []
    for c in fs_cookies:
        ck = {"name": c["name"], "value": c["value"], "domain": c.get("domain", ""), "path": c.get("path", "/")}
        if c.get("expiry") or c.get("expires"):
            try:
                ck["expires"] = float(c.get("expiry") or c.get("expires"))
            except (TypeError, ValueError):
                pass
        ck["httpOnly"] = bool(c.get("httpOnly"))
        ck["secure"] = bool(c.get("secure"))
        if str(c.get("sameSite", "")).capitalize() in ("Strict", "Lax", "None"):
            ck["sameSite"] = str(c["sameSite"]).capitalize()
        out.append(ck)
    return out
