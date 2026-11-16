"""
Code Review Endpoints: Single, Batch, Status, Results, Feedback, Webhook, and Real-Time Streams.
Features Multi-Tenant Data Isolation, Streaming Upload Caps, Atomic Idempotency, and Scoped Stream Tokens.
"""

import asyncio
import base64
import json
import logging
import re
import time
import uuid
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import JSONResponse, StreamingResponse

from cerberus.agents.orchestrator import orchestrator
from cerberus.api.dependencies import (
    get_key_record_for_token,
    require_scopes,
    verify_api_key,
)
from cerberus.config import settings
from cerberus.core.background import background_tasks
from cerberus.core.cache import cache_manager
from cerberus.core.database import AsyncSessionLocal
from cerberus.core.github_app import build_pr_review_payload, parse_pull_request_event, post_pr_review_to_github
from cerberus.core.privacy import redact_source_code_recursively
from cerberus.core.sarif import (
    review_response_to_gitlab_code_quality,
    review_response_to_sarif,
    review_response_to_sonarqube,
    zip_review_response_to_gitlab_code_quality,
    zip_review_response_to_sonarqube,
)
from cerberus.core.security import timing_safe_compare, verify_github_signature
from cerberus.core.syntax_verifier import detect_language_from_path
from cerberus.models.database import CodeReviewRecord, FindingRecord, ReviewFeedbackRecord
from cerberus.models.schemas import (
    BatchReviewRequest,
    BatchReviewResponse,
    CodeReviewRequest,
    CodeReviewResponse,
    FeedbackRequest,
    FeedbackResponse,
    ReviewApproveRequest,
    ReviewApproveResponse,
    ReviewConfig,
    ReviewContext,
    ReviewStatusResponse,
    ZipBase64ReviewRequest,
    ZipReviewResponse,
)

logger = logging.getLogger("cerberus.api.review")
router = APIRouter(prefix="/api/v1/review", tags=["Review"])

# Bounded in-memory store for quick lookups and active WebSocket broadcasts
REVIEWS_STORE_MAX_ITEMS = getattr(settings, "CACHE_MAX_ITEMS", 1000)
reviews_store: OrderedDict[str, CodeReviewResponse] = OrderedDict()
zip_reviews_store: OrderedDict[str, ZipReviewResponse] = OrderedDict()
_review_owners: OrderedDict[str, str] = OrderedDict()
_zip_review_owners: OrderedDict[str, str] = OrderedDict()
ws_connections: Dict[str, List[WebSocket]] = {}
_webhook_deliveries: OrderedDict[str, float] = OrderedDict()
MAX_WEBHOOK_PAYLOAD_BYTES = 10 * 1024 * 1024  # 10 MB cap
DELIVERY_IDEMPOTENCY_TTL_SECONDS = 600  # 10 minutes

# Strong reference tracking for background tasks to prevent GC in Python 3.11+
_background_tasks = background_tasks._tasks


def _create_background_task(coro, name: Optional[str] = None) -> asyncio.Task:
    """Creates a background task and retains a strong reference until completion."""
    return background_tasks.create_task(coro, name=name)


drain_background_tasks = background_tasks.drain_tasks


def _store_bounded_item(
    store: OrderedDict[str, Any],
    owner_store: Dict[str, str],
    item_id: str,
    item: Any,
    owner_id: Optional[str] = None,
    redis_prefix: Optional[str] = None,
) -> None:
    """Store item in bounded OrderedDict with LRU eviction and owner tracking."""
    if item_id in store:
        store.move_to_end(item_id)
    else:
        while len(store) >= REVIEWS_STORE_MAX_ITEMS and store:
            old_id, _ = store.popitem(last=False)
            owner_store.pop(old_id, None)
    store[item_id] = item
    if owner_id:
        owner_store[item_id] = owner_id
        if redis_prefix and cache_manager.redis_client:
            try:
                _create_background_task(cache_manager.redis_client.set(f"{redis_prefix}:{item_id}", owner_id, ex=86400))
            except Exception:
                pass


def _store_review(review_id: str, response: CodeReviewResponse, owner_id: Optional[str] = None) -> None:
    """Store review in bounded OrderedDict with LRU eviction, owner tracking, and privacy enforcement."""
    resp_to_store = response
    retain = getattr(settings, "RETAIN_SOURCE_CODE", False)
    if not retain:
        resp_to_store = redact_source_code_recursively(response)
    _store_bounded_item(reviews_store, _review_owners, review_id, resp_to_store, owner_id, "cvai:review_owner")


def _store_zip_review(review_id: str, response: ZipReviewResponse, owner_id: Optional[str] = None) -> None:
    """Store project zip review in bounded OrderedDict with LRU eviction."""
    _store_bounded_item(zip_reviews_store, _zip_review_owners, review_id, response, owner_id, "cvai:zip_owner")


async def _resolve_owner_from_sources(
    item_id: str,
    memory_owners: Dict[str, str],
    redis_prefix: str,
    check_db: bool = False,
) -> Optional[str]:
    """Resolves owner tenant_id from memory, Redis, or optional database record."""
    if item_id in memory_owners:
        return memory_owners[item_id]

    if cache_manager.redis_client:
        try:
            val = await cache_manager.redis_client.get(f"{redis_prefix}:{item_id}")
            if val:
                memory_owners[item_id] = val
                return val
        except Exception:
            pass

    if check_db:
        try:
            async with AsyncSessionLocal() as session:
                record = await session.get(CodeReviewRecord, item_id)
                if record and record.owner_id:
                    memory_owners[item_id] = record.owner_id
                    return record.owner_id
        except Exception:
            pass

    return None


async def _resolve_review_owner(review_id: str) -> Optional[str]:
    """Resolves owner tenant_id from memory, Redis, or database."""
    return await _resolve_owner_from_sources(review_id, _review_owners, "cvai:review_owner", check_db=True)


