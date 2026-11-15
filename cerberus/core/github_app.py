"""
Native GitHub App and Pull Request Webhook Automation Engine for cerberus</>.
Handles zero-click pull_request.opened event parsing, multi-agent review execution,
automated GitHub PR Review creation, and line-anchored review comment posting.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from cerberus.config import settings
from cerberus.models.schemas import (
    CodeReviewResponse,
    GitHubPRReviewComment,
    GitHubPRReviewPayload,
    GitHubPullRequestInfo,
)

logger = logging.getLogger("cerberus.core.github_app")


def parse_pull_request_event(payload: Dict[str, Any]) -> Optional[GitHubPullRequestInfo]:
    """
    Parses a GitHub webhook payload for pull_request events.
    Extracts PR metadata, target branch, and repository coordinates.
    """
    if "pull_request" not in payload:
        return None

    pr = payload["pull_request"]
    repo = payload.get("repository", {})
    owner = repo.get("owner", {}).get("login", "")
    repo_name = repo.get("name", "")
    full_name = repo.get("full_name", f"{owner}/{repo_name}")

    action = payload.get("action", "opened")
    number = payload.get("number") or pr.get("number", 0)

    head = pr.get("head", {})
    base = pr.get("base", {})

    return GitHubPullRequestInfo(
        action=action,
        pr_number=number,
        repo_name=repo_name,
        repo_owner=owner,
        full_name=full_name,
        title=pr.get("title", ""),
        body=pr.get("body") or "",
        head_sha=head.get("sha"),
        head_ref=head.get("ref"),
        base_ref=base.get("ref"),
        diff_url=pr.get("diff_url"),
        patch_url=pr.get("patch_url"),
        html_url=pr.get("html_url"),
    )


def build_pr_review_payload(
    review: CodeReviewResponse, pr_info: GitHubPullRequestInfo, filename: Optional[str] = None
) -> GitHubPRReviewPayload:
    """
    Constructs an official GitHub Pull Request Review payload with summary body
    and line-anchored review comments.
    """
    target_path = filename or "main.py"

    # Determine Review Action
    if review.should_block or (review.overall_score or 0) < 60:
        event = "REQUEST_CHANGES"
        verdict_badge = "🔴 **REQUEST CHANGES**"
    elif (review.overall_score or 0) >= 80:
        event = "APPROVE"
        verdict_badge = "🟢 **APPROVE**"
    else:
        event = "COMMENT"
        verdict_badge = "🟡 **COMMENT**"

    score_display = (
        int(review.overall_score)
        if (review.overall_score is not None and float(review.overall_score).is_integer())
        else review.overall_score
    )

    # Build Markdown Body
    body_lines = [
        "## 🛡️ cerberus</> Autonomous Multi-Agent Code Review",
        "",
        "| Quality Score | Verdict | Status | Review ID |",
        "| :---: | :---: | :---: | :---: |",
        f"| **{score_display} / 100** | {verdict_badge} | `{review.status.upper()}` | `{review.review_id}` |",
        "",
    ]

    if review.collaborative_consensus:
        cc = review.collaborative_consensus
        body_lines.extend(
            [
                "### 🤝 Project Consensus",
                f"- **Consensus Verdict:** `{cc.get('pr_action', 'N/A')}`",
                f"- **Synthesis:** {cc.get('summary', 'All agents completed analysis.')}",
                "",
            ]
        )

    all_findings = review.critical_issues + review.warnings + review.suggestions
    if all_findings:
        body_lines.append(f"### 🔍 Detected Findings ({len(all_findings)})")
        body_lines.append("")
        for f in all_findings:
            sev_emoji = "🚨" if f.severity.value == "critical" else ("⚠️" if f.severity.value == "high" else "ℹ️")
            line_str = f"Line {f.line}" if f.line else "Global"
            body_lines.append(f"- {sev_emoji} **[{f.severity.value.upper()}] {line_str}:** {f.title} — *{f.message}*")
            if f.recommendation:
                body_lines.append(f"  - **Remediation:** {f.recommendation}")
        body_lines.append("")

    if review.unified_patch:
        body_lines.extend(["### 🔧 Automated Multi-Agent Git Patch", "```diff", review.unified_patch, "```", ""])

    body_lines.append("---")
    body_lines.append("*Automated review conducted by cerberus</> multi-agent engine.*")
    markdown_body = "\n".join(body_lines)

    # Build line-anchored comments
    comments: List[GitHubPRReviewComment] = []
    for f in all_findings:
        if f.line and f.line > 0:
            c_body = f"**[{f.severity.value.upper()}] {f.title}**\n\n{f.message}"
            if f.recommendation:
                c_body += f"\n\n**Suggested Fix:**\n```suggestion\n{f.suggestion or f.recommendation}\n```"
            comments.append(GitHubPRReviewComment(path=target_path, line=f.line, body=c_body))

    return GitHubPRReviewPayload(commit_id=pr_info.head_sha, event=event, body=markdown_body, comments=comments)


async def post_pr_review_to_github(
    pr_info: GitHubPullRequestInfo, review_payload: GitHubPRReviewPayload, token: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Submits the automated review to the GitHub Pull Request Review API.
    POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews
    """
    auth_token = token or settings.GITHUB_TOKEN
    if not auth_token:
        logger.info("GITHUB_TOKEN not configured; skipping outbound GitHub API call.")
        return False, "GITHUB_TOKEN not configured"

    url = f"https://api.github.com/repos/{pr_info.repo_owner}/{pr_info.repo_name}/pulls/{pr_info.pr_number}/reviews"
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "cerberus-code-review-app",
    }

    payload_dict = {
        "body": review_payload.body,
        "event": review_payload.event,
        "comments": [c.model_dump() for c in review_payload.comments],
    }
    if review_payload.commit_id:
        payload_dict["commit_id"] = review_payload.commit_id

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload_dict, headers=headers)
            if resp.status_code in (200, 201):
                logger.info(f"Successfully posted PR review to {url} (HTTP {resp.status_code})")
                return True, None
            else:
                err_msg = f"GitHub API error ({resp.status_code}): {resp.text}"
                logger.warning(err_msg)
                return False, err_msg
    except Exception as e:
        err_msg = f"Failed to contact GitHub API: {str(e)}"
        logger.warning(err_msg)
        return False, err_msg


