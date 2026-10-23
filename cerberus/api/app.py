"""
FastAPI Application Entry Point & Lifecycle Management.
Includes Prometheus Metrics, CORS, and Embedded Web Dashboard.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from prometheus_client import CONTENT_TYPE_LATEST
from cerberus import __version__
from cerberus.api.v1 import agents, analytics, config, health, review
from cerberus.config import settings
from cerberus.core.cache import cache_manager
from cerberus.core.database import init_db
from cerberus.core.telemetry import get_prometheus_metrics


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await cache_manager.connect()
    yield
    # Shutdown — close all provider clients
    from cerberus.agents.orchestrator import orchestrator
    from cerberus.providers import close_all_providers
    for agent in orchestrator.registry.values():
        if hasattr(agent, "provider") and hasattr(agent.provider, "close") and agent.provider:
            await agent.provider.close()
    await close_all_providers()
    await cache_manager.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="cerberus</> Multi-Agent Code Review API",
        description="Autonomous Multi-Agent Code Review & Quality Assurance Platform",
        version=__version__,
        lifespan=lifespan,
    )

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

    # Include Routers
    app.include_router(health.router)
    app.include_router(review.router)
    app.include_router(agents.router)
    app.include_router(config.router)
    app.include_router(analytics.router)

    # Prometheus /metrics endpoint
    @app.get("/metrics", include_in_schema=False)
    def metrics_endpoint():
        return Response(content=get_prometheus_metrics(), media_type=CONTENT_TYPE_LATEST)

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
