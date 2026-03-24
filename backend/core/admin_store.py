from __future__ import annotations

import secrets
import string
from datetime import datetime

import aiosqlite

from .db import get_main_db
from .stats_store import log_app_event, query_app_events

_INVITE_ALPHABET = string.ascii_uppercase + string.digits


def _generate_batch_id() -> str:
    return f"BATCH-{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3).upper()}"


def _generate_invite_code(prefix: str = "INK") -> str:
    cleaned_prefix = "".join(ch for ch in (prefix or "INK").upper() if ch.isalnum())[:8] or "INK"
    body = "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(8))
    return f"{cleaned_prefix}-{body}"


async def generate_invitation_codes(
    *,
    count: int,
    grant_amount: int,
    remark: str = "",
    generated_by: str = "",
    prefix: str = "INK",
) -> dict:
    now = datetime.now().isoformat()
    batch_id = _generate_batch_id()
    db = await get_main_db()
    items: list[dict] = []

    await db.execute("BEGIN")
    try:
        while len(items) < count:
            code = _generate_invite_code(prefix)
            try:
                await db.execute(
                    """
                    INSERT INTO invitation_codes
                        (code, is_used, generated_at, used_by_user_id, grant_amount, remark, batch_id, generated_by, used_at)
                    VALUES (?, 0, ?, NULL, ?, ?, ?, ?, '')
                    """,
                    (code, now, grant_amount, remark.strip(), batch_id, generated_by.strip()),
                )
                items.append(
                    {
                        "code": code,
                        "grant_amount": grant_amount,
                        "remark": remark.strip(),
                        "batch_id": batch_id,
                        "generated_at": now,
                        "generated_by": generated_by.strip(),
                    }
                )
            except aiosqlite.IntegrityError:
                continue
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await log_app_event(
        level="info",
        category="admin",
        event_type="invite_codes_generated",
        actor_type="admin",
        username=generated_by,
        message=f"Generated {count} invitation codes",
        details={"count": count, "grant_amount": grant_amount, "batch_id": batch_id, "remark": remark.strip()},
    )
    return {"batch_id": batch_id, "items": items}


