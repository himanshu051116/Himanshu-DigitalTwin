"""Per-browser replay isolation: cookies are ephemeral demo state, not authentication."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app, DEMO, MODEL, MODEL_LABEL
from app.browser_sessions import (
    BrowserSessionStore, COOKIE_NAME, SessionCapacityError,
)


def test_two_browsers_cannot_mutate_each_others_synthetic_replays():
    first = TestClient(app)
    second = TestClient(app)
    assert first.get("/api/patients").status_code == 200
    assert second.get("/api/patients").status_code == 200
    a_cookie = first.cookies.get(COOKIE_NAME)
    b_cookie = second.cookies.get(COOKIE_NAME)
    assert a_cookie and b_cookie and a_cookie != b_cookie

    first.post("/api/replay/HDT-027/reset").raise_for_status()
    second.post("/api/replay/HDT-027/reset").raise_for_status()
    advanced = first.post("/api/replay/HDT-027/step?steps=12")
    assert advanced.status_code == 200
    assert advanced.json()["twin_version"] == 13
    b = second.get("/api/replay/HDT-027/snapshot")
    assert b.status_code == 200
    assert b.json()["twin_version"] == 1
    assert b.json()["patient"]["patient_id"] == "HDT-027"

    # A chapter jump resets only the visitor making the request.
    first.post("/api/demo/chapter/sensor_gap").raise_for_status()
    untouched = second.get("/api/replay/HDT-027/snapshot").json()
    assert untouched["twin_version"] == 1


def test_invalid_cookie_mints_a_new_server_owned_token():
    real = TestClient(app)
    real.get("/api/patients")
    token = real.cookies.get(COOKIE_NAME)
    visitor = TestClient(app)
    visitor.cookies.set(COOKIE_NAME, "attacker-chosen-unknown-value")
    response = visitor.get("/api/patients")
    assert response.status_code == 200
    assert visitor.cookies.get(COOKIE_NAME) != token
    assert visitor.cookies.get(COOKIE_NAME) != "attacker-chosen-unknown-value"
    assert response.headers.get("cache-control") == "no-store"
    assert "httponly" in response.headers["set-cookie"].lower()


def test_ws_requires_an_existing_browser_cookie_and_uses_its_own_state():
    unauthenticated = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as caught:
        with unauthenticated.websocket_connect("/ws/replay/HDT-041"):
            pass
    assert caught.value.code == 4401

    browser = TestClient(app)
    browser.get("/api/patients")
    browser.post("/api/replay/HDT-041/reset").raise_for_status()
    with browser.websocket_connect("/ws/replay/HDT-041") as ws:
        msg = ws.receive_json()
    assert msg["patient"]["patient_id"] == "HDT-041"
    assert msg["twin_version"] == 2


def test_capacity_and_expiry_are_bounded(monkeypatch):
    import app.browser_sessions as sessions_module

    timeline = [1000.0]
    monkeypatch.setattr(sessions_module, "monotonic", lambda: timeline[0])
    store = BrowserSessionStore(DEMO, MODEL, MODEL_LABEL, ttl=10, max_sessions=1)
    token, first = store.obtain(None)
    assert store.obtain(token)[1] is first
    with pytest.raises(SessionCapacityError):
        store.obtain(None)

    timeline[0] += 11
    assert store.existing(token) is None
    replacement, second = store.obtain(None)
    assert replacement != token
    assert second is not first


def test_parallel_same_cookie_lookups_return_identical_isolated_state():
    store = BrowserSessionStore(DEMO, MODEL, MODEL_LABEL, max_sessions=2)
    token, expected = store.obtain(None)
    with ThreadPoolExecutor(max_workers=8) as pool:
        sessions = list(pool.map(store.obtain, [token] * 16))
    assert all(t == token and st is expected for t, st in sessions)
