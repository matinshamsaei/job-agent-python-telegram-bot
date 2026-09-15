from sqlalchemy.engine.url import make_url
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.database_url import normalize_database_url
from app.db.engine import engine_kwargs, resolve_ipv4_host


def test_supabase_uri_becomes_asyncpg_with_ssl() -> None:
    target = normalize_database_url(
        "postgres://postgres:secret@db.abc.supabase.co:5432/postgres?sslmode=require"
    )
    assert target.url.startswith("postgresql+asyncpg://")
    assert "sslmode" not in target.url
    assert target.ssl is True
    assert target.supabase is True
    assert target.pgbouncer is False
    assert target.host == "db.abc.supabase.co"


def test_transaction_pooler_disables_prepared_statements() -> None:
    target = normalize_database_url(
        "postgresql://postgres:secret@aws-0-ap-south-1.pooler.supabase.com:6543/postgres?pgbouncer=true"
    )
    assert target.pgbouncer is True
    assert "pgbouncer" not in target.url


def test_local_url_does_not_force_ssl() -> None:
    target = normalize_database_url(
        "postgresql+asyncpg://jobagent:jobagent@localhost:5434/jobagent"
    )
    assert target.ssl is False
    assert target.supabase is False


def test_bracketed_hostname_is_unwrapped() -> None:
    target = normalize_database_url(
        "postgresql://postgres:secret@[db.abc.supabase.co]:5432/postgres"
    )
    assert "db.abc.supabase.co" in target.url
    assert "[" not in target.url
    assert target.ssl is True


def test_keyword_host_brackets_are_stripped() -> None:
    target = normalize_database_url(
        "host=[db.abc.supabase.co] port=5432 dbname=postgres user=postgres "
        "password=secret sslmode=require"
    )
    assert "[" not in target.url
    assert "db.abc.supabase.co" in target.url


def test_quoted_and_keyword_forms_are_accepted() -> None:
    quoted = normalize_database_url(
        '"postgresql://postgres:secret@db.abc.supabase.co:5432/postgres"'
    )
    assert quoted.url.startswith("postgresql+asyncpg://")
    keywords = normalize_database_url(
        "host=db.abc.supabase.co port=5432 dbname=postgres user=postgres "
        "password=secret sslmode=require"
    )
    assert keywords.url.startswith("postgresql+asyncpg://")
    assert keywords.ssl is True


def test_unencoded_at_in_password_is_repaired() -> None:
    target = normalize_database_url(
        "postgresql://postgres.ref:p@ssword@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
    )
    assert target.host == "aws-0-ap-south-1.pooler.supabase.com"
    assert target.port == 6543
    assert make_url(target.url).password == "p@ssword"


def test_ipv4_literal_is_unchanged() -> None:
    assert resolve_ipv4_host("127.0.0.1", 5432) == "127.0.0.1"


def test_pgbouncer_uses_null_pool() -> None:
    settings = Settings(
        database_url="postgresql://postgres:secret@example.pooler.supabase.com:6543/postgres"
    )
    kwargs = engine_kwargs(settings)
    assert kwargs["poolclass"] is NullPool
    assert kwargs["connect_args"]["ssl"]
    assert kwargs["connect_args"]["statement_cache_size"] == 0