async def _resolve_zip_review_owner(zip_review_id: str) -> Optional[str]:
    """Resolves project zip review owner tenant_id from memory, Redis, or database."""
    return await _resolve_owner_from_sources(zip_review_id, _zip_review_owners, "cvai:zip_owner", check_db=False)


async def _notify_local_websockets(review_id: str, event_data: Dict[str, Any]) -> None:
    """Dispatches a real-time event to locally connected WebSockets, pruning disconnected sockets."""
    if review_id not in ws_connections:
        return
    cleaned_event = event_data
    if not getattr(settings, "RETAIN_SOURCE_CODE", False):
        cleaned_event = redact_source_code_recursively(event_data)
    active_sockets = list(ws_connections[review_id])
    payload = json.dumps(cleaned_event)
    for ws in active_sockets:
        try:
            await ws.send_text(payload)
        except Exception:
            if ws in ws_connections.get(review_id, []):
                ws_connections[review_id].remove(ws)
    if review_id in ws_connections and not ws_connections[review_id]:
        del ws_connections[review_id]


async def _lookup_review_response(review_id: str) -> Optional[CodeReviewResponse]:
    """Resolves CodeReviewResponse from memory, populating from DB fallback if needed."""
    if review_id in reviews_store:
        reviews_store.move_to_end(review_id)
        return reviews_store[review_id]

    try:
        async with AsyncSessionLocal() as session:
            record = await session.get(CodeReviewRecord, review_id)
            if record and record.results_json:
                results_data = record.results_json
                if isinstance(results_data, str):
                    results_data = json.loads(results_data)
                if isinstance(results_data, dict):
                    if "created_at" not in results_data:
                        results_data["created_at"] = (
                            record.created_at.isoformat() if record.created_at else datetime.now(UTC).isoformat()
                        )
                    res = CodeReviewResponse(**results_data)
                    _store_review(review_id, res, owner_id=record.owner_id)
                    return res
    except Exception as e:
        logger.warning("DB lookup failed for %s: %s", review_id, e)

    return None


@router.post("", response_model=CodeReviewResponse, status_code=status.HTTP_200_OK)
async def submit_review(
    request: CodeReviewRequest,
    http_req: Request,
    api_key: str = Depends(verify_api_key),
):
    """
    Submit source code for multi-agent review across Security, Performance, and Quality.
    Automatically binds tenant attribution to ensure strict multi-tenant isolation.
    """
    if not request.code or not request.code.strip():
        raise HTTPException(status_code=400, detail="Source code snippet cannot be empty")

    tenant_id = getattr(http_req.state, "tenant_id", "default")
    response = await orchestrator.execute_review(request)

    retain = getattr(settings, "RETAIN_SOURCE_CODE", False)
    if not retain:
        response = redact_source_code_recursively(response)

    # Persist critical record synchronously before exposing to memory/events (fails closed if persistence fails)
    try:
        await _persist_review_synchronous_core(request, response, owner_id=tenant_id)
    except Exception:
        # Guarantee fail-closed semantics: ensure no trace remains in memory, ownership, or cache
        reviews_store.pop(response.review_id, None)
        _review_owners.pop(response.review_id, None)
        await cache_manager.delete_review(response.review_id)
        raise

    # Store in bounded in-memory cache ONLY after successful durable core persistence
    _store_review(response.review_id, response, owner_id=tenant_id)

    # Persist detailed findings in background asynchronously
    _create_background_task(_persist_detailed_findings(response, owner_id=tenant_id))

    # Publish to Redis pub/sub across workers for SSE & WebSocket synchronization
    _create_background_task(
        cache_manager.publish_review_event(
            response.review_id,
            {
                "event": "review_completed",
                "review_id": response.review_id,
                "overall_score": response.overall_score,
                "status": response.status,
            },
        )
    )

    # Notify connected local WebSockets
    await _notify_local_websockets(
        response.review_id,
        {
            "event": "review_completed",
            "review_id": response.review_id,
            "overall_score": response.overall_score,
        },
    )

    return response


@router.get("/{review_id}", response_model=CodeReviewResponse)
async def get_review_status(
    review_id: str,
    http_req: Request,
    api_key: str = Depends(verify_api_key),
):
    """
    Get current processing status and synthesized results of a review.
    Enforces multi-tenant isolation: non-owners receive HTTP 404.
    """
    tenant_id = getattr(http_req.state, "tenant_id", None)
    is_platform_admin = getattr(http_req.state, "is_platform_admin", False)

    owner_id: Optional[str] = await _resolve_review_owner(review_id)
    response: Optional[CodeReviewResponse] = await _lookup_review_response(review_id)

    if response is None:
        raise HTTPException(status_code=404, detail=f"Review with ID '{review_id}' was not found.")

    if not owner_id:
        owner_id = await _resolve_review_owner(review_id)

    # Multi-tenant isolation: forbid cross-tenant access without platform:admin scope
    if owner_id and not is_platform_admin and tenant_id and owner_id != tenant_id:
        raise HTTPException(status_code=404, detail=f"Review with ID '{review_id}' was not found.")

    if not owner_id and settings.ENVIRONMENT.lower() in ("production", "prod") and not is_platform_admin:
        raise HTTPException(status_code=404, detail=f"Review with ID '{review_id}' was not found.")

    return response


@router.get("/{review_id}/results", response_model=CodeReviewResponse)
async def get_review_results(
    review_id: str,
    http_req: Request,
    api_key: str = Depends(verify_api_key),
):
    """Retrieve full synthesized results, agent findings, and remediation suggestions."""
    return await get_review_status(review_id, http_req, api_key)


