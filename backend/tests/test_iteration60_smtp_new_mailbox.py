"""Iteration 60: Verify SMTP fix using new Hostinger mailbox
`email@support.mercariglobals.com`. Historical `5.7.1 Disabled by user from hPanel`
errors are pre-fix; new backend restart should route mail via new mailbox.
"""
from __future__ import annotations
import os
import ssl
import smtplib
import asyncio
import time
import pathlib
import pytest
import requests

# Load backend .env for SMTP creds (frontend .env has REACT_APP_BACKEND_URL).
BACKEND_ENV = pathlib.Path("/app/backend/.env")
FRONTEND_ENV = pathlib.Path("/app/frontend/.env")


def _load_env(p: pathlib.Path) -> dict:
    d = {}
    if not p.exists():
        return d
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        d[k.strip()] = v.strip().strip('"').strip("'")
    return d


BE = _load_env(BACKEND_ENV)
FE = _load_env(FRONTEND_ENV)
BASE_URL = FE.get("REACT_APP_BACKEND_URL", "").rstrip("/")

SMTP_HOST = BE.get("SMTP_HOST")
SMTP_PORT = int(BE.get("SMTP_PORT", "465"))
SMTP_USER = BE.get("SMTP_USER")
SMTP_PASSWORD = BE.get("SMTP_PASSWORD")
FROM_ADDR = BE.get("EMAIL_FROM_ADDRESS")
SUPPORT_EMAIL = BE.get("SUPPORT_EMAIL")
EXPECTED_MAILBOX = "email@support.mercariglobals.com"


# ---------- 1. Env sanity ----------
def test_backend_env_switched_to_new_mailbox():
    assert SMTP_USER == EXPECTED_MAILBOX, f"SMTP_USER={SMTP_USER}"
    assert FROM_ADDR == EXPECTED_MAILBOX, f"EMAIL_FROM_ADDRESS={FROM_ADDR}"
    assert SUPPORT_EMAIL == EXPECTED_MAILBOX, f"SUPPORT_EMAIL={SUPPORT_EMAIL}"
    assert SMTP_HOST == "smtp.hostinger.com"
    assert SMTP_PORT == 465


# ---------- 2. Direct SMTP SSL login ----------
def test_direct_smtp_ssl_login_new_mailbox():
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=20) as s:
        code, _ = s.login(SMTP_USER, SMTP_PASSWORD)
        # 235 = auth OK
        assert code in (235, 250), f"unexpected auth code {code}"


# ---------- 3. Running backend picked up new env ----------
def test_running_backend_has_new_smtp_user():
    """Read /proc/<pid>/environ for the supervised uvicorn backend."""
    import glob
    hits = []
    for envfile in glob.glob("/proc/[0-9]*/environ"):
        try:
            data = pathlib.Path(envfile).read_bytes().split(b"\x00")
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            continue
        env = {}
        for kv in data:
            if b"=" in kv:
                k, v = kv.split(b"=", 1)
                env[k.decode(errors="ignore")] = v.decode(errors="ignore")
        # heuristic: backend process has SMTP_USER set from our .env
        if env.get("SMTP_USER"):
            hits.append(env.get("SMTP_USER"))
    assert hits, "No backend process with SMTP_USER env found"
    assert all(h == EXPECTED_MAILBOX for h in hits), f"Found SMTP_USER values in running procs: {hits}"


# ---------- 4. Direct mailer.send_email ----------
def test_mailer_send_email_success():
    import sys
    sys.path.insert(0, "/app/backend")
    # ensure env vars visible to the module (in case pytest env differs)
    for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
              "EMAIL_FROM_ADDRESS", "EMAIL_FROM_NAME", "EMAIL_PROVIDER"):
        if BE.get(k):
            os.environ[k] = BE[k]
    from services import mailer  # type: ignore

    async def _run():
        return await mailer.send_email(
            to=EXPECTED_MAILBOX,  # self-send to avoid spamming external
            subject="[pytest iter60] SMTP mailbox switch verification",
            html="<p>Automated test — please ignore.</p>",
            text="Automated test — please ignore.",
            tags=["iter60", "smtp_switch"],
        )

    result = asyncio.get_event_loop().run_until_complete(_run()) if False else asyncio.run(_run())
    assert result.get("ok") is True, f"send_email returned {result}"
    assert result.get("provider") == "hostinger", f"provider={result.get('provider')}"
    assert "5.7.1" not in str(result.get("error") or ""), result


# ---------- 5. End-to-end via /api/support/tickets ----------
@pytest.fixture(scope="module")
def seller_token():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not configured")
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "sophia_style@demo.local", "password": "demo1234"},
        timeout=20,
    )
    if r.status_code != 200:
        pytest.skip(f"Seller login failed: {r.status_code} {r.text[:200]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if not tok:
        pytest.skip(f"No token in login response: {r.json()}")
    return tok


def test_support_ticket_email_sent_true(seller_token):
    r = requests.post(
        f"{BASE_URL}/api/support/tickets",
        json={
            "channel": "email",
            "subject": f"[iter60 pytest] SMTP mailbox switch {int(time.time())}",
            "message": "Iteration 60 verification — confirm outbound mail via new mailbox.",
        },
        headers={"Authorization": f"Bearer {seller_token}"},
        timeout=30,
    )
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    body = r.json()
    assert body.get("ok") is True
    assert body.get("channel") == "email"
    assert body.get("email_sent") is True, f"email_sent!=true, body={body}"


# ---------- 6. Backend log has no post-restart 5.7.1 ----------
def test_no_new_557_disabled_errors_in_backend_log():
    """Scan the backend supervisor log tail for post-restart 5.7.1 hPanel errors."""
    import subprocess
    log_paths = [
        "/var/log/supervisor/backend.err.log",
        "/var/log/supervisor/backend.out.log",
    ]
    combined = ""
    for p in log_paths:
        try:
            combined += subprocess.check_output(["tail", "-n", "400", p], text=True, timeout=5)
        except Exception:
            continue
    # Look for the exact hPanel error in the recent tail.
    # We accept historical entries older than restart; simplest check: no occurrences
    # in the LAST 200 lines (which will be after restart in this session).
    recent = "\n".join(combined.splitlines()[-200:])
    assert "5.7.1 Disabled by user from hPanel" not in recent, (
        "Found post-restart 5.7.1 hPanel error in backend tail — SMTP switch not effective"
    )
