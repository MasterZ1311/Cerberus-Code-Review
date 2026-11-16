"""
OpenTelemetry Distributed Tracing Configuration.
Provides end-to-end request tracing across agents, database, cache, and external APIs.
"""

import logging
from typing import Optional

from cerberus.config import settings

logger = logging.getLogger("cerberus.tracing")

# Global tracer instance
tracer: Optional[object] = None


def configure_tracing() -> None:
    """
    Initialize OpenTelemetry distributed tracing with OTLP exporter.
    Supports Jaeger, Grafana Tempo, Datadog, and other OTLP-compatible backends.
    """
    global tracer

    if not getattr(settings, "ENABLE_TRACING", False):
        logger.info("OpenTelemetry tracing disabled (ENABLE_TRACING=false)")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # Create resource with service metadata
        resource = Resource.create(
            {
                "service.name": "cerberus",
                "service.version": getattr(settings, "VERSION", "1.4.0"),
                "deployment.environment": settings.ENVIRONMENT,
            }
        )

        # Initialize tracer provider
        provider = TracerProvider(resource=resource)

        # Configure OTLP exporter
        otlp_endpoint = getattr(settings, "OTLP_ENDPOINT", "http://localhost:4317")
        insecure = settings.ENVIRONMENT.lower() in ("development", "dev", "local")

        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=insecure)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

        # Set global tracer provider
        trace.set_tracer_provider(provider)

        # Auto-instrument frameworks and libraries
        FastAPIInstrumentor.instrument()
        SQLAlchemyInstrumentor().instrument()
        RedisInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()

        tracer = trace.get_tracer("cerberus", getattr(settings, "VERSION", "1.4.0"))

        logger.info("OpenTelemetry tracing initialized successfully (endpoint=%s)", otlp_endpoint)

    except ImportError:
        logger.warning(
            "OpenTelemetry packages not installed. Install with: "
            "pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp "
            "opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-sqlalchemy "
            "opentelemetry-instrumentation-redis opentelemetry-instrumentation-httpx"
        )
    except Exception as e:
        logger.error("Failed to initialize OpenTelemetry tracing: %s: %s", type(e).__name__, e)


def get_tracer():
    """Get the configured OpenTelemetry tracer instance."""
    return tracer
