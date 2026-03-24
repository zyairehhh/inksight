from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse

from api.shared import limiter
from core.admin_store import (
    generate_invitation_codes,
    get_admin_overview,
    list_admin_devices,
    list_admin_users,
    list_invitation_codes,
)
from core.auth import (
    clear_admin_session_cookie,
    create_admin_session_token,
    is_admin_console_configured,
    require_admin_console_user,
    set_admin_session_cookie,
    verify_admin_console_credentials,
)
from core.stats_store import log_app_event, query_app_events

router = APIRouter(tags=["admin"])


@router.post("/admin/auth/login")
@limiter.limit("10/minute")
async def admin_login(request: Request, body: dict, response: Response):
    username = str(body.get("username") or "").strip()
    password = body.get("password") or ""

    if not is_admin_console_configured():
        return JSONResponse({"error": "admin_console_not_configured"}, status_code=503)

    if not verify_admin_console_credentials(username, password):
        await log_app_event(
            level="warning",
            category="admin",
            event_type="admin_login_failed",
            actor_type="admin",
            username=username,
            message="Admin login failed",
            details={"ip": getattr(request.client, "host", "")},
        )
        return JSONResponse({"error": "用户名或密码错误"}, status_code=401)

    token = create_admin_session_token(username)
    set_admin_session_cookie(response, token)
    await log_app_event(
        level="info",
        category="admin",
        event_type="admin_login_succeeded",
        actor_type="admin",
        username=username,
        message="Admin login succeeded",
        details={"ip": getattr(request.client, "host", "")},
    )
    return {"ok": True, "username": username}


@router.post("/admin/auth/logout")
async def admin_logout(
    response: Response,
    admin_username: str = Depends(require_admin_console_user),
):
    clear_admin_session_cookie(response)
    await log_app_event(
        level="info",
        category="admin",
        event_type="admin_logout",
        actor_type="admin",
        username=admin_username,
        message="Admin logout",
    )
    return {"ok": True}


@router.get("/admin/auth/me")
async def admin_me(admin_username: str = Depends(require_admin_console_user)):
    return {"ok": True, "username": admin_username}


@router.get("/admin/overview")
async def admin_overview(admin_username: str = Depends(require_admin_console_user)):
    payload = await get_admin_overview()
    payload["viewer"] = {"username": admin_username}
    return payload


@router.post("/admin/invite-codes/generate")
async def admin_generate_invite_codes(
    body: dict,
    admin_username: str = Depends(require_admin_console_user),
):
    count = int(body.get("count") or 0)
    grant_amount = int(body.get("grant_amount") or 0)
    remark = str(body.get("remark") or "").strip()
    prefix = str(body.get("prefix") or "INK").strip()

    if count < 1 or count > 200:
        return JSONResponse({"error": "count must be between 1 and 200"}, status_code=400)
    if grant_amount < 1 or grant_amount > 100000:
        return JSONResponse({"error": "grant_amount must be between 1 and 100000"}, status_code=400)

    generated = await generate_invitation_codes(
        count=count,
        grant_amount=grant_amount,
        remark=remark,
        generated_by=admin_username,
        prefix=prefix,
    )
    return {"ok": True, **generated}


@router.get("/admin/invite-codes")
async def admin_list_invite_codes(
    status: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin_username: str = Depends(require_admin_console_user),
):
    _ = admin_username
    items = await list_invitation_codes(status=status, limit=limit, offset=offset)
    return {"items": items}


@router.get("/admin/logs")
async def admin_logs(
    level: str = Query(default=""),
    category: str = Query(default=""),
    q: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin_username: str = Depends(require_admin_console_user),
):
    _ = admin_username
    items = await query_app_events(level=level, category=category, query=q, limit=limit, offset=offset)
    return {"items": items}


@router.get("/admin/users")
async def admin_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin_username: str = Depends(require_admin_console_user),
):
    _ = admin_username
    return {"items": await list_admin_users(limit=limit, offset=offset)}


@router.get("/admin/devices")
async def admin_devices(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin_username: str = Depends(require_admin_console_user),
):
    _ = admin_username
    return {"items": await list_admin_devices(limit=limit, offset=offset)}
