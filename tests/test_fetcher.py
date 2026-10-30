"""Test réel du fallback anti-bot : un serveur local imite un challenge Cloudflare
(403 + "Just a moment..." puis JS qui pose un cookie et recharge). httpx échoue,
Chromium headless résout, et les cookies sont réinjectés dans httpx."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scrapers.base import Fetcher, looks_blocked

CHALLENGE = b"""<html><head><title>Just a moment...</title></head><body>
<div id="challenge-platform">Checking your browser</div>
<script>setTimeout(function(){document.cookie='cf_clearance=ok; path=/'; location.reload();}, 800);</script>
</body></html>"""
REAL = b"""<html><body><a href="/players/1-test-player/27-1/"><span>85</span><span>ST</span><span>50K</span></a></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        ok = "cf_clearance=ok" in (self.headers.get("Cookie") or "")
        body = REAL if ok else CHALLENGE
        if ok and self.path.startswith("/api/"):
            body = b'{"data": {"currentPrice": {"price": 67500}}}'
        elif ok and self.path == "/page-with-api":
            body = b"<html><body><script>fetch('/api/fut/player-prices/27/1/')</script></body></html>"
        self.send_response(200 if ok else 403)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_looks_blocked():
    assert looks_blocked(403, CHALLENGE.decode())
    assert not looks_blocked(200, REAL.decode())


def test_cloudflare_fallback_to_playwright(server):
    pytest.importorskip("playwright")
    with Fetcher(mode="auto", min_delay=0) as f:
        try:
            res = f.get(server + "/players/", retries=0)
        except Exception as e:  # noqa: BLE001
            if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
                pytest.skip("Chromium non installé (définir PLAYWRIGHT_CHROMIUM_PATH)")
            raise
        assert res.via == "playwright"
        assert "test-player" in res.text
        # les cookies récupérés par le navigateur permettent à httpx de passer ensuite
        res2 = f.get(server + "/players/?page=2", retries=0)
        assert res2.via == "httpx" and "test-player" in res2.text


def test_circuit_breaker():
    from scrapers.base import FetchError

    with Fetcher(mode="httpx", min_delay=0) as f:
        for _ in range(3):
            with pytest.raises(FetchError):
                f.get("http://127.0.0.1:9/x", retries=0)
        with pytest.raises(FetchError, match="pause anti-blocage"):
            f.get("http://127.0.0.1:9/y", retries=0)
    # la pause survit au job suivant (nouveau Fetcher) : on ne martèle pas un site qui nous bloque
    with Fetcher(mode="httpx", min_delay=0) as f2:
        with pytest.raises(FetchError, match="pause anti-blocage"):
            f2.get("http://127.0.0.1:9/z", retries=0)


def test_backoff_levels_and_session(tmp_data):
    import json
    import time

    from scrapers import base

    t1 = base.register_block("x.test")
    t2 = base.register_block("x.test")
    assert 3500 < t1 - time.time() < 3700 and 7100 < t2 - time.time() < 7300  # 1h puis 2h
    base.clear_block("x.test")
    assert base.blocked_until("x.test") is None
    base.SESSION_FILE().write_text(json.dumps({"at": time.time(), "ua": "UA-FS",
                                                "cookies": [{"name": "cf_clearance", "value": "v", "domain": ".fut.gg"}]}))
    with Fetcher(mode="httpx", min_delay=0) as f:
        assert f.client.headers["User-Agent"] == "UA-FS" and f._fs_cookies


def test_proxy_and_title_helpers():
    from scrapers.base import page_title, playwright_proxy

    assert playwright_proxy("http://u:p@1.2.3.4:8080") == {"server": "http://1.2.3.4:8080", "username": "u", "password": "p"}
    assert playwright_proxy("http://1.2.3.4:8080") == {"server": "http://1.2.3.4:8080"}
    assert page_title("<html><title>Just a moment...</title></html>") == "Just a moment..."


def test_capture_api_intercepts_site_calls(server):
    """La page appelle elle-même une API : Chromium récupère la réponse JSON au passage."""
    pytest.importorskip("playwright")
    import config

    with Fetcher(mode="auto", min_delay=0) as f:
        f._fs_cookies = [{"name": "cf_clearance", "value": "ok", "domain": "127.0.0.1", "path": "/"}]
        try:
            cap = f.capture_api(server + "/page-with-api", stop_on="player-prices", wait_s=5)
        except Exception as e:  # noqa: BLE001
            if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
                pytest.skip("Chromium non installé")
            raise
        hits = [(st, body) for u, (st, body) in cap["api"].items() if "player-prices" in u]
        assert hits and hits[0][0] == 200 and hits[0][1]["data"]["currentPrice"]["price"] == 67500


def test_flaresolverr_proxy_format():
    from scrapers.base import flaresolverr_proxy

    assert flaresolverr_proxy("http://user_1:pw@109.0.0.9:50100") == {
        "url": "http://109.0.0.9:50100", "username": "user_1", "password": "pw"}


def test_browser_error_page_is_failure():
    page = "<html><title>www.fut.gg</title><body>This site can’t be reached ... ERR_TIMED_OUT Checking the proxy</body></html>"
    assert looks_blocked(200, page)
