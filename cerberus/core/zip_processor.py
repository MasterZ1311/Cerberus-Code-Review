"""
Safe ZIP Archive Processor for cerberus</> Multi-Agent Code Review.
Safely inspects, filters, and extracts code files from .zip archives with
protection against Zip-Slip, Zip-Bombs, and binary files.
"""

import io
import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

logger = logging.getLogger("cerberus.core.zip_processor")

# Security and Resource Limits
MAX_ZIP_ARCHIVE_BYTES = 25 * 1024 * 1024  # 25 MB archive size cap
MAX_TOTAL_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_SINGLE_FILE_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_EXTRACTED_CODE_FILES = 150  # Cap on files to prevent excessive agent load
MAX_NESTING_DEPTH = 15  # Guard against deep recursive directory bombs

EXTENSION_TO_LANGUAGE: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rs": "rust",
    ".php": "php",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
}

IGNORED_DIR_NAMES: Set[str] = {
    "__pycache__",
    ".git",
    ".github",
    ".vscode",
    ".idea",
    "node_modules",
    "venv",
    ".venv",
    "env",
    ".env",
    "dist",
    "build",
    "target",
    "bin",
    "obj",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    ".eggs",
    "site-packages",
    "vendor",
}

BINARY_EXTENSIONS: Set[str] = {
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".svg",
    ".pdf",
    ".doc",
    ".docx",
    ".zip",
    ".tar",
    ".gz",
    ".whl",
    ".pyc",
    ".pyo",
    ".pyd",
    ".class",
    ".o",
    ".a",
    ".jar",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".wasm",
    ".ttf",
    ".woff",
    ".woff2",
}


class ExtractedCodeFile(BaseModel):
    """Represents a validated source code file extracted from a ZIP archive."""

    path: str = Field(description="Normalized relative path inside the zip archive")
    filename: str = Field(description="Basename of the file")
    content: str = Field(description="UTF-8 decoded source code text")
    language: str = Field(description="Detected programming language")
    size_bytes: int = Field(description="Size of the file in bytes")
    line_count: int = Field(description="Total lines of code")


class ZipExtractionResult(BaseModel):
    """Aggregated outcome of extracting a ZIP archive."""

    project_name: str
    total_entries_in_zip: int
    code_files: List[ExtractedCodeFile] = Field(default_factory=list)
    skipped_files: List[str] = Field(default_factory=list)
    total_code_lines: int = 0
    language_distribution: Dict[str, int] = Field(default_factory=dict)


def is_safe_zip_path(path_str: str, max_depth: int = MAX_NESTING_DEPTH) -> bool:
    """
    Guards against Zip Slip (directory traversal attacks) and malicious entry naming.
    Rejects absolute paths, Windows drive references, null bytes, URL-encoded traversal,
    and paths exceeding maximum nesting depth.
    """
    if not path_str or "\0" in path_str:
        return False
    clean = path_str.replace("\\", "/")
    if "%2e" in clean.lower() or "%2f" in clean.lower():
        return False
    if clean.startswith("/"):
        return False
    if len(clean) >= 2 and clean[1] == ":":
        return False
    parts = clean.split("/")
    if ".." in parts:
        return False
    non_empty_parts = [p for p in parts if p and p != "."]
    if len(non_empty_parts) > max_depth:
        return False
    return True


def is_symlink_entry(info: zipfile.ZipInfo) -> bool:
    """Detects Unix symbolic links within zip archive headers (mode 0o120000)."""
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def detect_language_from_path(filename: str) -> Optional[str]:
    """Detects programming language from file extension."""
    suffix = Path(filename).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(suffix)


def is_ignored_path(path_str: str) -> bool:
    """Checks whether the file is in an ignored directory or has an ignored extension."""
    clean = path_str.replace("\\", "/")
    parts = clean.split("/")
    for p in parts[:-1]:
        if p in IGNORED_DIR_NAMES or p.startswith("."):
            return True
    filename = parts[-1]
    if filename.startswith("."):
        return True
    ext = Path(filename).suffix.lower()
    if ext in BINARY_EXTENSIONS:
        return True
    return False