@router.get("/{review_id}/sarif", response_class=JSONResponse)
async def get_review_sarif(
    review_id: str,
    http_req: Request,
    api_key: str = Depends(verify_api_key),
):
    """
    Export review findings in OASIS SARIF v2.1.0 standard format.
    Enforces multi-tenant isolation.
    """
    full = await get_review_status(review_id, http_req, api_key)
    filename = full.results.get("filename") if isinstance(full.results, dict) else "snippet.py"
    sarif_data = review_response_to_sarif(full, filename=filename)
    return JSONResponse(
        content=sarif_data,
        media_type="application/sarif+json",
        headers={"Content-Disposition": f"attachment; filename=cerberus-{review_id}.sarif"},
    )


@router.get("/{review_id}/gitlab", response_class=JSONResponse)
async def get_review_gitlab_code_quality(
    review_id: str,
    http_req: Request,
    api_key: str = Depends(verify_api_key),
):
    """Export review findings in GitLab CI Code Quality format with multi-tenant isolation."""
    full = await get_review_status(review_id, http_req, api_key)
    filename = full.results.get("filename") if isinstance(full.results, dict) else "snippet.py"
    gl_data = review_response_to_gitlab_code_quality(full, filename=filename)
    return JSONResponse(
        content=gl_data,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=gl-code-quality-report-{review_id}.json"},
    )


@router.get("/{review_id}/sonarqube", response_class=JSONResponse)
async def get_review_sonarqube(
    review_id: str,
    http_req: Request,
    api_key: str = Depends(verify_api_key),
):
    """Export review findings in SonarQube Generic Issue Import format with multi-tenant isolation."""
    full = await get_review_status(review_id, http_req, api_key)
    filename = full.results.get("filename") if isinstance(full.results, dict) else "snippet.py"
    sonar_data = review_response_to_sonarqube(full, filename=filename)
    return JSONResponse(
        content=sonar_data,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=sonar-generic-issues-{review_id}.json"},
    )


@router.post("/{review_id}/stream-token")
async def create_review_stream_token(
    review_id: str,
    http_req: Request,
    api_key: str = Depends(verify_api_key),
) -> Dict[str, Any]:
    """
    Issue a short-lived (60s), single-use scoped stream token for authenticating
    SSE or WebSocket streams without exposing long-lived API keys in URL query parameters.
    """
    # Enforce review ownership before generating stream token
    await get_review_status(review_id, http_req, api_key)
    tenant_id = getattr(http_req.state, "tenant_id", "default")
    token = await cache_manager.create_stream_token(review_id=review_id, tenant_id=tenant_id, ttl_seconds=60)
    return {
        "review_id": review_id,
        "stream_token": token,
        "expires_in_seconds": 60,
        "message": "Use ?stream_token=<token> to establish SSE or WebSocket streams.",
    }


