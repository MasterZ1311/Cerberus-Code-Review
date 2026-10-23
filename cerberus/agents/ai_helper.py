"""
AI Analysis Helper for Cerberus Agents.
Provides robust LLM response parsing, finding normalization, deduplication, and score synthesis.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from cerberus.models.schemas import Finding, SeverityEnum

logger = logging.getLogger("cerberus.agents.ai_helper")


def parse_llm_json(raw_text: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Extracts and parses a JSON object from raw LLM output, handling markdown code fences,
    conversational preamble, trailing commas, and formatting quirks.
    """
    if not raw_text or not raw_text.strip():
        return None

    text = raw_text.strip()

    # 1. Extract content from markdown code fences if present (```json ... ``` or ``` ... ```)
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()
    else:
        # Find outermost { and }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]

    # 2. First attempt standard json.loads
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 3. Clean common LLM JSON syntax issues (trailing commas before } or ])
    cleaned = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.debug(f"Failed to parse LLM JSON: {e}. Raw text excerpt: {text[:200]}")

    return None


def build_findings_from_llm(
    raw_findings: List[Dict[str, Any]],
    agent_name: str,
    code: str,
) -> List[Finding]:
    """
    Converts raw finding dictionaries from LLM output into validated Finding schema models.
    """
    code_lines = code.split("\n")
    num_lines = len(code_lines)
    findings: List[Finding] = []

    severity_map = {
        "critical": SeverityEnum.CRITICAL,
        "crit": SeverityEnum.CRITICAL,
        "high": SeverityEnum.HIGH,
        "medium": SeverityEnum.MEDIUM,
        "med": SeverityEnum.MEDIUM,
        "warn": SeverityEnum.MEDIUM,
        "warning": SeverityEnum.MEDIUM,
        "low": SeverityEnum.LOW,
        "info": SeverityEnum.INFO,
        "informational": SeverityEnum.INFO,
    }

    for idx, rf in enumerate(raw_findings, 1):
        if not isinstance(rf, dict):
            continue

        raw_sev = str(rf.get("severity", "medium")).strip().lower()
        severity = severity_map.get(raw_sev, SeverityEnum.MEDIUM)

        line_num: Optional[int] = None
        raw_line = rf.get("line")
        if raw_line is not None:
            try:
                parsed_line = int(raw_line)
                if 1 <= parsed_line <= max(1, num_lines):
                    line_num = parsed_line
            except (ValueError, TypeError):
                line_num = None

        snippet = rf.get("code_snippet")
        if not snippet and line_num and line_num <= len(code_lines):
            snippet = code_lines[line_num - 1].strip()

        cvss_score = None
        if "cvss_score" in rf and rf["cvss_score"] is not None:
            try:
                cvss_score = round(float(rf["cvss_score"]), 1)
            except (ValueError, TypeError):
                pass

        exploitability = None
        if "exploitability" in rf and rf["exploitability"] is not None:
            try:
                exploitability = round(float(rf["exploitability"]), 2)
            except (ValueError, TypeError):
                pass

        findings.append(
            Finding(
                id=rf.get("id") or f"{agent_name.upper()}-AI-{idx}",
                severity=severity,
                category=str(rf.get("category") or agent_name).lower(),
                title=str(rf.get("title") or f"{agent_name.capitalize()} Finding").strip(),
                message=str(rf.get("message") or rf.get("description") or rf.get("title") or "").strip(),
                line=line_num,
                code_snippet=str(snippet).strip() if snippet else None,
                explanation=rf.get("explanation"),
                recommendation=rf.get("recommendation"),
                suggestion=rf.get("suggestion") or rf.get("fix"),
                cwe_id=rf.get("cwe_id"),
                cvss_score=cvss_score,
                exploitability=exploitability,
                false_positive_probability=0.03,
            )
        )

    return findings


def merge_findings(
    heuristic_findings: List[Finding],
    llm_findings: List[Finding],
) -> List[Finding]:
    """
    Intelligently merges deterministic heuristic findings with AI findings.
    Enriches heuristic findings with LLM explanations/suggestions on overlap.
    Retains all unique findings from both sources.
    """
    if not llm_findings:
        return list(heuristic_findings)
    if not heuristic_findings:
        return list(llm_findings)

    merged: List[Finding] = []
    used_llm_indices = set()

    for hf in heuristic_findings:
        enriched_hf = hf.model_copy()
        # Look for matching LLM finding on the same line or same category
        for l_idx, lf in enumerate(llm_findings):
            if l_idx in used_llm_indices:
                continue

            same_line = (hf.line is not None and lf.line is not None and hf.line == lf.line)
            same_cat = (hf.category.lower() == lf.category.lower())

            if same_line or (same_cat and (hf.line is None or lf.line is None)):
                # Enrich heuristic finding with deeper LLM explanation & suggestion
                if lf.explanation and (not enriched_hf.explanation or len(lf.explanation) > len(enriched_hf.explanation)):
                    enriched_hf.explanation = lf.explanation
                if lf.recommendation and (not enriched_hf.recommendation or len(lf.recommendation) > len(enriched_hf.recommendation)):
                    enriched_hf.recommendation = lf.recommendation
                if lf.suggestion and not enriched_hf.suggestion:
                    enriched_hf.suggestion = lf.suggestion
                if lf.cwe_id and not enriched_hf.cwe_id:
                    enriched_hf.cwe_id = lf.cwe_id

                used_llm_indices.add(l_idx)
                break

        merged.append(enriched_hf)

    # Add remaining unique LLM findings
    for l_idx, lf in enumerate(llm_findings):
        if l_idx not in used_llm_indices:
            merged.append(lf)

    return merged


def compute_composite_score(
    findings: List[Finding],
    llm_score: Optional[float] = None,
    heuristic_score: Optional[float] = None,
) -> float:
    """
    Calculates composite quality score based on severity deductions and calibrated scores.
    """
    if not findings:
        return 100.0

    score = 100.0
    for f in findings:
        if f.severity == SeverityEnum.CRITICAL:
            score -= 35.0
        elif f.severity == SeverityEnum.HIGH:
            score -= 20.0
        elif f.severity == SeverityEnum.MEDIUM:
            score -= 10.0
        elif f.severity == SeverityEnum.LOW:
            score -= 5.0
        elif f.severity == SeverityEnum.INFO:
            score -= 2.0

    computed_score = max(0.0, min(100.0, score))

    # If LLM or heuristic provided a score, take the most conservative (lowest)
    candidates = [computed_score]
    if llm_score is not None and 0.0 <= llm_score <= 100.0:
        candidates.append(llm_score)
    if heuristic_score is not None and 0.0 <= heuristic_score <= 100.0:
        candidates.append(heuristic_score)

    return round(min(candidates), 1)
