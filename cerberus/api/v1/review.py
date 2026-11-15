"""
Code Review Endpoints: Single, Batch, Status, Results, Feedback, and WebSocket.
"""

import asyncio
import base64
import json
import logging
from pathlib import Path
import re
import time
from datetime import datetime, timezone
import uuid
from collections import OrderedDict
from typing import Dict, List, Optional
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import JSONResponse, StreamingResponse
from cerberus.agents.orchestrator import orchestrator
from cerberus.api.dependencies import require_scopes, validate_token_against_db, verify_api_key
from cerberus.config import settings
from cerberus.core.database import AsyncSessionLocal
from cerberus.core.sarif import (
    review_response_to_gitlab_code_quality,
    review_response_to_sarif,
    review_response_to_sonarqube,
    zip_review_response_to_gitlab_code_quality,
    zip_review_response_to_sarif,
    zip_review_response_to_sonarqube,
)
from cerberus.core.security import verify_github_signature
from cerberus.core.github_app import (
    parse_pull_request_event,
    build_pr_review_payload,
    post_pr_review_to_github
)
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
ws_connections: Dict[str, List[WebSocket]] = {}
_webhook_deliveries: OrderedDict[str, float] = OrderedDict()
MAX_WEBHOOK_PAYLOAD_BYTES = 10 * 1024 * 1024  # 10 MB cap
DELIVERY_IDEMPOTENCY_TTL_SECONDS = 600  # 10 minutes

# Strong reference tracking for background tasks to prevent GC in Python 3.11+
_background_tasks: set = set()


def _create_background_task(coro) -> asyncio.Task:
    """Creates a background task and retains a strong reference until completion."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def _store_review(review_id: str, response: CodeReviewResponse) -> None:
    """Store review in bounded OrderedDict with LRU eviction."""
    if review_id in reviews_store:
        reviews_store.move_to_end(review_id)
    else:
        while len(reviews_store) >= REVIEWS_STORE_MAX_ITEMS and reviews_store:
            reviews_store.popitem(last=False)
    reviews_store[review_id] = response


def _store_zip_review(review_id: str, response: ZipReviewResponse) -> None:
    """Store project zip review in bounded OrderedDict with LRU eviction."""
    if review_id in zip_reviews_store:
        zip_reviews_store.move_to_end(review_id)
    else:
        while len(zip_reviews_store) >= REVIEWS_STORE_MAX_ITEMS and zip_reviews_store:
            zip_reviews_store.popitem(last=False)
    zip_reviews_store[review_id] = response


@router.post("", response_model=CodeReviewResponse, status_code=status.HTTP_200_OK)
async def submit_review(
    request: CodeReviewRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Submit source code for multi-agent review across Security, Performance, and Quality.
    """
    if not request.code or not request.code.strip():
        raise HTTPException(status_code=400, detail="Source code snippet cannot be empty")

    response = await orchestrator.execute_review(request)
    _store_review(response.review_id, response)

    # Persist in background DB with strong reference tracking
    _create_background_task(_persist_review_record(request, response))

    # Notify connected WebSockets
    if response.review_id in ws_connections:
        active_sockets = list(ws_connections[response.review_id])
        for ws in active_sockets:
            try:
                await ws.send_text(json.dumps({
                    "event": "review_completed",
                    "review_id": response.review_id,
                    "overall_score": response.overall_score
                }))
            except Exception:
                if ws in ws_connections.get(response.review_id, []):
                    ws_connections[response.review_id].remove(ws)
        if response.review_id in ws_connections and not ws_connections[response.review_id]:
            del ws_connections[response.review_id]

    return response