def extract_code_from_zip(
    zip_source: bytes | io.BytesIO | str | Path,
    project_name: Optional[str] = None,
    max_files: int = MAX_EXTRACTED_CODE_FILES,
    max_total_bytes: int = MAX_TOTAL_UNCOMPRESSED_BYTES,
) -> ZipExtractionResult:
    """
    Safely inspects and extracts source code files from a ZIP archive.

    Args:
        zip_source: Raw bytes, BytesIO buffer, or filesystem path to .zip file.
        project_name: Optional custom project identifier.
        max_files: Maximum code files to extract before capping.
        max_total_bytes: Cumulative uncompressed byte limit for zip bomb protection.

    Returns:
        ZipExtractionResult containing all validated code files and metadata.

    Raises:
        ValueError: If archive is corrupt, malicious (Zip Slip/Bomb), or invalid.
    """
    archive_file: Any
    if isinstance(zip_source, (str, Path)):
        p = Path(zip_source)
        if not p.exists():
            raise ValueError(f"ZIP file not found at path: {zip_source}")
        if p.stat().st_size > MAX_ZIP_ARCHIVE_BYTES:
            raise ValueError(
                f"ZIP archive size ({p.stat().st_size} bytes) exceeds safety maximum of {MAX_ZIP_ARCHIVE_BYTES} bytes."
            )
        project_name = project_name or p.stem
        archive_file = str(p)
    elif isinstance(zip_source, bytes):
        if len(zip_source) > MAX_ZIP_ARCHIVE_BYTES:
            raise ValueError(
                f"ZIP archive size ({len(zip_source)} bytes) exceeds safety maximum of {MAX_ZIP_ARCHIVE_BYTES} bytes."
            )
        archive_file = io.BytesIO(zip_source)
        project_name = project_name or "uploaded_project"
    else:
        archive_file = zip_source
        project_name = project_name or "uploaded_project"

    if not zipfile.is_zipfile(archive_file):
        raise ValueError("Provided file is not a valid ZIP archive.")

    extracted_files: List[ExtractedCodeFile] = []
    skipped_files: List[str] = []
    seen_entries: Set[str] = set()
    accumulated_bytes = 0
    total_entries = 0
    lang_dist: Dict[str, int] = {}
    total_lines = 0

    with zipfile.ZipFile(archive_file, "r") as zf:
        infolist = zf.infolist()
        total_entries = len(infolist)

        for info in infolist:
            # Skip directories
            if info.is_dir() or info.filename.endswith("/") or info.filename.endswith("\\"):
                continue

            arcname = info.filename.replace("\\", "/")

            # Security check: Symlink rejection
            if is_symlink_entry(info):
                logger.warning(f"Rejected symbolic link entry in zip archive: {arcname}")
                skipped_files.append(f"{arcname} (rejected symlink)")
                continue

            # Security check: Zip Slip traversal & nesting depth
            if not is_safe_zip_path(arcname):
                logger.warning(f"Rejected potentially malicious zip entry (Zip Slip): {arcname}")
                skipped_files.append(f"Skipped {arcname}: unsafe path")
                continue

            # Security check: Duplicate entry rejection
            if arcname in seen_entries:
                logger.warning(f"Skipping duplicate zip entry: {arcname}")
                skipped_files.append(f"{arcname} (duplicate entry)")
                continue
            seen_entries.add(arcname)

            # Skip ignored directories and files
            if is_ignored_path(arcname):
                skipped_files.append(f"{arcname} (ignored path/extension)")
                continue

            # Detect language
            lang = detect_language_from_path(arcname)
            if not lang:
                skipped_files.append(f"{arcname} (unsupported code extension)")
                continue

            # Security check: Header declared single file size cap
            if info.file_size > MAX_SINGLE_FILE_BYTES:
                logger.warning(f"Skipping oversized file {arcname} ({info.file_size} bytes)")
                skipped_files.append(f"{arcname} (exceeds single file size limit)")
                continue

            # Read file content safely using bounded chunk streaming to defeat deceptive header zip bombs
            try:
                chunks = []
                current_file_bytes = 0
                with zf.open(info, "r") as entry_stream:
                    while True:
                        chunk = entry_stream.read(65536)  # 64 KB chunk
                        if not chunk:
                            break
                        current_file_bytes += len(chunk)
                        accumulated_bytes += len(chunk)
                        if current_file_bytes > MAX_SINGLE_FILE_BYTES:
                            logger.warning(
                                f"File {arcname} exceeded single file limit during extraction ({current_file_bytes} bytes)"
                            )
                            break
                        if accumulated_bytes > max_total_bytes:
                            logger.warning(
                                "Uncompressed ZIP size exceeded maximum safety threshold. Halting extraction."
                            )
                            break
                        chunks.append(chunk)

                if current_file_bytes > MAX_SINGLE_FILE_BYTES:
                    skipped_files.append(f"{arcname} (exceeds single file size limit)")
                    continue
                if accumulated_bytes > max_total_bytes:
                    skipped_files.append(f"{arcname} (halted: total uncompressed size limit reached)")
                    break

                raw_bytes = b"".join(chunks)

                # Attempt UTF-8, then fallback to latin-1
                try:
                    content_text = raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    content_text = raw_bytes.decode("latin-1", errors="replace")

                lines = content_text.count("\n") + (1 if content_text else 0)
                extracted_files.append(
                    ExtractedCodeFile(
                        path=arcname,
                        filename=Path(arcname).name,
                        content=content_text,
                        language=lang,
                        size_bytes=len(raw_bytes),
                        line_count=lines,
                    )
                )

                total_lines += lines
                lang_dist[lang] = lang_dist.get(lang, 0) + 1

                if len(extracted_files) >= max_files:
                    logger.info(f"Reached maximum code file cap ({max_files}). Remaining files skipped.")
                    break

            except Exception as e:
                logger.warning(f"Error reading zip file entry {arcname}: {e}")
                skipped_files.append(f"{arcname} (read error: {e})")

    return ZipExtractionResult(
        project_name=project_name,
        total_entries_in_zip=total_entries,
        code_files=extracted_files,
        skipped_files=skipped_files,
        total_code_lines=total_lines,
        language_distribution=lang_dist,
    )
