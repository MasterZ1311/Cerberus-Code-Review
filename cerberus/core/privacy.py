"""
Privacy and Source Code Retention Enforcement for Cerberus.
Provides recursive redaction of source code, patches, and diffs across nested data structures.
"""

from typing import Any, Dict, Set

from pydantic import BaseModel

REDACTED_TEXT: str = "[REDACTED BY PRIVACY POLICY]"

# Field names across JSON schemas, AST models, findings, and requests that contain source code
SENSITIVE_CODE_KEYS: Set[str] = {
    "code",
    "code_snippet",
    "raw_code",
    "snippet",
    "source_code",
    "source",
    "patch",
    "diff",
    "unified_patch",
    "suggestion",
    "content",
    "file_content",
}


def redact_source_code_recursively(obj: Any) -> Any:
    """
    Recursively inspects and redacts raw source code and code snippets from any
    nested dictionary, list, Pydantic model, or object structure when RETAIN_SOURCE_CODE is False.
    Preserves all non-sensitive review metadata (scores, lines, categories, rules, recommendations).
    """
    if isinstance(obj, BaseModel):
        dumped = obj.model_dump()
        redacted = redact_source_code_recursively(dumped)
        return type(obj).model_validate(redacted)

    if isinstance(obj, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in obj.items():
            if k.lower() in SENSITIVE_CODE_KEYS:
                if isinstance(v, str) and v:
                    cleaned[k] = REDACTED_TEXT
                elif isinstance(v, (dict, list, tuple, set, BaseModel)):
                    cleaned[k] = redact_source_code_recursively(v)
                else:
                    cleaned[k] = REDACTED_TEXT if v is not None else None
            else:
                cleaned[k] = redact_source_code_recursively(v)
        return cleaned

    if isinstance(obj, list):
        return [redact_source_code_recursively(item) for item in obj]

    if isinstance(obj, tuple):
        return tuple(redact_source_code_recursively(item) for item in obj)

    if isinstance(obj, set):
        return {redact_source_code_recursively(item) for item in obj}

    return obj
