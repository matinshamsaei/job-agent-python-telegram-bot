from app.core.config import Settings


def test_default_database_url_uses_asyncpg() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://jobagent:jobagent@localhost:5432/jobagent"
    )
    assert settings.database_url_str.startswith("postgresql+asyncpg://")


def test_log_level_is_normalized() -> None:
    settings = Settings(log_level="debug")
    assert settings.log_level == "DEBUG"


def test_reserved_secrets_default_empty() -> None:
    settings = Settings()
    assert settings.openai_api_key == ""
    assert settings.telegram_bot_token == ""
    assert settings.telegram_chat_id == ""