@router.post("/webhooks/github")
async def handle_github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: str = Header("pull_request"),
    x_github_delivery: Optional[str] = Header(None),
):
    """
    Native GitHub Actions and GitHub App Webhook Event Ingestion.
    Requires explicit HMAC-SHA256 signature verification in all non-local environments.
    Enforces multi-worker replay prevention via distributed Redis locks.
    """
    raw_body = await request.body()
    if len(raw_body) > MAX_WEBHOOK_PAYLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "payload_too_large",
                "message": f"Webhook payload exceeds {MAX_WEBHOOK_PAYLOAD_BYTES} bytes cap.",
            },
        )

    # 1. Environment and Secret Verification
    is_prod = settings.ENVIRONMENT.lower() in ("production", "prod")
    allow_insecure_local = getattr(settings, "ALLOW_INSECURE_LOCAL_WEBHOOKS", False)

    if is_prod:
        if not settings.GITHUB_WEBHOOK_SECRET or settings.GITHUB_WEBHOOK_SECRET in (
            "cerberus_dev_secret_key_change_in_production_32chars",
            "secret",
            "changeme",
            "password",
            "admin",
        ):
            logger.error("Production misconfiguration: GITHUB_WEBHOOK_SECRET is not securely set.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "misconfigured_secret",
                    "message": "GITHUB_WEBHOOK_SECRET is required and must be configured in production.",
                },
            )
        secret = settings.GITHUB_WEBHOOK_SECRET
    else:
        secret = settings.GITHUB_WEBHOOK_SECRET or settings.SECRET_KEY

    # 2. Strict Signature Enforcement
    if not x_hub_signature_256:
        if is_prod or not allow_insecure_local:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing required X-Hub-Signature-256 HMAC signature header.",
            )

    if x_hub_signature_256:
        is_valid = verify_github_signature(raw_body, x_hub_signature_256, secret)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid GitHub X-Hub-Signature-256 HMAC signature",
            )

    # 3. Distributed Replay Protection via Redis with in-memory fallback
    if x_github_delivery:
        is_duplicate = False
        redis_conn = cache_manager.redis_client
        if redis_conn:
            try:
                acquired = await redis_conn.set(
                    f"cvai:webhook:delivery:{x_github_delivery}",
                    "1",
                    ex=DELIVERY_IDEMPOTENCY_TTL_SECONDS,
                    nx=True,
                )
                if not acquired:
                    is_duplicate = True
            except Exception as e:
                logger.warning("Redis webhook replay check error: %s", e)

        if not redis_conn or not is_duplicate:
            now = time.time()
            stale_threshold = now - DELIVERY_IDEMPOTENCY_TTL_SECONDS
            while _webhook_deliveries and next(iter(_webhook_deliveries.values())) < stale_threshold:
                _webhook_deliveries.popitem(last=False)

            if x_github_delivery in _webhook_deliveries:
                is_duplicate = True
            else:
                _webhook_deliveries[x_github_delivery] = now

        if is_duplicate:
            logger.info("Duplicate webhook delivery detected and ignored: %s", x_github_delivery)
            return {
                "status": "ignored",
                "reason": "duplicate_event",
                "delivery_id": x_github_delivery,
                "message": f"Webhook delivery '{x_github_delivery}' was already processed.",
            }

    # 4. Safe JSON Parsing
    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "malformed_json", "message": "Invalid JSON payload in webhook request"},
        ) from err

    # 5. Event Type Validation
    event_normalized = (x_github_event or "").strip().lower()
    if event_normalized not in ("pull_request", "ping"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "unsupported_event", "message": f"Webhook event '{x_github_event}' is not supported."},
        )

    if event_normalized == "ping":
        return {"status": "pong", "zen": "Keep it logically awesome.", "hook_id": payload.get("hook_id", 0)}

    pr_info = parse_pull_request_event(payload)
    action = (pr_info.action if pr_info else payload.get("action", "opened")).lower()

    if action not in ("opened", "synchronize", "reopened"):
        return {
            "status": "ignored",
            "action": action,
            "message": f"Pull request action '{action}' is ignored; only opened, synchronize, and reopened trigger reviews.",
        }

    code_to_review = payload.get("code") or payload.get("patch") or payload.get("diff") or ""
    filename = payload.get("filename")

    if not code_to_review and payload.get("files") and isinstance(payload["files"], list):
        f0 = payload["files"][0]
        if isinstance(f0, dict):
            code_to_review = f0.get("patch") or f0.get("content") or ""
            filename = f0.get("filename")

    if not filename:
        filename = f"PR_{pr_info.pr_number}.py" if pr_info else "pr_change.py"

    if not code_to_review and pr_info:
        body_text = pr_info.body or ""
        code_block_match = re.search(r"```(?:\w+)?\s*\n([\s\S]*?)\n```", body_text)
        if code_block_match:
            code_to_review = code_block_match.group(1).strip()
        elif body_text.strip():
            code_to_review = body_text.strip()
        elif pr_info.title:
            code_to_review = ""

    if not code_to_review:
        return {
            "status": "ignored",
            "message": f"Webhook received for event '{x_github_event}' (action: '{action}') with no reviewable code content.",
        }

    language = payload.get("language") or detect_language_from_path(filename) or "python"

    review_req = CodeReviewRequest(
        code=code_to_review,
        filename=filename,
        language=language,
        config=ReviewConfig(blocking_mode=True),
        context=ReviewContext(custom={"is_webhook": True, "event": x_github_event, "action": action}),
    )
    result = await orchestrator.execute_review(review_req)

    # 6. Synchronous core persistence before exposing review state, cache, or external GitHub posts
    try:
        await _persist_review_synchronous_core(review_req, result, owner_id="github_webhook")
    except Exception as e:
        logger.error(
            "Failed to synchronously persist webhook review record %s: %s: %s", result.review_id, type(e).__name__, e
        )
        # Guarantee fail-closed semantics: ensure no trace in memory, ownership maps, or cache
        reviews_store.pop(result.review_id, None)
        _review_owners.pop(result.review_id, None)
        await cache_manager.delete_review(result.review_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "persistence_failure",
                "message": "Failed to persist webhook review record to durable storage.",
            },
        ) from None

    # 7. Store in bounded in-memory cache ONLY after successful durable core persistence
    _store_review(result.review_id, result, owner_id="github_webhook")

    # 8. Asynchronously persist noncritical detailed child findings
    _create_background_task(_persist_detailed_findings(result, owner_id="github_webhook"))

    pr_payload = None
    posted = False
    github_comments = []

    if pr_info:
        pr_payload = build_pr_review_payload(result, pr_info, filename=filename)
        posted, _ = await post_pr_review_to_github(pr_info, pr_payload)
        github_comments = [c.model_dump() for c in pr_payload.comments]
    else:
        fixer = orchestrator.registry.get("code_fixer")
        all_findings = result.critical_issues + result.warnings + result.suggestions
        github_comments = (
            getattr(fixer, "generate_pr_review_comments", lambda *args, **kwargs: [])(all_findings, filename=filename)
            if fixer
            else []
        )

    verdict = (
        result.collaborative_consensus.get("pr_action", "MERGE_READY")
        if result.collaborative_consensus
        else "MERGE_READY"
    )
    pr_action = pr_payload.event if pr_payload else ("REQUEST_CHANGES" if result.should_block else "APPROVE")

    return {
        "status": "completed",
        "event": x_github_event,
        "action": action,
        "review_id": result.review_id,
        "pr_number": pr_info.pr_number if pr_info else payload.get("number", 0),
        "repository": pr_info.full_name if pr_info else payload.get("repository", {}).get("full_name", "unknown"),
        "overall_score": result.overall_score or 0,
        "verdict": verdict,
        "pr_review_action": pr_action,
        "should_block": result.should_block,
        "block_reason": result.block_reason,
        "posted_to_github": posted,
        "github_review_payload": pr_payload.model_dump() if pr_payload else {},
        "github_review_comments": github_comments,
        "summary": result.summary or f"Cerberus analyzed {filename}: Score {result.overall_score}/100",
    }


@router.get("/{review_id}/status", response_model=ReviewStatusResponse)
async def get_review_status_only(
    review_id: str,
    http_req: Request,
    api_key: str = Depends(verify_api_key),
):
    """Get lightweight status and blocking evaluation for automated gating."""
    full = await get_review_status(review_id, http_req, api_key)
    return ReviewStatusResponse(
        review_id=full.review_id,
        status=full.status,
        overall_score=full.overall_score,
        created_at=full.created_at,
        completed_at=full.completed_at,
        should_block=full.should_block,
        block_reason=full.block_reason,
    )


