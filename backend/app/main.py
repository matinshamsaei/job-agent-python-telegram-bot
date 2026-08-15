import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import LIVE_PATHS
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.redis import close_redis, init_redis
from app.db.session import dispose_engine, init_engine

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    init_engine(settings)
    await init_redis(settings)
    logger.info(
        "application_started",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )
    try:
        yield
    finally:
        await close_redis()
        await dispose_engine()
        logger.info("application_stopped")


def create_app(
    settings: Settings | None = None,
    *,
    with_lifespan: bool = True,
) -> FastAPI:
    resolved = settings or get_settings()
    application = FastAPI(
        title="Job Search & Immigration Assistant",
        description="Personal job-search assistant. Never auto-applies.",
        version=resolved.app_version,
        lifespan=lifespan if with_lifespan else None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def log_requests(request: Request, call_next):
        if request.url.path in LIVE_PATHS or request.url.path in {"/health", "/health/ready"}:
            return await call_next(request)
        start = time.perf_counter()
        response = await call_next(request)
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        return response

    application.include_router(api_router)
    return application


app = create_app()