def build_github_check_run_payload(
    review: CodeReviewResponse, pr_info: GitHubPullRequestInfo, filename: Optional[str] = None
) -> Dict[str, Any]:
    """
    Constructs an official GitHub Check Run payload (GitHub Checks API).
    Includes line-level annotations for inline visual status badges on PR checks.
    """
    from cerberus.models.schemas import SeverityEnum

    target_path = filename or "main.py"
    all_findings = review.critical_issues + review.warnings + review.suggestions
    is_blocked = review.should_block or (review.overall_score or 0) < 60

    annotations = []
    for f in all_findings[:50]:  # GitHub Checks API caps annotations at 50 per batch
        level = (
            "failure"
            if f.severity in (SeverityEnum.CRITICAL, SeverityEnum.HIGH)
            else ("warning" if f.severity == SeverityEnum.MEDIUM else "notice")
        )
        annotations.append(
            {
                "path": target_path,
                "start_line": f.line or 1,
                "end_line": f.line or 1,
                "annotation_level": level,
                "message": f.message or f.title,
                "title": f.title,
                "raw_details": f.explanation or f.recommendation or "",
            }
        )

    return {
        "name": "cerberus</> Autonomous Multi-Agent QA",
        "head_sha": pr_info.head_sha or "HEAD",
        "status": "completed",
        "conclusion": "failure" if is_blocked else "success",
        "output": {
            "title": f"Cerberus Score: {review.overall_score}/100 — {'Blocked on Issues' if is_blocked else 'Approved'}",
            "summary": review.summary
            or "Multi-agent review completed across Security, Performance, Quality, Architecture, and Compliance.",
            "text": f"### Review ID: `{review.review_id}`\n\nTotal findings: {len(all_findings)}",
            "annotations": annotations,
        },
    }


async def post_check_run_to_github(
    pr_info: GitHubPullRequestInfo, check_run_payload: Dict[str, Any], token: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Submits the automated review to the GitHub Checks API (POST /repos/{owner}/{repo}/check-runs).
    Renders inline visual status badges and line annotations on GitHub PR checks.
    """
    auth_token = token or settings.GITHUB_TOKEN
    if not auth_token:
        logger.info("GITHUB_TOKEN not configured; skipping outbound GitHub Checks API call.")
        return False, "GITHUB_TOKEN not configured"

    url = f"https://api.github.com/repos/{pr_info.repo_owner}/{pr_info.repo_name}/check-runs"
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "cerberus-code-review-app",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=check_run_payload, headers=headers)
            if resp.status_code in (200, 201):
                logger.info(f"Successfully posted GitHub Check Run to {url} (HTTP {resp.status_code})")
                return True, None
            else:
                err_msg = f"GitHub Checks API error ({resp.status_code}): {resp.text}"
                logger.warning(err_msg)
                return False, err_msg
    except Exception as e:
        err_msg = f"Failed to contact GitHub Checks API: {str(e)}"
        logger.warning(err_msg)
        return False, err_msg
