from __future__ import annotations

import secrets

import httpx
from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import get_settings
from app.notifications.bot import process_update

router = APIRouter(tags=["telegram"])

WEBHOOK_PATH = "/telegram/webhook"


@router.post(WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    settings = get_settings()
    expected = settings.telegram_webhook_secret
    if not expected:
        raise HTTPException(status_code=503, detail="Telegram webhook is not configured")
    provided = x_telegram_bot_api_secret_token or ""
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="Telegram bot token is not configured")

    payload = await request.json()
    timeout = httpx.Timeout(settings.http_timeout_seconds + 40)
    async with httpx.AsyncClient(timeout=timeout) as client:
        await process_update(settings, client, payload)
    return {"ok": True}
