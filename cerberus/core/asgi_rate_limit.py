"""
ASGI Request Body Size Enforcement Middleware.
Terminates oversized chunked, streaming, multipart, or standard HTTP requests at the
ASGI receive layer before downstream framework or memory buffer parsing.
"""

import json
import logging
from typing import Optional

from cerberus.config import settings

logger = logging.getLogger("cerberus.asgi.limits")


class OversizedPayloadException(Exception):
    """Raised when an incoming request body exceeds the maximum configured byte limit."""

    def __init__(self, limit: int, received: int):
        self.limit = limit
        self.received = received
        super().__init__(f"Request body exceeded limit of {limit} bytes (received {received} bytes).")


class ASGIRequestSizeLimitMiddleware:
    """
    Pure ASGI middleware that enforces request body caps at the network receive layer.
    Accurately meters chunked transfer-encoding bodies where Content-Length is absent,
    catches misleading/forged Content-Length headers, and aborts streaming uploads immediately.
    """

    def __init__(self, app, default_limit: Optional[int] = None):
        self.app = app
        if default_limit is not None:
            self.default_limit: int = default_limit
        else:
            self.default_limit = int(getattr(settings, "MAX_REQUEST_BODY_BYTES", 30 * 1024 * 1024))

    def _resolve_limit_for_request(self, path: str, content_type: str) -> int:
        """Determines path-specific or route-specific payload limit."""
        # JSON code review submissions: /api/v1/review (or /api/v1/review/batch)
        if path == "/api/v1/review":
            return getattr(settings, "MAX_CODE_SIZE_BYTES", 5 * 1024 * 1024)

        # Multipart ZIP archives: /api/v1/review/zip and /api/v1/review/upload-zip
        if path in ("/api/v1/review/zip", "/api/v1/review/upload-zip"):
            return getattr(settings, "MAX_ZIP_UPLOAD_BYTES", 25 * 1024 * 1024)

        # Base64-encoded ZIP payloads: /api/v1/review/zip-base64 (~4/3 overhead of 25MB binary)
        if path == "/api/v1/review/zip-base64":
            return int(getattr(settings, "MAX_ZIP_UPLOAD_BYTES", 25 * 1024 * 1024) * 1.4)

        # Webhook ingestion payloads: /api/v1/review/webhooks/*
        if "/webhooks" in path:
            return 10 * 1024 * 1024  # 10 MB webhook cap

        return self.default_limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        headers = dict(scope.get("headers", []))
        content_type = headers.get(b"content-type", b"").decode("latin-1").lower()
        content_length_raw = headers.get(b"content-length")

        limit = self._resolve_limit_for_request(path, content_type)

        # 1. Early rejection if Content-Length is present and already exceeds limit
        if content_length_raw:
            try:
                cl = int(content_length_raw.decode("latin-1"))
                if cl > limit:
                    logger.warning(
                        f"Request to {path} rejected by Content-Length check: {cl} bytes > {limit} bytes limit."
                    )
                    await self._send_413_response(send, limit, cl)
                    return
            except ValueError:
                pass

        # 2. Wrap receive callable to meter incoming body chunks (chunked, absent CL, or misleading CL)
        total_received = 0
        limit_exceeded = False
        response_started = False

        async def metered_receive():
            nonlocal total_received, limit_exceeded
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                total_received += len(body)
                if total_received > limit:
                    limit_exceeded = True
                    raise OversizedPayloadException(limit=limit, received=total_received)
            return message

        async def metered_send(message):
            nonlocal response_started
            if limit_exceeded:
                # Discard downstream error messages (e.g. framework 400 body parsing errors)
                return
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, metered_receive, metered_send)
            if limit_exceeded and not response_started:
                logger.warning(
                    f"Request to {path} terminated at ASGI receive layer: received {total_received} bytes > {limit} bytes limit."
                )
                await self._send_413_response(send, limit, total_received)
        except OversizedPayloadException as exc:
            if not response_started:
                logger.warning(
                    f"Request to {path} terminated at ASGI receive layer: received {exc.received} bytes > {exc.limit} bytes limit."
                )
                await self._send_413_response(send, exc.limit, exc.received)

    async def _send_413_response(self, send, limit: int, received: int):
        """Constructs and delivers a truthful RFC-compliant HTTP 413 JSON response."""
        response_payload = json.dumps(
            {
                "error": "payload_too_large",
                "message": f"Request body exceeds maximum allowed size of {limit} bytes (received {received} bytes).",
                "limit_bytes": limit,
                "received_bytes": received,
            }
        ).encode("utf-8")

        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(response_payload)).encode("ascii")),
                    (b"connection", b"close"),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": response_payload,
            }
        )
