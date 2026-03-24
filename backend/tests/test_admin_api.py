from __future__ import annotations

import pytest
from httpx import AsyncClient
from unittest.mock import patch

from api.index import app
from core.config_store import _hash_password, get_user_api_quota, init_db
from core.cache import init_cache_db
from core.db import get_main_db
from core.stats_store import init_stats_db, log_app_event


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(tmp_path):
    from core import db as db_mod

    await db_mod.close_all()

    test_main_db = str(tmp_path / "test_inksight.db")
    test_cache_db = str(tmp_path / "test_cache.db")

    with patch.object(db_mod, "_MAIN_DB_PATH", test_main_db), \
         patch.object(db_mod, "_CACHE_DB_PATH", test_cache_db), \
         patch("core.config_store.DB_PATH", test_main_db), \
         patch("core.stats_store.DB_PATH", test_main_db), \
         patch("core.cache._CACHE_DB_PATH", test_cache_db):
        await init_db()
        await init_stats_db()
        await init_cache_db()

        try:
            from httpx import ASGITransport  # type: ignore

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                yield c
        except Exception:
            async with AsyncClient(app=app, base_url="http://test") as c:
                yield c

        await db_mod.close_all()


async def _login_admin(client: AsyncClient, monkeypatch, username: str = "operator", password: str = "admin-pass-123"):
    pw_hash, _ = _hash_password(password)
    monkeypatch.setenv("ADMIN_CONSOLE_USERNAME", username)
    monkeypatch.setenv("ADMIN_CONSOLE_PASSWORD_HASH", pw_hash)
    monkeypatch.setenv("ADMIN_CONSOLE_SESSION_SECRET", "admin-session-secret")
    return await client.post(
        "/api/admin/auth/login",
        json={"username": username, "password": password},
    )


async def _register_user(client: AsyncClient, username: str):
    return await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "pass1234",
            "email": f"{username}@example.com",
        },
    )


@pytest.mark.asyncio
async def test_admin_login_me_and_overview_require_session(client: AsyncClient, monkeypatch):
    pw_hash, _ = _hash_password("right-password")
    monkeypatch.setenv("ADMIN_CONSOLE_USERNAME", "operator")
    monkeypatch.setenv("ADMIN_CONSOLE_PASSWORD_HASH", pw_hash)
    monkeypatch.setenv("ADMIN_CONSOLE_SESSION_SECRET", "admin-session-secret")

    unauthorized = await client.get("/api/admin/overview")
    assert unauthorized.status_code == 401

    wrong = await client.post(
        "/api/admin/auth/login",
        json={"username": "operator", "password": "wrong-password"},
    )
    assert wrong.status_code == 401

    login = await client.post(
        "/api/admin/auth/login",
        json={"username": "operator", "password": "right-password"},
    )
    assert login.status_code == 200
    assert login.json()["ok"] is True

    me = await client.get("/api/admin/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "operator"

    overview = await client.get("/api/admin/overview")
    assert overview.status_code == 200
    body = overview.json()
    assert body["overview"]["total_users"] == 0
    assert "recent_errors" in body
    assert "recent_admin_actions" in body


@pytest.mark.asyncio
async def test_admin_overview_recent_errors_excludes_info_events(client: AsyncClient, monkeypatch):
    pw_hash, _ = _hash_password("right-password")
    monkeypatch.setenv("ADMIN_CONSOLE_USERNAME", "operator")
    monkeypatch.setenv("ADMIN_CONSOLE_PASSWORD_HASH", pw_hash)
    monkeypatch.setenv("ADMIN_CONSOLE_SESSION_SECRET", "admin-session-secret")

    wrong = await client.post(
        "/api/admin/auth/login",
        json={"username": "operator", "password": "wrong-password"},
    )
    assert wrong.status_code == 401

    login = await client.post(
        "/api/admin/auth/login",
        json={"username": "operator", "password": "right-password"},
    )
    assert login.status_code == 200

    overview = await client.get("/api/admin/overview")
    assert overview.status_code == 200
    recent_errors = overview.json()["recent_errors"]
    assert recent_errors
    assert all(item["level"] in ("warning", "error") for item in recent_errors)


@pytest.mark.asyncio
async def test_admin_endpoints_do_not_accept_arbitrary_authorization_header(client: AsyncClient, monkeypatch):
    pw_hash, _ = _hash_password("right-password")
    monkeypatch.setenv("ADMIN_CONSOLE_USERNAME", "operator")
    monkeypatch.setenv("ADMIN_CONSOLE_PASSWORD_HASH", pw_hash)
    monkeypatch.setenv("ADMIN_CONSOLE_SESSION_SECRET", "admin-session-secret")
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)

    unauthorized = await client.get(
        "/api/admin/overview",
        headers={"Authorization": "Bearer definitely-not-valid"},
    )
    assert unauthorized.status_code == 401