@router.post("/{review_id}/approve", response_model=ReviewApproveResponse)
async def approve_review(
    review_id: str,
    http_req: Request,
    payload: Optional[ReviewApproveRequest] = None,
    api_key: str = Depends(require_scopes("review:write")),
):
    """
    Human-in-the-Loop PR Approval Gate with multi-tenant ownership validation.
    """
    full = await get_review_status(review_id, http_req, api_key)
    req = payload or ReviewApproveRequest()
    now_iso = datetime.now(UTC).isoformat()

    if full.should_block and req.override_blocking:
        full.should_block = False
        full.block_reason = f"Manually approved by '{req.reviewer}'. Overrode blocking rule: {full.block_reason}"
    full.status = "approved"
    existing_owner = await _resolve_review_owner(review_id)
    tenant_id = existing_owner or getattr(http_req.state, "tenant_id", "default")
    _store_review(review_id, full, owner_id=tenant_id)

    try:
        async with AsyncSessionLocal() as session:
            record = await session.get(CodeReviewRecord, review_id)
            if record:
                record.status = "approved"
                if record.results_json and isinstance(record.results_json, dict):
                    rec_data = dict(record.results_json)
                    rec_data["status"] = "approved"
                    rec_data["should_block"] = False
                    record.results_json = rec_data
                await session.commit()
    except Exception as e:
        logger.warning("Could not persist review approval to DB: %s", e)

    return ReviewApproveResponse(
        review_id=review_id,
        status="approved",
        approved_by=req.reviewer,
        approved_at=now_iso,
        override_applied=req.override_blocking,
        message=f"Review '{review_id}' successfully approved for merge by {req.reviewer}.",
    )


@router.get("/{review_id}/stream")
async def stream_review_sse(
    review_id: str,
    request: Request,
    stream_token: Optional[str] = Query(None, description="Scoped one-time stream token"),
    token: Optional[str] = Query(None, description="Forbidden raw API key query parameter"),
    authorization: Optional[str] = Header(None),
):
    """
    Server-Sent Events (SSE) progress and completion stream.
    Rejects raw API keys in query parameters across ALL environments.
    Accepts scoped one-time stream tokens or Bearer Authorization headers with review ownership verification.
    """
    # 1. Reject raw API keys in query parameters
    if token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Raw API keys in query parameters are forbidden. Generate a scoped stream token via POST /{review_id}/stream-token or use the Authorization header.",
        )

    tenant_id: Optional[str] = None
    is_platform_admin = False

    # 2. Authenticate via scoped stream token or Bearer header
    if stream_token:
        token_data = await cache_manager.consume_stream_token(stream_token)
        if token_data and token_data.get("review_id") == review_id:
            tenant_id = token_data.get("tenant_id")
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid, expired, or already-consumed stream token.",
            )
    elif authorization and authorization.lower().startswith("bearer "):
        raw_key = authorization.split(" ", 1)[1].strip()
        key_record = await get_key_record_for_token(raw_key)
        if key_record:
            tenant_id = key_record.tenant_id
            scopes = set(key_record.scopes.split(",")) if key_record.scopes else set()
            is_dev_mode = settings.ENVIRONMENT.lower() not in ("production", "prod")
            is_platform_admin = ("platform:admin" in scopes) or bool(
                is_dev_mode
                and settings.DEFAULT_DEV_API_KEY
                and timing_safe_compare(raw_key, settings.DEFAULT_DEV_API_KEY)
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key in Authorization header.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide Authorization header or scoped ?stream_token=.",
        )

    # 3. Verify tenant ownership of the target review
    owner_id: Optional[str] = await _resolve_review_owner(review_id)
    if owner_id and not is_platform_admin and tenant_id and owner_id != tenant_id:
        raise HTTPException(status_code=404, detail=f"Review with ID '{review_id}' was not found.")

    async def event_generator():
        yield f"event: connected\ndata: {json.dumps({'review_id': review_id, 'status': 'connected'})}\n\n"

        # Check if review already finished
        # Check in-memory store and DB for already-completed reviews
        res = await _lookup_review_response(review_id)
        if res and res.status in ("completed", "approved", "failed"):
            yield f"event: completed\ndata: {json.dumps({'review_id': review_id, 'overall_score': res.overall_score, 'status': res.status})}\n\n"
            return

        # Stream via shared Redis pub/sub (guarantees cross-worker delivery)
        saw_completion = False
        async for evt in cache_manager.subscribe_review_events(review_id, timeout_seconds=30.0):
            evt_type = evt.get("event", "message")
            yield f"event: {evt_type}\ndata: {json.dumps(evt)}\n\n"
            if evt_type in ("review_completed", "completed"):
                saw_completion = True
                return

        # Fallback: if pub/sub timed out without completion event, check DB once more
        if not saw_completion:
            latest = await _lookup_review_response(review_id)
            if latest and latest.status in ("completed", "approved", "failed"):
                yield f"event: completed\ndata: {json.dumps({'review_id': review_id, 'overall_score': latest.overall_score, 'status': latest.status})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/batch", response_model=BatchReviewResponse)
