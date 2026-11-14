"""
Telemetry, Metrics (Prometheus), OpenTelemetry-Compatible Distributed Tracing, and Structured Logging.
"""

from contextlib import asynccontextmanager, contextmanager
import logging
import secrets
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# Configure application-wide logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("cerberus")

# Prometheus Metrics
REVIEW_REQUESTS_TOTAL = Counter(
    "cerberus_review_requests_total",
    "Total number of code review requests processed",
    ["status", "language"]
)

REVIEW_DURATION_SECONDS = Histogram(
    "cerberus_review_duration_seconds",
    "Time spent analyzing code reviews",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

AGENT_EXECUTION_SECONDS = Histogram(
    "cerberus_agent_execution_seconds",
    "Execution duration per agent",
    ["agent_name"],
    buckets=[0.05, 0.2, 0.5, 1.0, 3.0, 8.0]
)

FINDINGS_DETECTED_TOTAL = Counter(
    "cerberus_findings_detected_total",
    "Count of findings discovered by agents",
    ["agent_name", "severity"]
)

CACHE_HITS_TOTAL = Counter(
    "cerberus_cache_hits_total",
    "Number of review requests served directly from cache"
)

CACHE_MISSES_TOTAL = Counter(
    "cerberus_cache_misses_total",
    "Number of review requests requiring fresh agent analysis"
)


def get_prometheus_metrics() -> bytes:
    """Returns serialized Prometheus metrics bytes."""
    return generate_latest()


# -------------------------------------------------------------
# OPENTELEMETRY-COMPATIBLE DISTRIBUTED TRACING
# -------------------------------------------------------------

class Span:
    """
    OpenTelemetry-compatible tracing span.
    Adheres to W3C Trace Context specifications (traceparent).
    """

    def __init__(
        self,
        name: str,
        trace_id: str,
        span_id: str,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.attributes: Dict[str, Any] = attributes or {}
        self.events: List[Dict[str, Any]] = []
        self.start_time: float = time.time()
        self.end_time: Optional[float] = None
        self.status: str = "OK"
        self.error_message: Optional[str] = None

    def set_attribute(self, key: str, value: Any) -> "Span":
        self.attributes[key] = value
        return self

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> "Span":
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })
        return self

    def record_exception(self, exception: BaseException) -> "Span":
        self.status = "ERROR"
        self.error_message = str(exception)
        self.add_event("exception", {
            "exception.type": exception.__class__.__name__,
            "exception.message": str(exception),
        })
        return self

    def finish(self) -> "Span":
        if self.end_time is None:
            self.end_time = time.time()
        return self

    @property
    def duration_ms(self) -> int:
        if self.end_time is None:
            return int((time.time() - self.start_time) * 1000)
        return int((self.end_time - self.start_time) * 1000)

    def to_w3c_traceparent(self) -> str:
        """Emits W3C standard traceparent header value: version-traceid-spanid-traceflags."""
        return f"00-{self.trace_id}-{self.span_id}-01"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "traceparent": self.to_w3c_traceparent(),
            "status": self.status,
            "error_message": self.error_message,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "events": self.events,
        }


class Tracer:
    """
    In-process OpenTelemetry-compatible Tracer.
    Tracks root and child spans with W3C traceparent propagation and export.
    """

    def __init__(self, max_stored_traces: int = 500):
        self.max_stored_traces = max_stored_traces
        self._traces: Dict[str, List[Span]] = {}

    def _generate_trace_id(self) -> str:
        return secrets.token_hex(16)  # 32 hex chars

    def _generate_span_id(self) -> str:
        return secrets.token_hex(8)  # 16 hex chars

    def parse_traceparent(self, header: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """Parses W3C traceparent header: 00-{trace_id}-{span_id}-{flags}."""
        if not header:
            return None, None
        parts = header.strip().split("-")
        if len(parts) == 4 and parts[0] == "00" and len(parts[1]) == 32 and len(parts[2]) == 16:
            return parts[1], parts[2]
        return None, None

    def start_trace(
        self,
        name: str,
        parent_traceparent: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Span:
        """Starts a new distributed trace (or continues an inbound W3C trace)."""
        trace_id, parent_span_id = self.parse_traceparent(parent_traceparent)
        if not trace_id:
            trace_id = self._generate_trace_id()
        span_id = self._generate_span_id()

        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            attributes=attributes,
        )
        self._record_span(span)
        return span

    def start_span(
        self,
        name: str,
        parent: Optional[Span] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Span:
        """Starts a child span under the given parent span."""
        if parent:
            trace_id = parent.trace_id
            parent_span_id = parent.span_id
        else:
            trace_id = self._generate_trace_id()
            parent_span_id = None
        span_id = self._generate_span_id()

        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            attributes=attributes,
        )
        self._record_span(span)
        return span

    def _record_span(self, span: Span) -> None:
        if span.trace_id not in self._traces:
            if len(self._traces) >= self.max_stored_traces:
                oldest_key = next(iter(self._traces))
                del self._traces[oldest_key]
            self._traces[span.trace_id] = []
        self._traces[span.trace_id].append(span)

    @asynccontextmanager
    async def async_span(
        self,
        name: str,
        parent: Optional[Span] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        span = self.start_span(name, parent=parent, attributes=attributes)
        try:
            yield span
        except BaseException as e:
            span.record_exception(e)
            raise
        finally:
            span.finish()

    @contextmanager
    def sync_span(
        self,
        name: str,
        parent: Optional[Span] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        span = self.start_span(name, parent=parent, attributes=attributes)
        try:
            yield span
        except BaseException as e:
            span.record_exception(e)
            raise
        finally:
            span.finish()

    def get_trace_spans(self, trace_id: str) -> List[Dict[str, Any]]:
        """Returns all serialized spans belonging to a trace_id."""
        spans = self._traces.get(trace_id, [])
        return [s.to_dict() for s in spans]

    def clear(self) -> None:
        self._traces.clear()


# Global OpenTelemetry-compatible Tracer instance
tracer = Tracer()

