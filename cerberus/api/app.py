"""
FastAPI Application Entry Point & Lifecycle Management.
Includes Prometheus Metrics, CORS, and Embedded Web Dashboard.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST

from cerberus import __version__
from cerberus.api.v1 import agents, analytics, config, health, keys, review
from cerberus.config import settings
from cerberus.core.cache import cache_manager
from cerberus.core.database import init_db
from cerberus.core.security import rate_limiter
from cerberus.core.security_headers import SecurityHeadersMiddleware, SensitiveDataMaskingFilter
from cerberus.core.telemetry import get_prometheus_metrics


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await cache_manager.connect()
    await rate_limiter.connect()
    yield
    # Shutdown — close all provider clients and resources
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
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # HTTP Request Body Size Enforcement Middleware
    @app.middleware("http")
    async def enforce_max_request_size(request: Request, call_next):
        content_length = request.headers.get("content-length")
        max_bytes = getattr(settings, "MAX_REQUEST_BODY_BYTES", 30 * 1024 * 1024)
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": "payload_too_large",
                            "message": f"Request body exceeds maximum allowed size of {max_bytes} bytes.",
                        },
                    )
            except ValueError:
                pass
        return await call_next(request)

    # Global Exception Handler (Prevents Internal Exception Traceback Leakage)
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logging.getLogger("cerberus.api").exception(
            f"Unhandled exception during {request.method} {request.url.path}: {exc}"
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
