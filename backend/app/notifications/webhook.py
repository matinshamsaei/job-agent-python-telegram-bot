"""Register or remove the Telegram webhook that points at this API."""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

from app.core.config import Settings
from app.core.logging import configure_logging

WEBHOOK_PATH = "/telegram/webhook"


def webhook_url(settings: Settings, public_base_url: str | None) -> str:
    base = (public_base_url or settings.public_base_url or "").rstrip("/")
    if not base:
        raise RuntimeError(
            "Pass --url or set PUBLIC_BASE_URL to the public HTTPS origin, "
            "for example https://job-agent.vercel.app"
        )
    return f"{base}{WEBHOOK_PATH}"


async def telegram_api(settings: Settings, method: str, payload: dict | None = None) -> dict:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        response = await client.post(url, json=payload or {})
        response.raise_for_status()
        body = response.json()
    if not body.get("ok"):
        raise RuntimeError(body.get("description") or f"Telegram {method} failed")
    return body


async def set_webhook(settings: Settings, public_base_url: str | None) -> dict:
    if not settings.telegram_webhook_secret:
        raise RuntimeError("TELEGRAM_WEBHOOK_SECRET is not set")
    return await telegram_api(
        settings,
        "setWebhook",
        {
            "url": webhook_url(settings, public_base_url),
            "secret_token": settings.telegram_webhook_secret,
            "allowed_updates": ["callback_query"],
            "drop_pending_updates": True,
        },
    )


async def delete_webhook(settings: Settings) -> dict:
    return await telegram_api(settings, "deleteWebhook", {"drop_pending_updates": True})


async def webhook_info(settings: Settings) -> dict:
    return await telegram_api(settings, "getWebhookInfo")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Manage the Telegram webhook")
    parser.add_argument("command", choices=("set", "delete", "info"))
    parser.add_argument("--url", help="Public origin or full webhook URL")
    args = parser.parse_args(argv)
    settings = Settings()
    configure_logging(settings)
    origin = args.url
    if origin and origin.rstrip("/").endswith(WEBHOOK_PATH):
        origin = origin[: -len(WEBHOOK_PATH)]
    if args.command == "set":
        result = asyncio.run(set_webhook(settings, origin))
        print(f"Webhook set to {webhook_url(settings, origin)}")
    elif args.command == "delete":
        result = asyncio.run(delete_webhook(settings))
        print("Webhook deleted; polling can be used locally again.")
    else:
        result = asyncio.run(webhook_info(settings))
        info = result.get("result") or {}
        print(f"url={info.get('url') or '(none)'}")
        print(f"pending_update_count={info.get('pending_update_count', 0)}")
        if info.get("last_error_message"):
            print(f"last_error_message={info['last_error_message']}")
            return
        return
    if not result.get("ok", True):
        sys.exit(1)


if __name__ == "__main__":
    main()
