from app.core.config import Settings


def test_default_database_url_uses_asyncpg() -> None:
    settings = Settings(
        database_url="postgresql://jobagent:jobagent@localhost:5432/jobagent"
    )
    assert settings.database_url_str.startswith("postgresql+asyncpg://")


def test_cors_origins_accepts_comma_separated_env() -> None:
    settings = Settings(cors_origins="https://example.vercel.app,http://localhost:3000")
    assert settings.cors_origin_list == ["https://example.vercel.app", "http://localhost:3000"]


def test_empty_env_uses_defaults(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "")
    monkeypatch.setenv("LOG_JSON", "")
    monkeypatch.setenv("API_PORT", "")
    monkeypatch.setenv("DETECT_CONCURRENCY", "")
    settings = Settings()
    assert settings.app_env == "development"
    assert settings.log_json is False
    assert settings.api_port == 8000
    assert settings.detect_concurrency == 2


def test_vercel_does_not_load_dotenv_files(monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    from app.core import config as config_mod

    assert config_mod._settings_env_files() == ()


def test_redis_is_optional() -> None:
    settings = Settings(redis_url="")
    assert settings.redis_configured is False


def test_log_level_is_normalized() -> None:
    settings = Settings(log_level="debug")
    assert settings.log_level == "DEBUG"


def test_reserved_secrets_default_empty() -> None:
    settings = Settings(openai_api_key="", telegram_bot_token="", telegram_chat_id="")
    assert settings.openai_api_key == ""
    assert settings.telegram_bot_token == ""
    assert settings.telegram_chat_id == ""
