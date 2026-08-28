from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AiProviderSnapshot, AiUsageRecord

logger = logging.getLogger(__name__)

DEEPSEEK_BALANCE_URL = "https://api.deepseek.com/user/balance"
DEEPSEEK_USAGE_URLS = (
    "https://platform.deepseek.com/api/v0/usage/cost",
    "https://platform.deepseek.com/api/v0/usage/amount",
)
REFRESH_COOLDOWN_SECONDS = 60
USAGE_KEEP_DAYS = 14


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _fetch_json(
    url: str,
    api_key: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if method == "POST":
        headers["Content-Type"] = "application/json"
    response = httpx.request(method, url, headers=headers, json=body, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _parse_usage(raw: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for response in raw.values():
        if not response:
            continue
        if response.get("code") not in (None, 0):
            continue
        data = response.get("data")
        if isinstance(data, dict):
            items = data.get("items") or []
        else:
            items = data or response.get("items") or []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                records.append(
                    {
                        "date": (
                            item.get("date")
                            or item.get("timestamp")
                            or item.get("created_at")
                            or ""
                        ),
                        "tokens": int(
                            item.get("tokens")
                            or item.get("token_count")
                            or item.get("usage")
                            or 0
                        ),
                        "cost": float(
                            item.get("cost")
                            or item.get("amount")
                            or item.get("total_cost")
                            or 0
                        ),
                    }
                )
        if response.get("total_tokens") is not None:
            records.append(
                {
                    "date": date.today().isoformat(),
                    "tokens": int(response["total_tokens"] or 0),
                    "cost": float(response.get("total_cost") or 0),
                }
            )

    merged: dict[str, dict[str, Any]] = {}
    for record in records:
        key = record.get("date") or "unknown"
        if key in merged:
            merged[key]["tokens"] += record["tokens"]
            merged[key]["cost"] += record["cost"]
        else:
            merged[key] = {"date": key, "tokens": record["tokens"], "cost": record["cost"]}
    return sorted(merged.values(), key=lambda item: item["date"], reverse=True)


def refresh_deepseek_monitor(db: Session) -> AiProviderSnapshot:
    settings = get_settings()
    now = _utcnow()
    api_key = settings.DEEPSEEK_API_KEY
    if not api_key:
        snapshot = AiProviderSnapshot(
            provider="deepseek",
            status="error",
            is_available=False,
            error_message="未配置 DeepSeek API Key",
            checked_at=now.replace(tzinfo=None),
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
        return snapshot

    try:
        raw = _fetch_json(DEEPSEEK_BALANCE_URL, api_key)
        if not bool(raw.get("is_available")):
            snapshot = AiProviderSnapshot(
                provider="deepseek",
                status="error",
                is_available=False,
                error_message="DeepSeek 服务当前不可用",
                checked_at=now.replace(tzinfo=None),
            )
            db.add(snapshot)
            db.commit()
            db.refresh(snapshot)
            return snapshot
        info = (raw.get("balance_infos") or [{}])[0]
        snapshot = AiProviderSnapshot(
            provider="deepseek",
            status="ok",
            is_available=True,
            total_balance=str(info.get("total_balance") or "0"),
            granted_balance=str(info.get("granted_balance") or "0"),
            topped_up_balance=str(info.get("topped_up_balance") or "0"),
            checked_at=now.replace(tzinfo=None),
        )
        db.add(snapshot)
        db.flush()

        usage_raw: dict[str, Any] = {}
        for url in DEEPSEEK_USAGE_URLS:
            try:
                usage_raw[url] = _fetch_json(url, api_key)
            except Exception:
                logger.exception("DeepSeek usage endpoint failed: %s", url)
                continue
        for record in _parse_usage(usage_raw):
            usage_date = date.fromisoformat(record["date"])
            row = db.scalar(
                select(AiUsageRecord).where(
                    AiUsageRecord.provider == "deepseek",
                    AiUsageRecord.usage_date == usage_date,
                )
            )
            if row is None:
                db.add(
                    AiUsageRecord(
                        provider="deepseek",
                        usage_date=usage_date,
                        tokens=record["tokens"],
                        cost=record["cost"],
                    )
                )
            else:
                row.tokens = record["tokens"]
                row.cost = record["cost"]

        cutoff = date.today() - timedelta(days=USAGE_KEEP_DAYS)
        db.execute(
            sa_delete(AiUsageRecord).where(
                AiUsageRecord.provider == "deepseek",
                AiUsageRecord.usage_date < cutoff,
            )
        )
        db.commit()
        db.refresh(snapshot)
        return snapshot
    except Exception as exc:
        logger.exception("DeepSeek monitor refresh failed")
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            if code == 401:
                message = "DeepSeek API Key 无效或未授权"
            elif code == 402:
                message = "DeepSeek 余额不足，无法调用"
            elif code == 429:
                message = "DeepSeek 请求过于频繁，请稍后刷新"
            else:
                message = f"DeepSeek API 返回错误（HTTP {code}）"
        elif isinstance(exc, httpx.ConnectError):
            message = "无法连接 DeepSeek API，请检查服务器网络"
        else:
            message = str(exc)[:500]
        snapshot = AiProviderSnapshot(
            provider="deepseek",
            status="error",
            is_available=False,
            error_message=message,
            checked_at=now.replace(tzinfo=None),
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
        return snapshot


def can_refresh(db: Session) -> bool:
    now = _utcnow()
    latest = db.scalar(
        select(AiProviderSnapshot)
        .where(AiProviderSnapshot.provider == "deepseek")
        .order_by(AiProviderSnapshot.checked_at.desc())
        .limit(1)
    )
    if latest is None:
        return True
    checked = _as_aware(latest.checked_at)
    return checked is None or (now - checked).total_seconds() >= REFRESH_COOLDOWN_SECONDS


def get_monitor_state(db: Session) -> dict[str, Any]:
    snapshot = db.scalar(
        select(AiProviderSnapshot)
        .where(AiProviderSnapshot.provider == "deepseek")
        .order_by(AiProviderSnapshot.checked_at.desc())
        .limit(1)
    )
    usage = list(
        db.scalars(
            select(AiUsageRecord)
            .where(AiUsageRecord.provider == "deepseek")
            .order_by(AiUsageRecord.usage_date.desc())
            .limit(USAGE_KEEP_DAYS)
        ).all()
    )
    threshold = get_settings().AI_LOW_BALANCE_THRESHOLD
    is_low = (
        snapshot is not None
        and snapshot.status == "ok"
        and float(snapshot.total_balance or 0) < threshold
    )
    return {
        "provider": "deepseek",
        "snapshot": snapshot,
        "usage": list(reversed(usage)),
        "is_low_balance": is_low,
        "low_balance_threshold": threshold,
    }
