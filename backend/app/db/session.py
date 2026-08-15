from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings

engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings) -> AsyncEngine:
    global engine, SessionLocal
    engine = create_async_engine(
        settings.database_url_str,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )
    SessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine


async def dispose_engine() -> None:
    global engine, SessionLocal
    if engine is not None:
        await engine.dispose()
    engine = None
    SessionLocal = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if SessionLocal is None:
        raise RuntimeError("Database engine is not initialized")
    async with SessionLocal() as session:
        yield session


async def check_database() -> None:
    if engine is None:
        raise RuntimeError("Database engine is not initialized")
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