async def batch_review(
    request: BatchReviewRequest,
    http_req: Request,
    api_key: str = Depends(verify_api_key),
):
    """Submit multiple files or snippets for concurrent batch code review."""
    if len(request.files) > settings.MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size {len(request.files)} exceeds maximum allowed of {settings.MAX_BATCH_SIZE}",
        )

    tenant_id = getattr(http_req.state, "tenant_id", "default")
    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_BATCH_REVIEWS)

    async def _throttled_review(req):
        async with semaphore:
            return await orchestrator.execute_review(req)

    results: List[CodeReviewResponse] = await asyncio.gather(*[_throttled_review(req) for req in request.files])

    retain = getattr(settings, "RETAIN_SOURCE_CODE", False)
    sanitized_results: List[CodeReviewResponse] = [
        redact_source_code_recursively(res) if not retain else res for res in results
    ]

    # Persist batch review core records synchronously in an atomic batch session before exposing to memory/cache
    pairs = list(zip(request.files, sanitized_results, strict=False))
    try:
        await _persist_batch_reviews_synchronous_core(pairs, owner_id=tenant_id)
    except Exception:
        # Guarantee no partial in-memory, ownership, or cache state remains on persistence failure
        for res in sanitized_results:
            reviews_store.pop(res.review_id, None)
            _review_owners.pop(res.review_id, None)
            await cache_manager.delete_review(res.review_id)
        raise

    # Store in memory and launch background child findings persistence ONLY after core persistence succeeds
    for res in sanitized_results:
        _store_review(res.review_id, res, owner_id=tenant_id)
        _create_background_task(_persist_detailed_findings(res, owner_id=tenant_id))

    return BatchReviewResponse(
        batch_id=f"batch_{uuid.uuid4().hex[:12]}",
        total_files=len(sanitized_results),
        reviews=sanitized_results,
    )


