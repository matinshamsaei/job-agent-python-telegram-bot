from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from app.db.engine import engine_kwargs

engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings) -> async_sessionmaker[AsyncSession]:
    global engine, SessionLocal
    engine = create_async_engine(settings.database_url_str, **engine_kwargs(settings))
    SessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return SessionLocal


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
