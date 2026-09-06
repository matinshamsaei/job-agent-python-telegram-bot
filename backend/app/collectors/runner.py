import json
import xml.etree.ElementTree as ET

import httpx
import structlog

from app.collectors.base import (
    CollectionOutcome,
    CollectorTarget,
    JobCollector,
    MissingTokenError,
    RawJob,
)
from app.collectors.registry import build_collector, missing_adapter_reason
from app.core.config import Settings
from app.core.enums import CollectionStatus

logger = structlog.get_logger(__name__)

PARSE_ERRORS = (ET.ParseError, json.JSONDecodeError, ValueError, KeyError, TypeError)


def classify_http_error(error: httpx.HTTPStatusError) -> tuple[CollectionStatus, str]:
    status = error.response.status_code
    if status in {401, 403}:
        return CollectionStatus.AUTH_REQUIRED, f"HTTP {status}: feed requires credentials"
    if status == 429:
        return CollectionStatus.BLOCKED, "HTTP 429: rate limited"
    if status in {404, 410}:
        return CollectionStatus.FEED_UNAVAILABLE, f"HTTP {status}: board token or feed url is wrong"
    if status >= 500:
        return CollectionStatus.FEED_UNAVAILABLE, f"HTTP {status}: upstream error"
    return CollectionStatus.INVALID_SOURCE, f"HTTP {status}"


async def collect_source(
    target: CollectorTarget,
    client: httpx.AsyncClient,
    settings: Settings,
) -> CollectionOutcome:
    """Collect one source and always return a status explaining the result."""
    collector = build_collector(target.ats_type, client, settings)
    if collector is None:
        detail = missing_adapter_reason(target.ats_type)
        logger.info(
            "source_adapter_missing",
            company=target.company_slug,
            ats_type=target.ats_type,
            careers_url=target.careers_url,
            reason=detail,
        )
        return CollectionOutcome(status=CollectionStatus.ADAPTER_MISSING, detail=detail)

    try:
        jobs = await collector.collect(target)
    except MissingTokenError as exc:
        return _failure(target, CollectionStatus.NEEDS_TOKEN, str(exc))
    except httpx.HTTPStatusError as exc:
        status, detail = classify_http_error(exc)
        return _failure(target, status, detail)
    except httpx.RequestError as exc:
        return _failure(target, CollectionStatus.FEED_UNAVAILABLE, f"{type(exc).__name__}: {exc}")
    except PARSE_ERRORS as exc:
        return _failure(target, CollectionStatus.INVALID_SOURCE, f"{type(exc).__name__}: {exc}")

    if not jobs:
        return CollectionOutcome(status=CollectionStatus.NO_JOBS, detail="feed reachable, zero postings")
    return CollectionOutcome(status=CollectionStatus.COLLECTED, jobs=jobs)


async def enrich_job(
    collector: JobCollector,
    target: CollectorTarget,
    raw: RawJob,
) -> RawJob:
    """Best-effort description fetch. A failure keeps the list-level fields."""
    try:
        return await collector.enrich(target, raw)
    except (httpx.HTTPError, MissingTokenError, *PARSE_ERRORS) as exc:
        logger.warning(
            "enrich_failed",
            company=target.company_slug,
            title=raw.title,
            error=f"{type(exc).__name__}: {exc}",
        )
        return raw


def _failure(target: CollectorTarget, status: CollectionStatus, detail: str) -> CollectionOutcome:
    logger.warning(
        "source_unavailable",
        company=target.company_slug,
        ats_type=target.ats_type,
        label=target.label,
        status=status.value,
        detail=detail,
    )
    return CollectionOutcome(status=status, detail=detail)
