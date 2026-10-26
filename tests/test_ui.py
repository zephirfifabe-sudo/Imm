from fastapi.testclient import TestClient

from fccoach.core.state import SharedState
from fccoach.ui.server import create_app


def test_dashboard_and_state():
    st = SharedState()
    st.update("ocr", {"clock": "12:34", "score": [1, 0]})
    client = TestClient(create_app(st))
    assert "Adversaire" in client.get("/").text
    data = client.get("/api/state").json()
    assert data["ocr"]["clock"] == "12:34"