@pytest.mark.asyncio
async def test_admin_generate_invite_code_and_redeem_uses_grant_amount(client: AsyncClient, monkeypatch):
    login = await _login_admin(client, monkeypatch)
    assert login.status_code == 200

    generated = await client.post(
        "/api/admin/invite-codes/generate",
        json={"count": 2, "grant_amount": 120, "remark": "beta batch"},
    )
    assert generated.status_code == 200
    payload = generated.json()
    assert payload["ok"] is True
    assert payload["batch_id"]
    assert len(payload["items"]) == 2
    assert payload["items"][0]["grant_amount"] == 120
    assert payload["items"][0]["remark"] == "beta batch"

    registered = await _register_user(client, "redeem-user")
    assert registered.status_code == 200
    user_id = registered.json()["user_id"]

    before = await get_user_api_quota(user_id)
    assert before is not None
    assert before["free_quota_remaining"] == 50

    redeem = await client.post(
        "/api/auth/redeem-invite-code",
        json={"invite_code": payload["items"][0]["code"]},
    )
    assert redeem.status_code == 200
    assert redeem.json()["free_quota_remaining"] == 170


@pytest.mark.asyncio
async def test_admin_logs_and_lists_return_data(client: AsyncClient, monkeypatch):
    login = await _login_admin(client, monkeypatch)
    assert login.status_code == 200

    invite_resp = await client.post(
        "/api/admin/invite-codes/generate",
        json={"count": 1, "grant_amount": 60, "remark": "ops"},
    )
    assert invite_resp.status_code == 200

    reg = await _register_user(client, "ops-user")
    assert reg.status_code == 200

    logs = await client.get("/api/admin/logs", params={"category": "admin", "limit": 20})
    assert logs.status_code == 200
    log_body = logs.json()
    assert log_body["items"]
    assert any(item["event_type"] == "admin_login_succeeded" for item in log_body["items"])

    users = await client.get("/api/admin/users", params={"limit": 10})
    assert users.status_code == 200
    assert users.json()["items"][0]["username"] == "ops-user"

    db = await get_main_db()
    await db.execute(
        """
        INSERT INTO device_state (mac, last_refresh_at, updated_at)
        VALUES (?, ?, ?)
        """,
        ("AA:BB:CC:DD:EE:FF", "2026-03-24T12:00:00", "2026-03-24T12:00:00"),
    )
    await db.commit()

    devices = await client.get("/api/admin/devices", params={"limit": 10})
    assert devices.status_code == 200
    assert devices.json()["items"][0]["mac"] == "AA:BB:CC:DD:EE:FF"


@pytest.mark.asyncio
async def test_admin_logs_enrich_no_device_preview_and_raw_message(client: AsyncClient, monkeypatch):
    login = await _login_admin(client, monkeypatch)
    assert login.status_code == 200

    reg = await _register_user(client, "preview-user")
    assert reg.status_code == 200
    user_id = reg.json()["user_id"]

    await log_app_event(
        level="error",
        category="llm",
        event_type="json_mode_llm_failed",
        actor_type="user",
        actor_id=user_id,
        message="LLM call failed for POETRY",
        details={
            "request_surface": "no_device_preview",
            "raw_message": "Missing or invalid API key for aliyun.",
            "usage_source": "current_user_api_key",
            "model": "deepseek-v3.2",
        },
    )

    logs = await client.get("/api/admin/logs", params={"category": "llm", "limit": 20})
    assert logs.status_code == 200
    item = logs.json()["items"][0]
    assert item["display_username"] == "preview-user"
    assert item["display_mac"] == "no device preview"
    assert item["raw_message"] == "Missing or invalid API key for aliyun."
    assert item["is_no_device_preview"] is True
    assert item["api_kind"] == "api url"
    assert item["model_name"] == "deepseek-v3.2"


@pytest.mark.asyncio
async def test_admin_logs_backfill_no_device_preview_for_legacy_llm_rows(client: AsyncClient, monkeypatch):
    login = await _login_admin(client, monkeypatch)
    assert login.status_code == 200

    await log_app_event(
        level="error",
        category="llm",
        event_type="json_mode_llm_failed",
        actor_type="system",
        message="Legacy llm failure",
        details={"raw_message": "legacy raw error"},
    )

    logs = await client.get("/api/admin/logs", params={"category": "llm", "limit": 20})
    assert logs.status_code == 200
    item = logs.json()["items"][0]
    assert item["display_mac"] == "no device preview"
    assert item["is_no_device_preview"] is True
    assert item["api_kind"] == "invite code"
