from __future__ import annotations

import ipaddress
import os
import socket
import ssl
import time

from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.database_url import DatabaseTarget


def is_serverless() -> bool:
    return os.environ.get("VERCEL") == "1"


def _is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def resolve_ipv4_host(host: str, port: int, *, attempts: int = 4) -> str:
    """Resolve A records only. Vercel cannot open IPv6 sockets (EBUSY / errno 99)."""
    if _is_ip_address(host):
        return host
    last_error: OSError | None = None
    for _ in range(attempts):
        try:
            infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        except OSError as exc:
            last_error = exc
            time.sleep(0.15)
            continue
        if infos:
            return infos[0][4][0]
        time.sleep(0.15)
    if last_error is not None:
        raise last_error
    raise OSError(f"no IPv4 address for {host}")


def engine_connect_args(target: DatabaseTarget) -> dict:
    connect_args: dict = {}
    if target.ssl:
        if target.supabase:
            # Pooler chain is not in the default CA store (sslmode=require).
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            connect_args["ssl"] = ctx
        else:
            connect_args["ssl"] = True
    if target.pgbouncer:
        # Transaction-mode PgBouncer cannot use prepared statements.
        connect_args["statement_cache_size"] = 0
    return connect_args


def engine_kwargs(settings: Settings) -> dict:
    target = settings.database_target
    kwargs: dict = {
        "pool_pre_ping": True,
        "connect_args": engine_connect_args(target),
    }
    if is_serverless() or target.pgbouncer:
        kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 5
    return kwargs
