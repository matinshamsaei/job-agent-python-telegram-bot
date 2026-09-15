from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from sqlalchemy.engine.url import make_url

_BRACKETED_HOST = re.compile(r"(?:@|://)\[([^]]+)\]")

_LIBPQ_QUERY_KEYS = {
    "sslmode",
    "sslrootcert",
    "sslcert",
    "sslkey",
    "channel_binding",
    "gssencmode",
    "pgbouncer",
}


@dataclass(frozen=True, slots=True)
class DatabaseTarget:
    url: str
    host: str
    port: int | None
    ssl: bool
    pgbouncer: bool
    supabase: bool


def _strip_wrapping_quotes(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def _decode_bracket_escapes(raw: str) -> str:
    return (
        raw.replace("%5B", "[")
        .replace("%5D", "]")
        .replace("%5b", "[")
        .replace("%5d", "]")
    )


def _unbracket_non_ip_host(raw: str) -> str:
    """Python 3.13 only allows [host] for IP addresses, not DNS names."""

    def _replace(match: re.Match[str]) -> str:
        host = match.group(1)
        prefix = match.group(0)[: match.group(0).index("[")]
        try:
            ipaddress.ip_address(host.split("%", 1)[0])
        except ValueError:
            return f"{prefix}{host}"
        return match.group(0)

    return _BRACKETED_HOST.sub(_replace, raw, count=1)


def _repair_unencoded_at_in_password(parsed):
    """Recover `user:p@ss@host` where `@` in the password was not URL-encoded."""
    host = parsed.host or ""
    if "@" not in host:
        return parsed
    extra, real_host = host.rsplit("@", 1)
    if "." not in real_host:
        return parsed
    password = f"{parsed.password or ''}@{extra}"
    return parsed.set(password=password, host=real_host)


def _from_libpq_keywords(raw: str) -> str | None:
    """Convert `host=... user=... password=...` dashboard copy into a URI."""
    if "://" in raw:
        return None
    tokens = raw.replace("\n", " ").split()
    if not tokens or "=" not in tokens[0]:
        return None
    parts: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            return None
        key, value = token.split("=", 1)
        parts[key.lower()] = value
    host = parts.get("host")
    if not host:
        return None
    host = host.strip("[]")
    user = quote(parts.get("user", "postgres"), safe="")
    password = quote(parts.get("password", ""), safe="")
    port = parts.get("port", "5432")
    dbname = parts.get("dbname", "postgres")
    auth = f"{user}:{password}@" if parts.get("password") else f"{user}@"
    query = urlencode({k: v for k, v in parts.items() if k == "sslmode"})
    suffix = f"?{query}" if query else ""
    return f"postgresql://{auth}{host}:{port}/{dbname}{suffix}"


def normalize_database_url(raw: str) -> DatabaseTarget:
    """Turn a libpq/Supabase URL into an asyncpg SQLAlchemy URL.

    Supabase dashboard URLs are `postgres://` or `postgresql://` and often
    include `sslmode` / `pgbouncer` query params that asyncpg does not accept.
    Python 3.13 also rejects `[hostname]` in URLs; brackets are only valid for IPs.
    """
    value = _unbracket_non_ip_host(_decode_bracket_escapes(_strip_wrapping_quotes(raw)))
    keyword_uri = _from_libpq_keywords(value)
    if keyword_uri:
        value = keyword_uri

    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://") :]

    for prefix, replacement in (
        ("postgresql+asyncpg://", "postgresql+asyncpg://"),
        ("postgresql+psycopg2://", "postgresql+asyncpg://"),
        ("postgresql+psycopg://", "postgresql+asyncpg://"),
        ("postgresql://", "postgresql+asyncpg://"),
    ):
        if value.startswith(prefix):
            if prefix != replacement:
                value = replacement + value[len(prefix) :]
            break
    else:
        scheme = value.split(":", 1)[0]
        raise ValueError(
            "DATABASE_URL must be a postgres:// connection URI "
            f"(got scheme {scheme!r}). Copy Session pooler or Direct from "
            "Supabase → Project Settings → Database."
        )

    value = _unbracket_non_ip_host(value)
    try:
        parsed = make_url(value)
    except Exception as exc:
        raise ValueError(
            "DATABASE_URL could not be parsed. URL-encode special characters "
            "in the password (@, #, %, /) or copy the URI again from Supabase."
        ) from exc

    parsed = _repair_unencoded_at_in_password(parsed)

    if not parsed.host:
        raise ValueError(
            "DATABASE_URL could not be parsed. URL-encode special characters "
            "in the password (@, #, %, /) or copy the URI again from Supabase."
        )

    query = dict(parsed.query)
    sslmode = query.pop("sslmode", None)
    pgbouncer = str(query.pop("pgbouncer", "")).lower() in {"1", "true", "yes"}
    for key in list(query):
        if key.lower() in _LIBPQ_QUERY_KEYS:
            query.pop(key, None)

    host = parsed.host.lower()
    supabase = host.endswith(".supabase.co") or host.endswith(".supabase.com")
    if sslmode == "disable":
        ssl = False
    elif sslmode in {"require", "verify-ca", "verify-full"}:
        ssl = True
    else:
        ssl = supabase

    if parsed.port == 6543:
        pgbouncer = True

    parsed = parsed.set(drivername="postgresql+asyncpg", query=query)
    url = parsed.render_as_string(hide_password=False)
    return DatabaseTarget(
        url=url,
        host=host,
        port=parsed.port,
        ssl=ssl,
        pgbouncer=pgbouncer,
        supabase=supabase,
    )
