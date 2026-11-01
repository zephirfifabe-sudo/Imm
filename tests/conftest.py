import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    """Chaque test a sa propre BDD / dossier data."""
    import config
    from database import db

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "market_history.db")
    monkeypatch.setattr(config, "WATCHLIST_PATH", tmp_path / "watchlist.json")
    monkeypatch.setattr(config, "RULES_PATH", tmp_path / "market_rules.json")
    # les tests historiques décrivent le moteur v1 ; les tests v2 passent version="v2" explicitement
    monkeypatch.setattr(config, "BRAIN_VERSION", "v1")
    monkeypatch.setattr(config, "BRAIN_SHADOW", "v2")
    db.init_db()
    yield tmp_path


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


os.environ.setdefault("REQUEST_MIN_DELAY", "0")
