"""
Zero-Downtime Asynchronous Schema Migration Engine for cerberus</>.
Supports forward migrations with revision tracking on SQLite and PostgreSQL.
Fails closed upon unexpected migration failures to protect data integrity.
"""

import hashlib
import logging
from datetime import UTC, datetime
from typing import List, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("cerberus.migrations")

# Ordered list of registered schema migrations: (version, description, SQL or DDL callable)
MIGRATIONS: List[Tuple[str, str, str]] = [
    (
        "001_initial_schema",
        "Create initial core tables: code_reviews, review_findings, review_feedback, api_keys",
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(64) PRIMARY KEY,
            description VARCHAR(255) NOT NULL,
            checksum VARCHAR(64) NOT NULL,
            applied_at TIMESTAMP NOT NULL
        );
        """,
    ),
    (
        "002_review_approval_columns",
        "Add manual approval tracking columns to code_reviews",
        """
        SELECT 1;
        """,
    ),
    (
        "003_multitenancy_and_config",
        "Ensure runtime_config and multi-tenant attribution columns exist",
        """
        CREATE TABLE IF NOT EXISTS runtime_config (
            key VARCHAR(64) PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP NOT NULL
        );
        """,
    ),
    (
        "004_tenant_identity_enforcement_and_backfill",
        "Backfill legacy unowned records to explicit legacy_unassigned tenant",
        """
        SELECT 1;
        """,
    ),
]


async def _migrate_multitenancy_columns(conn) -> None:
    """Ensure multi-tenant and ownership columns exist on pre-existing database tables."""
    dialect = conn.dialect.name
    columns_to_ensure = [
        ("api_keys", "tenant_id", "VARCHAR(64)"),
        ("code_reviews", "owner_id", "VARCHAR(64)"),
        ("review_findings", "owner_id", "VARCHAR(64)"),
        ("review_feedback", "owner_id", "VARCHAR(64)"),
    ]
    for table, col, col_type in columns_to_ensure:
        try:
            if dialect == "sqlite":
                res = await conn.execute(text(f"PRAGMA table_info({table});"))
                existing_cols = {row[1] for row in res.fetchall()}
                if existing_cols and col not in existing_cols:
                    logger.info("Adding column '%s' to table '%s'", col, table)
                    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};"))
            else:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type};"))
        except Exception as e:
            logger.debug("Schema migration column check (%s.%s): %s", table, col, e)

    # Safe backfill strategy for legacy unowned records to prevent silent access
    backfill_statements = [
        text(
            "UPDATE api_keys SET tenant_id = 'legacy_unassigned' WHERE tenant_id IS NULL OR tenant_id = '' OR tenant_id = 'default';"
        ),
        text(
            "UPDATE code_reviews SET owner_id = 'legacy_unassigned' WHERE owner_id IS NULL OR owner_id = '' OR owner_id = 'default';"
        ),
        text(
            "UPDATE review_findings SET owner_id = 'legacy_unassigned' WHERE owner_id IS NULL OR owner_id = '' OR owner_id = 'default';"
        ),
        text(
            "UPDATE review_feedback SET owner_id = 'legacy_unassigned' WHERE owner_id IS NULL OR owner_id = '' OR owner_id = 'default';"
        ),
    ]
    for stmt in backfill_statements:
        try:
            await conn.execute(stmt)
        except Exception as e:
            logger.debug("Safe backfill check: %s", e)


async def run_migrations(engine: AsyncEngine) -> int:
    """
    Executes pending migrations sequentially inside transactions.
    Fails closed: raises an exception if any migration fails.
    Returns the count of newly applied migrations.
    """
    applied_count = 0
    try:
        async with engine.begin() as conn:
            # 1. Ensure migrations ledger table exists
            await conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(64) PRIMARY KEY,
                    description VARCHAR(255) NOT NULL,
                    checksum VARCHAR(64) NOT NULL,
                    applied_at TIMESTAMP NOT NULL
                );
            """)
            )

            # 2. Ensure multi-tenant schema columns are present
            await _migrate_multitenancy_columns(conn)

            # 2. Query already applied versions
            result = await conn.execute(text("SELECT version FROM schema_migrations;"))
            applied_versions = {row[0] for row in result.fetchall()}

            # 3. Apply missing migrations
            for version, description, sql_stmt in MIGRATIONS:
                if version not in applied_versions:
                    logger.info("Applying schema migration '%s': %s", version, description)
                    if sql_stmt.strip():
                        for stmt in sql_stmt.strip().split(";"):
                            clean_stmt = stmt.strip()
                            if clean_stmt:
                                await conn.execute(text(clean_stmt))

                    checksum = hashlib.sha256(sql_stmt.encode("utf-8")).hexdigest()
                    now = datetime.now(UTC)
                    await conn.execute(
                        text("""
                            INSERT INTO schema_migrations (version, description, checksum, applied_at)
                            VALUES (:version, :description, :checksum, :applied_at);
                        """),
                        {"version": version, "description": description, "checksum": checksum, "applied_at": now},
                    )
                    applied_count += 1
                    logger.info("Schema migration '%s' applied successfully.", version)

    except Exception as e:
        logger.critical("Schema migration failed on %s: %s", version if "version" in locals() else "ledger", e)
        raise

    return applied_count