@router.post("/zip", response_model=ZipReviewResponse, status_code=status.HTTP_200_OK)
@router.post("/upload-zip", response_model=ZipReviewResponse, status_code=status.HTTP_200_OK)
async def upload_zip_review(
    http_req: Request,
    file: UploadFile = File(..., description="ZIP archive containing source code"),
    project_name: Optional[str] = Form(None, description="Optional project name"),
    agents: Optional[str] = Form(None, description="Comma-separated agents to run"),
    blocking: bool = Form(False, description="Enable blocking mode"),
    api_key: str = Depends(verify_api_key),
):
    """
    Upload and review an entire project packaged as a .zip file.
    Streams upload chunk-by-chunk and enforces byte caps before loading into memory.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Uploaded file must have a .zip extension.")

    max_bytes = getattr(settings, "MAX_ZIP_UPLOAD_BYTES", 25 * 1024 * 1024)
    chunks: List[bytes] = []
    total_read = 0
    chunk_size = 64 * 1024  # 64 KB

    try:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total_read += len(chunk)
            if total_read > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"Uploaded ZIP file exceeds maximum allowed size of {max_bytes} bytes.",
                )
            chunks.append(chunk)

        zip_bytes = b"".join(chunks)
        if not zip_bytes:
            raise HTTPException(status_code=400, detail="Uploaded ZIP file is empty.")

        agents_list = [a.strip() for a in agents.split(",") if a.strip()] if agents else None
        cfg = ReviewConfig(blocking_mode=blocking)
        p_name = project_name or Path(file.filename).stem

        response = await orchestrator.execute_zip_review(
            zip_source=zip_bytes, project_name=p_name, agents=agents_list, config=cfg
        )

        tenant_id = getattr(http_req.state, "tenant_id", "default")
        _store_zip_review(response.review_id, response, owner_id=tenant_id)
        for fr in response.file_reviews:
            _store_review(fr.review_id, fr.review, owner_id=tenant_id)

        return response
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as e:
        logger.exception("Error processing ZIP review: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process ZIP review. Ensure archive is valid and uncorrupted.",
        ) from e


@router.post("/zip-base64", response_model=ZipReviewResponse, status_code=status.HTTP_200_OK)
async def review_zip_base64(
    request: ZipBase64ReviewRequest,
    http_req: Request,
    api_key: str = Depends(verify_api_key),
):
    """
    Review a project from base64-encoded ZIP data.
    Validates payload size and base64 character set strictly before decoding.
    """
    raw_b64 = (request.zip_base64 or "").strip()
    if not raw_b64:
        raise HTTPException(status_code=400, detail="Base64 ZIP content cannot be empty.")

    max_bytes = getattr(settings, "MAX_ZIP_UPLOAD_BYTES", 25 * 1024 * 1024)
    # Estimated decoded size: len * 3 / 4
    estimated_size = (len(raw_b64) * 3) // 4
    if estimated_size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Base64 ZIP payload exceeds maximum allowed size of {max_bytes} bytes.",
        )

    try:
        # Strict base64 character set validation
        if not re.fullmatch(r"^[A-Za-z0-9+/=\r\n]+$", raw_b64):
            raise ValueError("Malformed base64: invalid characters detected in encoding.")

        zip_bytes = base64.b64decode(raw_b64, validate=True)
        if not zip_bytes:
            raise HTTPException(status_code=400, detail="Decoded ZIP content is empty.")

        cfg = ReviewConfig(blocking_mode=request.blocking or False)
        response = await orchestrator.execute_zip_review(
            zip_source=zip_bytes,
            project_name=request.project_name or "uploaded_project",
            agents=request.agents,
            config=cfg,
        )

        tenant_id = getattr(http_req.state, "tenant_id", "default")
        _store_zip_review(response.review_id, response, owner_id=tenant_id)
        for fr in response.file_reviews:
            _store_review(fr.review_id, fr.review, owner_id=tenant_id)

        return response
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as e:
        logger.exception("Error processing base64 ZIP review: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process base64 ZIP review. Ensure base64 encoding and archive format are valid.",
        ) from e


@router.get("/zip/{zip_review_id}", response_model=ZipReviewResponse)
async def get_zip_review(
    zip_review_id: str,
    http_req: Request,
    api_key: str = Depends(verify_api_key),
):
    """Retrieve full synthesized report of an uploaded project ZIP review with tenant isolation."""
    tenant_id = getattr(http_req.state, "tenant_id", None)
    is_platform_admin = getattr(http_req.state, "is_platform_admin", False)

    if zip_review_id in zip_reviews_store:
        zip_reviews_store.move_to_end(zip_review_id)
        owner = await _resolve_zip_review_owner(zip_review_id)
        if owner and not is_platform_admin and tenant_id and owner != tenant_id:
            raise HTTPException(status_code=404, detail=f"Project review '{zip_review_id}' was not found.")
        return zip_reviews_store[zip_review_id]

    raise HTTPException(status_code=404, detail=f"Project review '{zip_review_id}' was not found.")


@router.get("/zip/{zip_review_id}/sonarqube", response_class=JSONResponse)
async def get_zip_review_sonarqube(
    zip_review_id: str,
    http_req: Request,
    api_key: str = Depends(verify_api_key),
):
    """Export full project ZIP review findings in SonarQube Generic Issue Import format."""
    zip_resp = await get_zip_review(zip_review_id, http_req, api_key)
    sonar_data = zip_review_response_to_sonarqube(zip_resp)
    return JSONResponse(
        content=sonar_data,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=sonar-generic-issues-{zip_review_id}.json"},
    )


@router.get("/zip/{zip_review_id}/gitlab", response_class=JSONResponse)
async def get_zip_review_gitlab(
    zip_review_id: str,
    http_req: Request,
    api_key: str = Depends(verify_api_key),
):
    """Export full project ZIP review findings in GitLab CI Code Quality format."""
    zip_resp = await get_zip_review(zip_review_id, http_req, api_key)
    gl_data = zip_review_response_to_gitlab_code_quality(zip_resp)
    return JSONResponse(
        content=gl_data,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=gl-code-quality-report-{zip_review_id}.json"},
    )


@router.post("/{review_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    review_id: str,
    feedback: FeedbackRequest,
    http_req: Request,
    api_key: str = Depends(verify_api_key),
):
    """Submit developer feedback and rating for a completed review with tenant ownership validation."""
    await get_review_status(review_id, http_req, api_key)
    tenant_id = getattr(http_req.state, "tenant_id", "default")
    try:
        async with AsyncSessionLocal() as session:
            record = ReviewFeedbackRecord(
                review_id=review_id,
                owner_id=tenant_id,
                user_id=api_key,
                rating=feedback.rating,
                is_helpful=feedback.is_helpful,
                false_positives=feedback.false_positives,
                false_negatives=feedback.false_negatives,
                comments=feedback.comments,
            )
            session.add(record)
            await session.commit()
    except Exception as e:
        logger.warning("Could not persist feedback: %s", e)

    return FeedbackResponse(status="success", message="Feedback recorded. Thank you for improving Cerberus.")


@router.websocket("/{review_id}/ws")
async def websocket_review_stream(
    websocket: WebSocket,
    review_id: str,
    stream_token: Optional[str] = Query(None, description="Scoped one-time stream token"),
    token: Optional[str] = Query(None, description="Forbidden raw API key query parameter"),
):
    """
    Live WebSocket stream broadcasting agent lifecycle events and progress across workers.
    Rejects raw API keys in query parameters across ALL environments.
    Accepts scoped one-time stream tokens or Bearer Authorization headers with review ownership verification.
    """
    if token:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Raw API keys in query parameters are forbidden. Generate a stream token via POST /{review_id}/stream-token or use the Authorization header.",
        )
        return

    auth_header = websocket.headers.get("authorization")
    raw_key = None
    if auth_header and auth_header.lower().startswith("bearer "):
        raw_key = auth_header.split(" ", 1)[1].strip()

    tenant_id: Optional[str] = None
    is_platform_admin = False

    if stream_token:
        token_data = await cache_manager.consume_stream_token(stream_token)
        if token_data and token_data.get("review_id") == review_id:
            tenant_id = token_data.get("tenant_id")
        else:
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid, expired, or already-consumed stream token.",
            )
            return
    elif raw_key:
        key_record = await get_key_record_for_token(raw_key)
        if key_record:
            tenant_id = key_record.tenant_id
            scopes = set(key_record.scopes.split(",")) if key_record.scopes else set()
            is_dev_mode = settings.ENVIRONMENT.lower() not in ("production", "prod")
            is_platform_admin = ("platform:admin" in scopes) or bool(
                is_dev_mode
                and settings.DEFAULT_DEV_API_KEY
                and timing_safe_compare(raw_key, settings.DEFAULT_DEV_API_KEY)
            )
        else:
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid API key in Authorization header.",
            )
            return
    else:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Authentication required. Provide Authorization header or scoped ?stream_token=.",
        )
        return

    # Enforce tenant ownership of target review
    owner_id: Optional[str] = await _resolve_review_owner(review_id)
    if owner_id and not is_platform_admin and tenant_id and owner_id != tenant_id:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Review not found or unauthorized.",
        )
        return

    await websocket.accept()
    if review_id not in ws_connections:
        ws_connections[review_id] = []
    ws_connections[review_id].append(websocket)

    try:
        await websocket.send_text(
            json.dumps(
                {
                    "event": "connected",
                    "review_id": review_id,
                    "message": "Subscribed to live agent updates.",
                }
            )
        )

        # If already completed in local store or DB, send completed event immediately
        res = await _lookup_review_response(review_id)
        if res and res.status in ("completed", "approved", "failed"):
            await websocket.send_text(
                json.dumps(
                    {
                        "event": "review_completed",
                        "review_id": review_id,
                        "overall_score": res.overall_score,
                        "status": res.status,
                    }
                )
            )

        # Forward Redis pub/sub events to WebSocket in real-time across multiple workers
        async def _forward_pubsub_events():
            async for evt in cache_manager.subscribe_review_events(review_id, timeout_seconds=60.0):
                try:
                    await websocket.send_text(json.dumps(evt))
                    if evt.get("event") in ("review_completed", "completed"):
                        break
                except Exception:
                    break
            # Fallback if pubsub ended without completion event
            final_res = await _lookup_review_response(review_id)
            if final_res and final_res.status in ("completed", "approved", "failed"):
                try:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "event": "review_completed",
                                "review_id": review_id,
                                "overall_score": final_res.overall_score,
                                "status": final_res.status,
                            }
                        )
                    )
                except Exception:
                    pass

        pubsub_task = asyncio.create_task(_forward_pubsub_events())
        try:
            while True:
                await websocket.receive_text()
        finally:
            pubsub_task.cancel()
            try:
                await pubsub_task
            except (asyncio.CancelledError, Exception):
                pass
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if review_id in ws_connections:
            if websocket in ws_connections[review_id]:
                ws_connections[review_id].remove(websocket)
            if not ws_connections[review_id]:
                del ws_connections[review_id]


async def _persist_review_synchronous_core(
    request: CodeReviewRequest,
    response: CodeReviewResponse,
    owner_id: Optional[str] = None,
    max_retries: int = 2,
    retry_delay: float = 0.05,
) -> None:
    """
    Synchronously persist the minimum retrieval-critical CodeReviewRecord to the database
    with retries before returning to the caller.
    Guarantees that any immediate memory eviction or cross-worker database lookup succeeds.
    Fails closed if the database write cannot be completed after retries.
    """
    retain = getattr(settings, "RETAIN_SOURCE_CODE", False)
    results_dump = response.model_dump() if hasattr(response, "model_dump") else dict(response)
    if not retain:
        results_dump = redact_source_code_recursively(results_dump)

    snippet_to_store = "[REDACTED]" if not retain else (request.code[:2000] if request.code else "")

    last_error: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            async with AsyncSessionLocal() as session:
                existing = await session.get(CodeReviewRecord, response.review_id)
                if not existing:
                    review_rec = CodeReviewRecord(
                        id=response.review_id,
                        owner_id=owner_id,
                        code_snippet=snippet_to_store,
                        language=request.language or "python",
                        status=response.status,
                        overall_score=response.overall_score,
                        processing_time_ms=response.processing_time_ms,
                        results_json=results_dump,
                    )
                    session.add(review_rec)
                    await session.commit()
                return
        except Exception as e:
            last_error = e
            logger.warning(
                "Sync review persist attempt %s/%s failed for %s: %s",
                attempt + 1,
                max_retries + 1,
                response.review_id,
                e,
            )
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * (2**attempt))

    logger.error(
        "Failed to synchronously persist critical review record %s after %s attempts: %s",
        response.review_id,
        max_retries + 1,
        last_error,
    )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "error": "persistence_failure",
            "message": "Failed to persist review record to durable storage.",
        },
    )


async def _persist_batch_reviews_synchronous_core(
    pairs: List[Tuple[CodeReviewRequest, CodeReviewResponse]],
    owner_id: Optional[str] = None,
    max_retries: int = 2,
    retry_delay: float = 0.05,
) -> None:
    """Synchronously persist a batch of core review records in a single transactional session with retry."""
    retain = getattr(settings, "RETAIN_SOURCE_CODE", False)
    records_to_add: List[CodeReviewRecord] = []
    for req, resp in pairs:
        snippet_to_store = (
            "[REDACTED_SOURCE_CODE]"
            if not retain
            else (req.code if len(req.code) <= 10000 else req.code[:10000] + "\n...[truncated]")
        )
        results_dump = redact_source_code_recursively(resp.model_dump()) if not retain else resp.model_dump()
        records_to_add.append(
            CodeReviewRecord(
                id=resp.review_id,
                owner_id=owner_id,
                code_snippet=snippet_to_store,
                language=req.language or "python",
                status=resp.status,
                overall_score=resp.overall_score,
                processing_time_ms=resp.processing_time_ms,
                results_json=results_dump,
            )
        )

    seen_ids: Set[str] = set()
    deduped_records: List[CodeReviewRecord] = []
    for rec in records_to_add:
        if rec.id and rec.id not in seen_ids:
            seen_ids.add(rec.id)
            deduped_records.append(rec)

    last_error: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    for rec in deduped_records:
                        await session.merge(rec)
                return
        except Exception as e:
            last_error = e
            logger.warning(
                "Sync batch review persist attempt %s/%s failed for %s records: %s",
                attempt + 1,
                max_retries + 1,
                len(records_to_add),
                e,
            )
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * (2**attempt))

    logger.error(
        "Failed to synchronously persist batch review records after %s attempts: %s", max_retries + 1, last_error
    )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "error": "persistence_failure",
            "message": "Failed to persist batch review records to durable storage.",
        },
    )


async def _persist_detailed_findings(
    response: CodeReviewResponse,
    owner_id: Optional[str] = None,
) -> None:
    """Asynchronously persist individual child finding records to database."""
    try:
        retain = getattr(settings, "RETAIN_SOURCE_CODE", False)
        async with AsyncSessionLocal() as session:
            for f in response.critical_issues + response.warnings + response.suggestions:
                finding_rec = FindingRecord(
                    review_id=response.review_id,
                    owner_id=owner_id,
                    agent_name=f.category,
                    severity=f.severity.value if hasattr(f.severity, "value") else str(f.severity),
                    category=f.category,
                    title=f.title,
                    message=f.message,
                    line_number=f.line,
                    code_snippet=f.code_snippet if retain else None,
                    remediation=f.recommendation,
                    suggestion=f.suggestion if retain else None,
                    cwe_id=f.cwe_id,
                    cvss_score=f.cvss_score,
                )
                session.add(finding_rec)

            await session.commit()
    except Exception as e:
        logger.warning("Database background write error for findings: %s", e)


async def _persist_review_record(
    request: CodeReviewRequest, response: CodeReviewResponse, owner_id: Optional[str] = None
) -> None:
    """Persist review core synchronously and findings asynchronously."""
    await _persist_review_synchronous_core(request, response, owner_id=owner_id)
    await _persist_detailed_findings(response, owner_id=owner_id)
