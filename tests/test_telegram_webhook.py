from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.notifications.bot import process_update
from app.notifications.webhook import webhook_url
from app.core.config import Settings


def test_webhook_rejects_missing_secret(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")
    client = TestClient(create_app(with_lifespan=False))
    response = client.post("/telegram/webhook", json={"update_id": 1})
    assert response.status_code == 503


def test_webhook_rejects_wrong_secret(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "expected-secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    client = TestClient(create_app(with_lifespan=False))
    response = client.post(
        "/telegram/webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert response.status_code == 401


def test_webhook_accepts_valid_secret_without_callback(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "expected-secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    client = TestClient(create_app(with_lifespan=False))
    response = client.post(
        "/telegram/webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "expected-secret"},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_webhook_dispatches_callback_query(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "expected-secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    client = TestClient(create_app(with_lifespan=False))
    payload = {
        "update_id": 9,
        "callback_query": {
            "id": "cb",
            "data": "skip:1",
            "message": {"chat": {"id": 42}, "message_id": 7},
        },
    }
    with patch("app.api.telegram.process_update", new_callable=AsyncMock) as mocked:
        response = client.post(
            "/telegram/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "expected-secret"},
        )
    assert response.status_code == 200
    mocked.assert_awaited_once()
    assert mocked.await_args.args[2]["update_id"] == 9


@pytest.mark.asyncio
async def test_process_update_ignores_other_chats() -> None:
    settings = Settings(telegram_chat_id="99")
    client = AsyncMock()
    callback = {
        "id": "cb",
        "data": "skip:1",
        "message": {"chat": {"id": 1}, "message_id": 7},
    }
    with patch("app.notifications.bot.handle_callback", new_callable=AsyncMock) as mocked:
        await process_update(settings, client, {"callback_query": callback})
    mocked.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_update_handles_matching_chat() -> None:
    settings = Settings(telegram_chat_id="42")
    client = AsyncMock()
    callback = {
        "id": "cb",
        "data": "skip:1",
        "message": {"chat": {"id": 42}, "message_id": 7},
    }
    with patch("app.notifications.bot.handle_callback", new_callable=AsyncMock) as mocked:
        await process_update(settings, client, {"callback_query": callback})
    mocked.assert_awaited_once()


def test_webhook_url_appends_path() -> None:
    settings = Settings(public_base_url="https://example.vercel.app/")
    assert webhook_url(settings, None) == "https://example.vercel.app/telegram/webhook"
