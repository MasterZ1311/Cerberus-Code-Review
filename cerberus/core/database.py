"""
Database Engine & Async Session Management.
Supports SQLite (zero-config local) and PostgreSQL (production).
"""

import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from cerberus.config import settings
from cerberus.core.migrations import run_migrations
from cerberus.models.database import Base

logger = logging.getLogger("cerberus.database")

# Ensure proper connection string for SQLite with async
db_url = settings.DATABASE_URL
if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite+aiosqlite:///"):
    db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///")
elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+asyncpg://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

if "sqlite+aiosqlite:///./cerberus.db" in db_url:
    from pathlib import Path
    if not Path("cerberus.db").exists():
        fallback_db = Path(__file__).resolve().parent.parent.parent / "cerberus.db"
        if fallback_db.exists():
            db_url = f"sqlite+aiosqlite:///{fallback_db.as_posix()}"

connect_args = {}
engine_kwargs = {
    "echo": False,
    "future": True,
    "pool_pre_ping": True,
}

if "sqlite" in db_url:
    connect_args["check_same_thread"] = False
else:
    # Enterprise connection pooling for PostgreSQL in production
    engine_kwargs.update({
        "pool_size": 20,
        "max_overflow": 10,
        "pool_recycle": 3600,
        "pool_timeout": 30,
    })

engine = create_async_engine(
    db_url,
    connect_args=connect_args,
    **engine_kwargs
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)


async def warm_connection_pool() -> bool:
    """Pre-warms database connection pool on startup to prevent cold-start latency."""
    try:
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection pool warmed successfully.")
        return True
    except Exception as e:
        logger.warning(f"Connection pool warm-up notice: {e}")
        return False


async def init_db() -> None:
    """Initialize database tables, warm connections, and seed development credentials."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await run_migrations(engine)
        await warm_connection_pool()
        logger.info("Database schema initialized and migrations applied successfully.")

        # Seed default dev key in non-production mode
        if settings.ENVIRONMENT.lower() not in ("production", "prod") and settings.DEFAULT_DEV_API_KEY:
            async with AsyncSessionLocal() as session:
                from sqlalchemy import select
                from cerberus.core.security import hash_api_key
                from cerberus.models.database import ApiKeyRecord

                dev_hash = hash_api_key(settings.DEFAULT_DEV_API_KEY)
                stmt = select(ApiKeyRecord).where(ApiKeyRecord.key_hash == dev_hash)
                result = await session.execute(stmt)
                existing = result.scalars().first()
                if not existing:
                    dev_record = ApiKeyRecord(
                        key_hash=dev_hash,
                        name="Default Development Key",
                        prefix=settings.API_KEY_PREFIX,
                        scopes="review:read,review:write,admin",
                        is_active=True,
                    )
                    session.add(dev_record)
                    await session.commit()
                    logger.info(f"Seeded default development API key '{settings.DEFAULT_DEV_API_KEY}'.")
    except Exception as e:
        logger.warning(f"Database initialization warning: {e}")


async def execute_with_db_retry(
    fn,
    max_retries: int = 3,
    delay: float = 0.1
):
    """
    Executes a database transaction with automated retry on transient operational or lock errors.
    """
    import asyncio
    for attempt in range(max_retries):
        try:
            return await fn()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            logger.warning(f"Database transient error on attempt {attempt + 1}: {e}. Retrying in {delay}s...")
            await asyncio.sleep(delay)
            delay *= 2.0


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency for transactional database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