@router.get("/{review_id}", response_model=CodeReviewResponse)
async def get_review_status(
    review_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Get the current processing status and summary of a review."""
    if review_id in reviews_store:
        reviews_store.move_to_end(review_id)
        return reviews_store[review_id]

    # Check database fallback
    try:
        async with AsyncSessionLocal() as session:
            record = await session.get(CodeReviewRecord, review_id)
            if record and record.results_json:
                results_data = record.results_json
                if isinstance(results_data, str):
                    results_data = json.loads(results_data)
                if isinstance(results_data, dict):
                    response = CodeReviewResponse(**results_data)
                    _store_review(review_id, response)
                    return response
    except Exception as e:
        logger.warning(f"DB lookup failed for {review_id}: {e}")

    raise HTTPException(status_code=404, detail=f"Review with ID '{review_id}' was not found.")


@router.get("/{review_id}/results", response_model=CodeReviewResponse)
async def get_review_results(
    review_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Retrieve full synthesized results, agent findings, and remediation suggestions."""
    return await get_review_status(review_id, api_key)


@router.get("/{review_id}/sarif", response_class=JSONResponse)
async def get_review_sarif(
    review_id: str,
    api_key: str = Depends(verify_api_key)
):
    """
    Export review findings in OASIS SARIF v2.1.0 standard format.
    Enables native ingestion by GitHub Code Scanning and CI/CD security gates.
    """
    full = await get_review_status(review_id, api_key)
    filename = full.results.get("filename") if isinstance(full.results, dict) else "snippet.py"
    sarif_data = review_response_to_sarif(full, filename=filename)
    return JSONResponse(
        content=sarif_data,
        media_type="application/sarif+json",
        headers={"Content-Disposition": f"attachment; filename=cerberus-{review_id}.sarif"}
    )


@router.get("/{review_id}/gitlab", response_class=JSONResponse)
async def get_review_gitlab_code_quality(
    review_id: str,
    api_key: str = Depends(verify_api_key)
):
    """
    Export review findings in standard GitLab CI Code Quality format (gl-code-quality-report.json).
    Enables native MR widget integration in GitLab CI/CD pipelines.
    """
    full = await get_review_status(review_id, api_key)
    filename = full.results.get("filename") if isinstance(full.results, dict) else "snippet.py"
    gl_data = review_response_to_gitlab_code_quality(full, filename=filename)
    return JSONResponse(
        content=gl_data,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=gl-code-quality-report-{review_id}.json"}
    )


@router.get("/{review_id}/sonarqube", response_class=JSONResponse)
async def get_review_sonarqube(
    review_id: str,
    api_key: str = Depends(verify_api_key)
):
    """
    Export review findings in standard SonarQube Generic Issue Import format (sonar-generic-issues.json).
    Enables native dashboard ingestion in enterprise SonarQube and SonarCloud instances.
    """
    full = await get_review_status(review_id, api_key)
    filename = full.results.get("filename") if isinstance(full.results, dict) else "snippet.py"
    sonar_data = review_response_to_sonarqube(full, filename=filename)
    return JSONResponse(
        content=sonar_data,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=sonar-generic-issues-{review_id}.json"}
    )


@router.post("/webhooks/github")
async def handle_github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: str = Header("pull_request"),
    x_github_delivery: Optional[str] = Header(None)
):
    """
    Native GitHub Actions and GitHub App Webhook Event Ingestion.
    Validates X-Hub-Signature-256 HMAC signature against configured secret,
    prevents duplicate replay deliveries, processes pull_request events,
    generates line-anchored review comments, and submits reviews to the GitHub API.
    """
    raw_body = await request.body()
    if len(raw_body) > MAX_WEBHOOK_PAYLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"error": "payload_too_large", "message": f"Webhook payload exceeds {MAX_WEBHOOK_PAYLOAD_BYTES} bytes cap."}
        )

    # 1. Secret Determination & Production Verification
    is_prod = settings.ENVIRONMENT.lower() in ("production", "prod")
    if is_prod:
        if not settings.GITHUB_WEBHOOK_SECRET or settings.GITHUB_WEBHOOK_SECRET in (
            "cerberus_dev_secret_key_change_in_production_32chars",
            "secret",
            "changeme",
            "password",
            "admin"
        ):
            logger.error("Production misconfiguration: GITHUB_WEBHOOK_SECRET is not securely set.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "misconfigured_secret", "message": "GITHUB_WEBHOOK_SECRET is required and must be configured in production."}
            )
        secret = settings.GITHUB_WEBHOOK_SECRET
    else:
        secret = settings.GITHUB_WEBHOOK_SECRET or settings.SECRET_KEY

    # 2. Strict Signature Enforcement
    # Require signature in production or whenever GITHUB_WEBHOOK_SECRET is configured
    if is_prod or settings.GITHUB_WEBHOOK_SECRET:
        if not x_hub_signature_256:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing required X-Hub-Signature-256 HMAC signature header"
            )

    if x_hub_signature_256:
        is_valid = verify_github_signature(raw_body, x_hub_signature_256, secret)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid GitHub X-Hub-Signature-256 HMAC signature"
            )

    # 3. Replay Protection via X-GitHub-Delivery
    if x_github_delivery:
        now = time.time()
        stale_threshold = now - DELIVERY_IDEMPOTENCY_TTL_SECONDS
        while _webhook_deliveries and next(iter(_webhook_deliveries.values())) < stale_threshold:
            _webhook_deliveries.popitem(last=False)

        if x_github_delivery in _webhook_deliveries:
            logger.info(f"Duplicate webhook delivery detected and ignored: {x_github_delivery}")
            return {
                "status": "ignored",
                "reason": "duplicate_event",
                "delivery_id": x_github_delivery,
                "message": f"Webhook delivery '{x_github_delivery}' was already processed."
            }
        _webhook_deliveries[x_github_delivery] = now

    # 4. Safe JSON Parsing
    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "malformed_json", "message": "Invalid JSON payload in webhook request"}
        )

    # 5. Event Type Validation
    event_normalized = (x_github_event or "").strip().lower()
    if event_normalized not in ("pull_request", "ping"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "unsupported_event", "message": f"Webhook event '{x_github_event}' is not supported."}
        )

    # Handle Ping Event
    if event_normalized == "ping":
        return {
            "status": "pong",
            "zen": "Keep it logically awesome.",
            "hook_id": payload.get("hook_id", 0)
        }

    # 6. Parse Pull Request Context & Supported Actions
    pr_info = parse_pull_request_event(payload)
    action = (pr_info.action if pr_info else payload.get("action", "opened")).lower()

    if action not in ("opened", "synchronize", "reopened"):
        return {
            "status": "ignored",
            "action": action,
            "message": f"Pull request action '{action}' is ignored; only opened, synchronize, and reopened trigger reviews."
        }

    # Determine code to review
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
        # Check if PR body contains markdown code block
        body_text = pr_info.body or ""
        code_block_match = re.search(r"```(?:\w+)?\s*\n([\s\S]*?)\n```", body_text)
        if code_block_match:
            code_to_review = code_block_match.group(1).strip()
        elif body_text.strip():
            # Fallback if body text is provided as direct snippet
            code_to_review = body_text.strip()
        elif pr_info.title:
            code_to_review = ""

    if not code_to_review:
        return {
            "status": "ignored",
            "message": f"Webhook received for event '{x_github_event}' (action: '{action}') with no reviewable code content."
        }

    language = payload.get("language") or detect_language_from_path(filename) or "python"

    review_req = CodeReviewRequest(
        code=code_to_review,
        filename=filename,
        language=language,
        config=ReviewConfig(blocking_mode=True),
        context={"is_webhook": True, "event": x_github_event, "action": action}
    )
    result = await orchestrator.execute_review(review_req)
    _store_review(result.review_id, result)
    asyncio.create_task(_persist_review_record(review_req, result))

    # Build official GitHub PR review payload
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
        github_comments = fixer.generate_pr_review_comments(all_findings, filename=filename) if hasattr(fixer, "generate_pr_review_comments") else []

    verdict = result.collaborative_consensus.get("pr_action", "MERGE_READY") if result.collaborative_consensus else "MERGE_READY"
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
        "summary": result.summary or f"Cerberus analyzed {filename}: Score {result.overall_score}/100"
    }


