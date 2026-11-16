"""
FastAPI Application Entry Point & Lifecycle Management.
Includes Prometheus Metrics, CORS, and Embedded Web Dashboard.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST

from cerberus import __version__
from cerberus.api.v1 import agents, analytics, auth, config, health, keys, plugins, review, tenants
from cerberus.config import settings
from cerberus.core.cache import cache_manager
from cerberus.core.database import init_db
from cerberus.core.security import rate_limiter
from cerberus.core.security_headers import SecurityHeadersMiddleware, SensitiveDataMaskingFilter
from cerberus.core.telemetry import get_prometheus_metrics

logger = logging.getLogger("cerberus.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Cerberus Multi-Agent API v%s (env=%s)", __version__, settings.ENVIRONMENT)

    # Initialize OpenTelemetry distributed tracing
    from cerberus.core.tracing import configure_tracing

    configure_tracing()

    try:
        await init_db()
        logger.info("Durable database backend initialized successfully.")
    except Exception as e:
        logger.error("Critical startup failure during database initialization: %s: %s", type(e).__name__, e)
        raise

    try:
        await cache_manager.connect()
        logger.info("Cache manager initialized (enabled=%s).", cache_manager.enabled)
    except Exception as e:
        logger.warning("Cache connection warning during startup: %s: %s", type(e).__name__, e)

    try:
        await rate_limiter.connect()
        logger.info("Rate limiter initialized successfully.")
    except Exception as e:
        logger.warning("Rate limiter connection warning during startup: %s: %s", type(e).__name__, e)

    retention_task = None
    if getattr(settings, "ENABLE_RETENTION_WORKER", True) and settings.ENVIRONMENT.lower() not in ("test", "testing"):
        from cerberus.core.background import background_tasks
        from cerberus.core.retention import retention_lifecycle_worker

        retention_task = background_tasks.create_task(
            retention_lifecycle_worker(interval_seconds=86400),
            name="retention_lifecycle_worker",
        )
        logger.info("Automated retention lifecycle worker started.")

    yield

    # Shutdown — close background tasks and resources
    if retention_task:
        retention_task.cancel()
        try:
            await retention_task
        except (asyncio.CancelledError, Exception):
            pass

    # Drain active background tasks before disposing database, cache, and provider resources
    from cerberus.core.background import background_tasks

    try:
        await background_tasks.drain_tasks(timeout=5.0)
    except Exception as drain_err:
        logger.warning("Error draining background tasks during shutdown: %s", drain_err)

    from cerberus.agents.orchestrator import orchestrator
    from cerberus.core.database import engine
    from cerberus.providers import close_all_providers

    for agent in orchestrator.registry.values():
        if hasattr(agent, "provider") and hasattr(agent.provider, "close") and agent.provider:
            await agent.provider.close()
    await close_all_providers()
    await rate_limiter.close()
    await cache_manager.close()
    if engine:
        try:
            await engine.dispose()
        except Exception:
            pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="cerberus</> Multi-Agent Code Review API",
        description="Autonomous Multi-Agent Code Review & Quality Assurance Platform",
        version=__version__,
        lifespan=lifespan,
    )

    # Attach Sensitive Data Masking Log Filter
    for handler in logging.root.handlers:
        handler.addFilter(SensitiveDataMaskingFilter())

    # Security Headers Middleware
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS Configuration
    allowed_origins = settings.cors_origins_list
    allow_credentials = True
    if "*" in allowed_origins:
        allow_credentials = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "X-GitHub-Event",
            "X-Hub-Signature-256",
            "X-Request-ID",
        ],
    )

    # ASGI Request Body Size Enforcement Middleware (Terminates oversized chunked/streaming bodies at receive layer)
    from cerberus.core.asgi_rate_limit import ASGIRequestSizeLimitMiddleware

    app.add_middleware(ASGIRequestSizeLimitMiddleware)

    # Global Exception Handler (Prevents Internal Exception Traceback Leakage)
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logging.getLogger("cerberus.api").exception(
            "Unhandled exception during %s %s: %s", request.method, request.url.path, exc
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": "An unexpected internal server error occurred. Request has been logged.",
            },
        )

    # Include Routers
    app.include_router(health.router)
    app.include_router(review.router)
    app.include_router(agents.router)
    app.include_router(config.router)
    app.include_router(analytics.router)
    app.include_router(keys.router)
    app.include_router(auth.router)
    app.include_router(plugins.router)
    app.include_router(tenants.router)

    # Prometheus /metrics endpoint
    @app.get("/metrics", include_in_schema=False)
    def metrics_endpoint():
        return Response(content=get_prometheus_metrics(), media_type=CONTENT_TYPE_LATEST)

    # Static Assets & Logo Serving
    assets_dir = Path(__file__).parent.parent.parent / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/logo.png", include_in_schema=False)
    def logo_endpoint():
        logo_path = Path(__file__).parent.parent / "web" / "logo.png"
        if not logo_path.exists():
            logo_path = Path(__file__).parent.parent.parent / "assets" / "cerberus_logo.png"
        return FileResponse(logo_path, media_type="image/png")

    @app.get("/favicon.png", include_in_schema=False)
    @app.get("/favicon.ico", include_in_schema=False)
    def favicon_endpoint():
        fav_path = Path(__file__).parent.parent / "web" / "favicon.png"
        if not fav_path.exists():
            fav_path = Path(__file__).parent.parent.parent / "assets" / "favicon.png"
        return FileResponse(fav_path, media_type="image/png")

    # Serve the Embedded Web Dashboard at Root
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
    def dashboard():
        html_path = Path(__file__).parent.parent / "web" / "index.html"
        if html_path.exists():
            return html_path.read_text(encoding="utf-8")
        return "<h1>cerberus</> Multi-Agent API is running.</h1>"

    return app


app = create_app()
