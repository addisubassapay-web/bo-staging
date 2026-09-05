"""
Automated coverage for the internal self-ping keep-alive + Slack/Discord
alert pipeline.

Convention: this repo doesn't ship ``pytest-asyncio``, so async paths are
driven via ``asyncio.run`` inside plain sync test functions (mirroring
`tests/test_deliverability_hardening.py`).
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any, List, Optional

import pytest

sys.path.insert(0, "/app/backend")


# ---------------------------------------------------------------------------
# httpx.AsyncClient stub
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, status_code: int = 200, json_body: Optional[dict] = None):
        self.status_code = status_code
        self._json = json_body if json_body is not None else {"status": "ok"}

    def json(self) -> dict:
        return self._json


class _FakeAsyncClient:
    """Async-context-manager stand-in for httpx.AsyncClient."""

    get_returns: List[Any] = []
    post_calls: List[dict] = []
    get_raises: Optional[BaseException] = None

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url: str):
        if _FakeAsyncClient.get_raises is not None:
            raise _FakeAsyncClient.get_raises
        if not _FakeAsyncClient.get_returns:
            return _FakeResponse(200, {"status": "ok"})
        item = _FakeAsyncClient.get_returns.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def post(self, url: str, json: dict):
        _FakeAsyncClient.post_calls.append({"url": url, "json": json})
        return _FakeResponse(200, {"ok": True})


@pytest.fixture(autouse=True)
def _reset_fake_client(monkeypatch):
    _FakeAsyncClient.get_returns = []
    _FakeAsyncClient.post_calls = []
    _FakeAsyncClient.get_raises = None
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    yield


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("PREVIEW_URL", "https://example.preview.emergentagent.com")
    monkeypatch.setenv("HEALTH_ALERT_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/xxx")
    monkeypatch.setenv("PORT", "8001")
    return monkeypatch


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_tick_uses_preview_url(env):
    from server import _self_ping_tick
    _FakeAsyncClient.get_returns = [_FakeResponse(200, {"status": "ok"})]
    state = {"consecutive_degraded": 0, "alert_state": "healthy"}
    result = asyncio.run(_self_ping_tick(state))
    assert result["target"] == "https://example.preview.emergentagent.com/api/health"
    assert result["status"] == "ok"
    assert result["fired"] is None
    assert state["consecutive_degraded"] == 0


def test_tick_falls_back_to_localhost(monkeypatch):
    monkeypatch.delenv("PREVIEW_URL", raising=False)
    monkeypatch.setenv("PORT", "8001")
    monkeypatch.delenv("HEALTH_ALERT_WEBHOOK_URL", raising=False)
    from server import _self_ping_tick
    _FakeAsyncClient.get_returns = [_FakeResponse(200, {"status": "ok"})]
    state = {"consecutive_degraded": 0, "alert_state": "healthy"}
    result = asyncio.run(_self_ping_tick(state))
    assert result["target"] == "http://localhost:8001/api/health"


def test_single_degraded_does_not_alert(env):
    from server import _self_ping_tick
    _FakeAsyncClient.get_returns = [_FakeResponse(200, {"status": "degraded", "db": {"ok": False}})]
    state = {"consecutive_degraded": 0, "alert_state": "healthy"}
    result = asyncio.run(_self_ping_tick(state))
    assert result["status"] == "degraded"
    assert result["fired"] is None
    assert state["consecutive_degraded"] == 1
    assert state["alert_state"] == "healthy"
    assert _FakeAsyncClient.post_calls == []


def test_two_consecutive_degraded_fires_slack_alert(env):
    from server import _self_ping_tick
    _FakeAsyncClient.get_returns = [
        _FakeResponse(200, {"status": "degraded", "db": {"ok": False, "latency_ms": None}, "mailer": {"breaker_open": False}}),
        _FakeResponse(200, {"status": "degraded", "db": {"ok": False, "latency_ms": None}, "mailer": {"breaker_open": True}}),
    ]
    state = {"consecutive_degraded": 0, "alert_state": "healthy"}
    r1 = asyncio.run(_self_ping_tick(state))
    r2 = asyncio.run(_self_ping_tick(state))
    assert r1["fired"] is None
    assert r2["fired"] == "degraded"
    assert state["alert_state"] == "alerting"
    assert len(_FakeAsyncClient.post_calls) == 1
    call = _FakeAsyncClient.post_calls[0]
    assert call["url"] == "https://hooks.slack.com/services/T/B/xxx"
    assert "text" in call["json"] and "content" not in call["json"]
    assert "DEGRADED" in call["json"]["text"]


def test_recovery_fires_resolution(env):
    from server import _self_ping_tick
    _FakeAsyncClient.get_returns = [
        _FakeResponse(200, {"status": "degraded"}),
        _FakeResponse(200, {"status": "degraded"}),
        _FakeResponse(200, {"status": "ok", "db": {"ok": True}}),
    ]
    state = {"consecutive_degraded": 0, "alert_state": "healthy"}
    asyncio.run(_self_ping_tick(state))
    asyncio.run(_self_ping_tick(state))
    assert state["alert_state"] == "alerting"
    r3 = asyncio.run(_self_ping_tick(state))
    assert r3["fired"] == "recovered"
    assert state["alert_state"] == "healthy"
    assert state["consecutive_degraded"] == 0
    assert len(_FakeAsyncClient.post_calls) == 2
    assert "RECOVERED" in _FakeAsyncClient.post_calls[1]["json"]["text"]


def test_alerting_state_prevents_spam(env):
    from server import _self_ping_tick
    _FakeAsyncClient.get_returns = [
        _FakeResponse(200, {"status": "degraded"}),
        _FakeResponse(200, {"status": "degraded"}),
        _FakeResponse(200, {"status": "degraded"}),
        _FakeResponse(200, {"status": "degraded"}),
    ]
    state = {"consecutive_degraded": 0, "alert_state": "healthy"}
    for _ in range(4):
        asyncio.run(_self_ping_tick(state))
    assert len(_FakeAsyncClient.post_calls) == 1, "expected exactly one page, not per-tick spam"


def test_5xx_response_is_degraded(env):
    from server import _self_ping_tick
    _FakeAsyncClient.get_returns = [
        _FakeResponse(500, {"status": "ok"}),
        _FakeResponse(503, {"status": "ok"}),
    ]
    state = {"consecutive_degraded": 0, "alert_state": "healthy"}
    r1 = asyncio.run(_self_ping_tick(state))
    r2 = asyncio.run(_self_ping_tick(state))
    assert r1["status"] == "degraded"
    assert r2["status"] == "degraded"
    assert r2["fired"] == "degraded"


def test_network_exception_treated_as_degraded(env):
    from server import _self_ping_tick
    _FakeAsyncClient.get_raises = ConnectionError("boom")
    state = {"consecutive_degraded": 0, "alert_state": "healthy"}
    r1 = asyncio.run(_self_ping_tick(state))
    assert r1["status"] == "degraded"
    assert "error" in r1["data"]
    _FakeAsyncClient.get_raises = ConnectionError("still down")
    r2 = asyncio.run(_self_ping_tick(state))
    assert r2["fired"] == "degraded"


def test_post_health_alert_no_webhook_configured(monkeypatch):
    monkeypatch.delenv("HEALTH_ALERT_WEBHOOK_URL", raising=False)
    from server import _post_health_alert
    ok = asyncio.run(_post_health_alert("http://x/api/health", {}, kind="degraded"))
    assert ok is False
    assert _FakeAsyncClient.post_calls == []


def test_post_health_alert_discord_payload_shape(monkeypatch):
    monkeypatch.setenv("HEALTH_ALERT_WEBHOOK_URL", "https://discord.com/api/webhooks/123/abc")
    from server import _post_health_alert
    ok = asyncio.run(_post_health_alert(
        "http://x/api/health",
        {"db": {"ok": False, "latency_ms": None}, "mailer": {"breaker_open": True}},
        kind="degraded",
    ))
    assert ok is True
    assert len(_FakeAsyncClient.post_calls) == 1
    call = _FakeAsyncClient.post_calls[0]
    assert "content" in call["json"] and "text" not in call["json"]
    assert "DEGRADED" in call["json"]["content"]


def test_post_health_alert_slack_payload_shape(monkeypatch):
    monkeypatch.setenv("HEALTH_ALERT_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/xxx")
    from server import _post_health_alert
    ok = asyncio.run(_post_health_alert(
        "http://x/api/health",
        {"db": {"ok": True, "latency_ms": 12.3}, "mailer": {"breaker_open": False}},
        kind="recovered",
    ))
    assert ok is True
    assert "text" in _FakeAsyncClient.post_calls[0]["json"]
    assert "RECOVERED" in _FakeAsyncClient.post_calls[0]["json"]["text"]


def test_live_pod_recent_heartbeat_in_log():
    """Smoke: prove the real backend has actually been pinging itself.

    We look for a recent `[self-ping] Heartbeat ping status: 200` line in
    the supervisor stderr log. Skipped when the log file isn't reachable
    (CI runs elsewhere).
    """
    import os
    log = "/var/log/supervisor/backend.err.log"
    if not os.path.exists(log):
        pytest.skip("supervisor log not available")
    tail_bytes = 200_000
    with open(log, "rb") as f:
        try:
            f.seek(-tail_bytes, os.SEEK_END)
        except OSError:
            f.seek(0)
        data = f.read().decode(errors="ignore")
    assert "[self-ping] Heartbeat ping status:" in data, (
        "no recent self-ping heartbeat in log — is the loop dead?"
    )