@router.get("/{review_id}/status", response_model=ReviewStatusResponse)
async def get_review_status_only(
    review_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Get lightweight status and blocking evaluation for automated gating."""
    full = await get_review_status(review_id, api_key)
    return ReviewStatusResponse(
        review_id=full.review_id,
        status=full.status,
        overall_score=full.overall_score,
        created_at=full.created_at,
        completed_at=full.completed_at,
        should_block=full.should_block,
        block_reason=full.block_reason
    )


@router.post("/{review_id}/approve", response_model=ReviewApproveResponse)
async def approve_review(
    review_id: str,
    payload: Optional[ReviewApproveRequest] = None,
    api_key: str = Depends(require_scopes("review:write"))
):
    """
    Human-in-the-Loop PR Approval Gate.
    Allows engineers or technical leads to explicitly approve a review,
    overriding automated blocking thresholds when deliberate exceptions are justified.
    """
    full = await get_review_status(review_id, api_key)
    req = payload or ReviewApproveRequest()
    now_iso = datetime.now(timezone.utc).isoformat()

    # Update in-memory review state
    if full.should_block and req.override_blocking:
        full.should_block = False
        full.block_reason = f"Manually approved by '{req.reviewer}'. Overrode blocking rule: {full.block_reason}"
    full.status = "approved"
    _store_review(review_id, full)

    # Persist in DB if available
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
        logger.warning(f"Could not persist review approval to DB: {e}")

    return ReviewApproveResponse(
        review_id=review_id,
        status="approved",
        approved_by=req.reviewer,
        approved_at=now_iso,
        override_applied=req.override_blocking,
        message=f"Review '{review_id}' successfully approved for merge by {req.reviewer}."
    )


@router.get("/{review_id}/stream")
async def stream_review_sse(
    review_id: str,
    token: Optional[str] = Query(None)
):
    """
    Server-Sent Events (SSE) progress and completion stream for CI/CD runners and dashboard.
    """
    is_valid = await validate_token_against_db(token)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid or missing API key token")

    async def event_generator():
        # Yield connection event
        yield f"event: connected\ndata: {json.dumps({'review_id': review_id, 'status': 'connected'})}\n\n"
        
        # Check if already completed
        if review_id in reviews_store:
            res = reviews_store[review_id]
            yield f"event: completed\ndata: {json.dumps({'review_id': review_id, 'overall_score': res.overall_score, 'status': res.status})}\n\n"
            return

        # Poll briefly until completed
        for _ in range(30):
            await asyncio.sleep(0.5)
            if review_id in reviews_store:
                res = reviews_store[review_id]
                yield f"event: completed\ndata: {json.dumps({'review_id': review_id, 'overall_score': res.overall_score, 'status': res.status})}\n\n"
                return
        yield f"event: ping\ndata: {json.dumps({'review_id': review_id, 'status': 'waiting'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/batch", response_model=BatchReviewResponse)
async def batch_review(
    request: BatchReviewRequest,
    api_key: str = Depends(verify_api_key)
):
    """Submit multiple files or snippets for concurrent batch code review."""
    if len(request.files) > settings.MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size {len(request.files)} exceeds maximum allowed of {settings.MAX_BATCH_SIZE}"
        )

    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_BATCH_REVIEWS)

    async def _throttled_review(req):
        async with semaphore:
            return await orchestrator.execute_review(req)

    results: List[CodeReviewResponse] = await asyncio.gather(*[_throttled_review(req) for req in request.files])

    for res in results:
        _store_review(res.review_id, res)

    return BatchReviewResponse(
        batch_id=f"batch_{uuid.uuid4().hex[:12]}",
        total_files=len(results),
        reviews=results
    )


@router.post("/zip", response_model=ZipReviewResponse, status_code=status.HTTP_200_OK)
@router.post("/upload-zip", response_model=ZipReviewResponse, status_code=status.HTTP_200_OK)
async def upload_zip_review(
    file: UploadFile = File(..., description="ZIP archive containing source code"),
    project_name: Optional[str] = Form(None, description="Optional project name"),
    agents: Optional[str] = Form(None, description="Comma-separated agents to run"),
    blocking: bool = Form(False, description="Enable blocking mode"),
    api_key: str = Depends(verify_api_key)
):
    """
    Upload and review an entire project packaged as a .zip file.
    Extracts all supported source files and runs multi-agent reviews in parallel.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Uploaded file must have a .zip extension.")

    try:
        zip_bytes = await file.read()
        if not zip_bytes:
            raise HTTPException(status_code=400, detail="Uploaded ZIP file is empty.")

        agents_list = [a.strip() for a in agents.split(",") if a.strip()] if agents else None
        cfg = ReviewConfig(blocking_mode=blocking)
        p_name = project_name or Path(file.filename).stem

        response = await orchestrator.execute_zip_review(
            zip_source=zip_bytes,
            project_name=p_name,
            agents=agents_list,
            config=cfg
        )

        _store_zip_review(response.review_id, response)
        for fr in response.file_reviews:
            _store_review(fr.review_id, fr.review)

        return response
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception(f"Error processing ZIP review: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process ZIP review: {str(e)}")


@router.post("/zip-base64", response_model=ZipReviewResponse, status_code=status.HTTP_200_OK)
async def review_zip_base64(
    request: ZipBase64ReviewRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Review a project from base64-encoded ZIP data.
    Useful for automated CI/CD and direct JSON API integrations.
    """
    try:
        zip_bytes = base64.b64decode(request.zip_base64)
        if not zip_bytes:
            raise HTTPException(status_code=400, detail="Decoded ZIP content is empty.")

        cfg = ReviewConfig(blocking_mode=request.blocking or False)
        response = await orchestrator.execute_zip_review(
            zip_source=zip_bytes,
            project_name=request.project_name or "uploaded_project",
            agents=request.agents,
            config=cfg
        )

        _store_zip_review(response.review_id, response)
        for fr in response.file_reviews:
            _store_review(fr.review_id, fr.review)

        return response
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception(f"Error processing base64 ZIP review: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process base64 ZIP review: {str(e)}")


@router.get("/zip/{zip_review_id}", response_model=ZipReviewResponse)
async def get_zip_review(
    zip_review_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Retrieve full synthesized report of an uploaded project ZIP review."""
    if zip_review_id in zip_reviews_store:
        zip_reviews_store.move_to_end(zip_review_id)
        return zip_reviews_store[zip_review_id]
    raise HTTPException(status_code=404, detail=f"Project review '{zip_review_id}' was not found.")


@router.get("/zip/{zip_review_id}/sonarqube", response_class=JSONResponse)
async def get_zip_review_sonarqube(
    zip_review_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Export full project ZIP review findings in SonarQube Generic Issue Import format."""
    zip_resp = await get_zip_review(zip_review_id, api_key)
    sonar_data = zip_review_response_to_sonarqube(zip_resp)
    return JSONResponse(
        content=sonar_data,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=sonar-generic-issues-{zip_review_id}.json"}
    )


@router.get("/zip/{zip_review_id}/gitlab", response_class=JSONResponse)
async def get_zip_review_gitlab(
    zip_review_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Export full project ZIP review findings in GitLab CI Code Quality format."""
    zip_resp = await get_zip_review(zip_review_id, api_key)
    gl_data = zip_review_response_to_gitlab_code_quality(zip_resp)
    return JSONResponse(
        content=gl_data,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=gl-code-quality-report-{zip_review_id}.json"}
    )


@router.post("/{review_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    review_id: str,
    feedback: FeedbackRequest,
    api_key: str = Depends(verify_api_key)
):
    """Submit developer feedback and rating for a completed review."""
    try:
        async with AsyncSessionLocal() as session:
            record = ReviewFeedbackRecord(
                review_id=review_id,
                user_id=api_key,
                rating=feedback.rating,
                is_helpful=feedback.is_helpful,
                false_positives=feedback.false_positives,
                false_negatives=feedback.false_negatives,
                comments=feedback.comments
            )
            session.add(record)
            await session.commit()
    except Exception as e:
        logger.warning(f"Could not persist feedback: {e}")

    return FeedbackResponse(status="success", message="Feedback recorded. Thank you for improving Cerberus.")


@router.websocket("/{review_id}/ws")
async def websocket_review_stream(
    websocket: WebSocket,
    review_id: str,
    token: Optional[str] = Query(None)
):
    """Live WebSocket stream broadcasting agent lifecycle events and progress."""
    auth_header = websocket.headers.get("authorization")
    raw_token = token
    if not raw_token and auth_header and auth_header.startswith("Bearer "):
        raw_token = auth_header.split(" ", 1)[1].strip()

    is_valid = await validate_token_against_db(raw_token)
    if not is_valid:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or missing API key")
        return

    await websocket.accept()
    if review_id not in ws_connections:
        ws_connections[review_id] = []
    ws_connections[review_id].append(websocket)

    try:
        await websocket.send_text(json.dumps({
            "event": "connected",
            "review_id": review_id,
            "message": "Subscribed to live agent updates."
        }))
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if review_id in ws_connections:
            if websocket in ws_connections[review_id]:
                ws_connections[review_id].remove(websocket)
            if not ws_connections[review_id]:
                del ws_connections[review_id]


async def _persist_review_record(request: CodeReviewRequest, response: CodeReviewResponse) -> None:
    """Asynchronously persist review and findings to database."""
    try:
        async with AsyncSessionLocal() as session:
            review_rec = CodeReviewRecord(
                id=response.review_id,
                code_snippet=request.code[:2000],  # truncate if very large
                language=request.language or "python",
                status=response.status,
                overall_score=response.overall_score,
                processing_time_ms=response.processing_time_ms,
                results_json=response.model_dump(),
            )
            session.add(review_rec)

            # Add individual findings
            for f in response.critical_issues + response.warnings + response.suggestions:
                finding_rec = FindingRecord(
                    review_id=response.review_id,
                    agent_name=f.category,
                    severity=f.severity.value,
                    category=f.category,
                    title=f.title,
                    message=f.message,
                    line_number=f.line,
                    code_snippet=f.code_snippet,
                    remediation=f.recommendation,
                    suggestion=f.suggestion,
                    cwe_id=f.cwe_id,
                    cvss_score=f.cvss_score,
                )
                session.add(finding_rec)

            await session.commit()
    except Exception as e:
        logger.warning(f"Database background write error: {e}")
