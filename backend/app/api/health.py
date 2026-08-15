from collections.abc import Awaitable, Callable

import structlog
from fastapi import APIRouter, Response

from app.core.config import get_settings
from app.db.redis import check_redis
from app.db.session import check_database
from app.schemas.health import CheckStatus, HealthChecks, HealthResponse

router = APIRouter(tags=["health"])
logger = structlog.get_logger(__name__)

LIVE_PATHS = {"/health/live"}


async def _run_check(
    name: str, probe: Callable[[], Awaitable[None]]
) -> tuple[CheckStatus, str | None]:
    try:
        await probe()
        return "ok", None
    except Exception as exc:
        logger.warning("health_check_failed", check=name, error=str(exc))
        return "error", str(exc)


@router.get("/health/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        checks=HealthChecks(database="skipped", redis="skipped"),
    )


@router.get("/health/ready", response_model=HealthResponse)
@router.get("/health", response_model=HealthResponse)
async def ready(response: Response) -> HealthResponse:
    settings = get_settings()
    db_status, db_error = await _run_check("database", check_database)
    redis_status, redis_error = await _run_check("redis", check_redis)

    errors: dict[str, str] = {}
    if db_error:
        errors["database"] = db_error
    if redis_error:
        errors["redis"] = redis_error

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    if overall != "ok":
        response.status_code = 503

    return HealthResponse(
        status=overall,
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        checks=HealthChecks(database=db_status, redis=redis_status),
        errors=errors,
    )