async def list_invitation_codes(
    *,
    status: str = "all",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []

    if status == "used":
        clauses.append("ic.is_used = 1")
    elif status == "unused":
        clauses.append("ic.is_used = 0")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    db = await get_main_db()
    cursor = await db.execute(
        f"""
        SELECT
            ic.id, ic.code, ic.is_used, ic.generated_at, ic.used_by_user_id,
            ic.grant_amount, ic.remark, ic.batch_id, ic.generated_by, ic.used_at,
            u.username
        FROM invitation_codes ic
        LEFT JOIN users u ON u.id = ic.used_by_user_id
        {where}
        ORDER BY ic.generated_at DESC, ic.id DESC
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "code": row[1],
            "is_used": bool(row[2]),
            "generated_at": row[3],
            "used_by_user_id": row[4],
            "grant_amount": int(row[5] or 50),
            "remark": row[6] or "",
            "batch_id": row[7] or "",
            "generated_by": row[8] or "",
            "used_at": row[9] or "",
            "used_by_username": row[10] or "",
        }
        for row in rows
    ]


async def redeem_invitation_code(*, user_id: int, invite_code: str, username: str = "") -> dict:
    code = (invite_code or "").strip()
    if not code:
        return {"ok": False, "error": "邀请码不能为空", "status_code": 400}

    db = await get_main_db()
    try:
        await db.execute("BEGIN")
        cursor = await db.execute(
            """
            SELECT id, code, is_used, grant_amount
            FROM invitation_codes
            WHERE code = ?
            LIMIT 1
            """,
            (code,),
        )
        row = await cursor.fetchone()
        if not row:
            await db.rollback()
            await log_app_event(
                level="warning",
                category="invite",
                event_type="invite_redeem_invalid",
                actor_type="user",
                actor_id=user_id,
                username=username,
                message="Invalid invitation code",
                details={"code": code},
            )
            return {"ok": False, "error": "邀请码无效", "status_code": 400}
        if row[2]:
            await db.rollback()
            await log_app_event(
                level="warning",
                category="invite",
                event_type="invite_redeem_used",
                actor_type="user",
                actor_id=user_id,
                username=username,
                message="Invitation code already used",
                details={"code": code},
            )
            return {"ok": False, "error": "邀请码已被使用", "status_code": 409}

        grant_amount = int(row[3] or 50)
        used_at = datetime.now().isoformat()
        cursor = await db.execute(
            """
            UPDATE invitation_codes
            SET is_used = 1, used_by_user_id = ?, used_at = ?
            WHERE code = ? AND is_used = 0
            """,
            (user_id, used_at, code),
        )
        if cursor.rowcount == 0:
            await db.rollback()
            return {"ok": False, "error": "邀请码已被使用", "status_code": 409}

        await db.execute(
            """
            INSERT OR IGNORE INTO api_quotas (user_id, total_calls_made, free_quota_remaining)
            VALUES (?, 0, 0)
            """,
            (user_id,),
        )
        await db.execute(
            """
            UPDATE api_quotas
            SET free_quota_remaining = free_quota_remaining + ?
            WHERE user_id = ?
            """,
            (grant_amount, user_id),
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    cursor = await db.execute(
        "SELECT free_quota_remaining FROM api_quotas WHERE user_id = ?",
        (user_id,),
    )
    quota_row = await cursor.fetchone()
    remaining = int(quota_row[0] or 0) if quota_row else 0

    await log_app_event(
        level="info",
        category="invite",
        event_type="invite_redeemed",
        actor_type="user",
        actor_id=user_id,
        username=username,
        message=f"Invitation code redeemed for +{grant_amount}",
        details={"code": code, "grant_amount": grant_amount, "remaining_quota": remaining},
    )
    return {"ok": True, "grant_amount": grant_amount, "free_quota_remaining": remaining}


async def get_admin_overview() -> dict:
    db = await get_main_db()

    async def _one(sql: str):
        cursor = await db.execute(sql)
        row = await cursor.fetchone()
        return row[0] if row else 0

    total_users = int(await _one("SELECT COUNT(*) FROM users") or 0)
    total_llm_calls = int(await _one("SELECT COALESCE(SUM(total_calls_made), 0) FROM api_quotas") or 0)
    total_invite_codes = int(await _one("SELECT COUNT(*) FROM invitation_codes") or 0)
    used_invite_codes = int(await _one("SELECT COUNT(*) FROM invitation_codes WHERE is_used = 1") or 0)
    total_devices = int(await _one("SELECT COUNT(*) FROM device_state") or 0)
    total_renders = int(await _one("SELECT COUNT(*) FROM render_logs") or 0)
    recent_error_count = int(
        await _one(
            """
            SELECT COUNT(*)
            FROM app_event_logs
            WHERE level IN ('error', 'warning')
              AND created_at >= datetime('now', '-1 day')
            """
        )
        or 0
    )

    recent_errors = await query_app_events(levels=("warning", "error"), limit=8)
    recent_admin_actions = await query_app_events(category="admin", limit=8)

    return {
        "overview": {
            "total_users": total_users,
            "total_llm_calls": total_llm_calls,
            "total_invite_codes": total_invite_codes,
            "used_invite_codes": used_invite_codes,
            "unused_invite_codes": max(total_invite_codes - used_invite_codes, 0),
            "total_devices": total_devices,
            "total_renders": total_renders,
            "recent_error_count": recent_error_count,
        },
        "recent_errors": recent_errors,
        "recent_admin_actions": recent_admin_actions,
    }


async def list_admin_users(*, limit: int = 50, offset: int = 0) -> list[dict]:
    db = await get_main_db()
    cursor = await db.execute(
        """
        SELECT
            u.id,
            u.username,
            u.role,
            u.created_at,
            COALESCE(aq.free_quota_remaining, 0),
            COALESCE(aq.total_calls_made, 0),
            COUNT(DISTINCT dm.mac)
        FROM users u
        LEFT JOIN api_quotas aq ON aq.user_id = u.id
        LEFT JOIN device_memberships dm ON dm.user_id = u.id AND dm.status = 'active'
        GROUP BY u.id, u.username, u.role, u.created_at, aq.free_quota_remaining, aq.total_calls_made
        ORDER BY u.created_at DESC, u.id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "username": row[1],
            "role": row[2] or "user",
            "created_at": row[3],
            "free_quota_remaining": int(row[4] or 0),
            "total_calls_made": int(row[5] or 0),
            "device_count": int(row[6] or 0),
        }
        for row in rows
    ]


async def list_admin_devices(*, limit: int = 50, offset: int = 0) -> list[dict]:
    db = await get_main_db()
    cursor = await db.execute(
        """
        SELECT
            ds.mac,
            ds.last_persona,
            ds.last_refresh_at,
            ds.updated_at,
            COALESCE(rl.total_renders, 0),
            COALESCE(u.username, '')
        FROM device_state ds
        LEFT JOIN (
            SELECT mac, COUNT(*) AS total_renders
            FROM render_logs
            GROUP BY mac
        ) rl ON rl.mac = ds.mac
        LEFT JOIN device_memberships dm
            ON dm.mac = ds.mac AND dm.role = 'owner' AND dm.status = 'active'
        LEFT JOIN users u ON u.id = dm.user_id
        ORDER BY COALESCE(NULLIF(ds.last_refresh_at, ''), ds.updated_at) DESC, ds.mac ASC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )
    rows = await cursor.fetchall()
    return [
        {
            "mac": row[0],
            "last_persona": row[1] or "",
            "last_refresh_at": row[2] or "",
            "updated_at": row[3] or "",
            "total_renders": int(row[4] or 0),
            "owner_username": row[5] or "",
        }
        for row in rows
    ]
