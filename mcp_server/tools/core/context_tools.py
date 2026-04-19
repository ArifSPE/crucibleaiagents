from __future__ import annotations

import json
import mimetypes
import os
import re
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from fastmcp import FastMCP

from mcp_server.tool_registry import MCPToolSpec


@dataclass(frozen=True)
class WorkspaceAccessPolicy:
    roots: tuple[Path, ...]
    max_file_bytes: int
    max_list_entries: int
    allowed_extensions: frozenset[str]


def _parse_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = (os.getenv(name, str(default)) or str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _default_root_candidates() -> list[Path]:
    candidates = [
        Path(os.getenv("MCP_RESOURCE_MOUNT_PATH", "/mnt/mcp-resources")),
        Path(os.getenv("MCP_PRIMARY_WORKSPACE_ROOT", "/workspace")),
        Path.cwd(),
    ]
    resolved: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            normalized = candidate.expanduser().resolve()
        except Exception:
            continue
        key = str(normalized)
        if key in seen:
            continue
        seen.add(key)
        resolved.append(normalized)
    return resolved


def _load_policy() -> WorkspaceAccessPolicy:
    roots_raw = (os.getenv("MCP_RESOURCE_ROOTS", "") or "").strip()
    configured_roots = [item.strip() for item in roots_raw.split(",") if item.strip()] if roots_raw else []

    roots: list[Path] = []
    seen: set[str] = set()
    source_values = configured_roots or [str(path) for path in _default_root_candidates()]

    for value in source_values:
        try:
            resolved = Path(value).expanduser().resolve()
        except Exception:
            continue
        if not resolved.exists() or not resolved.is_dir():
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        roots.append(resolved)

    if not roots:
        roots = [Path.cwd().resolve()]

    extensions_raw = (os.getenv("MCP_RESOURCE_ALLOWED_EXTENSIONS", "") or "").strip()
    allowed_extensions = frozenset(
        part.lower() if part.startswith(".") else f".{part.lower()}"
        for part in [item.strip() for item in extensions_raw.split(",") if item.strip()]
    )

    return WorkspaceAccessPolicy(
        roots=tuple(roots),
        max_file_bytes=_parse_int_env("MCP_RESOURCE_MAX_FILE_BYTES", 1_048_576, 1024, 10_485_760),
        max_list_entries=_parse_int_env("MCP_RESOURCE_MAX_LIST_ENTRIES", 200, 10, 1000),
        allowed_extensions=allowed_extensions,
    )


def _is_within_roots(path: Path, roots: tuple[Path, ...]) -> bool:
    try:
        resolved = path.expanduser().resolve(strict=False)
    except Exception:
        return False

    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _resolve_path(path_value: str, policy: WorkspaceAccessPolicy) -> Path:
    candidate_text = (path_value or "").strip()
    if not candidate_text:
        raise ValueError("filepath is required")

    requested = Path(candidate_text).expanduser()
    candidates: list[Path] = []

    if requested.is_absolute():
        candidates.append(requested)
    else:
        for root in policy.roots:
            candidates.append(root / requested)

    safe_candidates = [candidate.resolve(strict=False) for candidate in candidates if _is_within_roots(candidate, policy.roots)]
    if not safe_candidates:
        raise ValueError("Access denied - path outside MCP_RESOURCE_ROOTS")

    for candidate in safe_candidates:
        if candidate.exists():
            return candidate

    return safe_candidates[0]


def _display_path(path: Path, policy: WorkspaceAccessPolicy) -> str:
    resolved = path.resolve(strict=False)
    for root in policy.roots:
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            continue
    return resolved.name


def _ensure_file_is_readable(path: Path, policy: WorkspaceAccessPolicy) -> None:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {_display_path(path, policy)}")
    if not path.is_file():
        raise ValueError(f"Not a file: {_display_path(path, policy)}")

    suffix = path.suffix.lower()
    if policy.allowed_extensions and suffix not in policy.allowed_extensions:
        raise ValueError(
            f"File extension '{suffix or '<none>'}' is not allowed by MCP_RESOURCE_ALLOWED_EXTENSIONS"
        )

    size = path.stat().st_size
    if size > policy.max_file_bytes:
        raise ValueError(
            f"File exceeds MCP_RESOURCE_MAX_FILE_BYTES ({size} bytes > {policy.max_file_bytes} bytes)"
        )


def _clean_extracted_text(value: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in (value or "").replace("\x00", "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml")

    root = ElementTree.fromstring(document_xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    lines: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        fragments = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        combined = "".join(fragments).strip()
        if combined:
            lines.append(combined)

    extracted = _clean_extracted_text("\n".join(lines))
    if extracted:
        return extracted

    fallback = document_xml.decode("utf-8", errors="replace")
    return _clean_extracted_text(re.sub(r"<[^>]+>", " ", fallback))


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        extracted_pages = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                extracted_pages.append(page_text)

        combined = _clean_extracted_text("\n".join(extracted_pages))
        if combined:
            return combined
    except Exception:
        pass

    raw_bytes = path.read_bytes()
    extracted_segments: list[str] = []

    for stream_bytes in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", raw_bytes, re.S):
        candidate_streams = [stream_bytes]
        try:
            candidate_streams.append(zlib.decompress(stream_bytes))
        except Exception:
            pass

        for candidate in candidate_streams:
            decoded = candidate.decode("latin-1", errors="ignore")
            matches = re.findall(r"\(([^()]*)\)\s*T[Jj]", decoded)
            if matches:
                extracted_segments.extend(matches)

    if not extracted_segments:
        decoded_full = raw_bytes.decode("latin-1", errors="ignore")
        extracted_segments = re.findall(r"\(([^()]*)\)", decoded_full)

    cleaned = _clean_extracted_text("\n".join(extracted_segments))
    if cleaned:
        return cleaned

    raise ValueError("Unable to extract readable text from PDF")


def _read_file_text(path_value: str, policy: WorkspaceAccessPolicy) -> tuple[Path, str]:
    path = _resolve_path(path_value, policy)
    _ensure_file_is_readable(path, policy)

    suffix = path.suffix.lower()
    if suffix == ".docx":
        return path, _extract_docx_text(path)
    if suffix == ".pdf":
        return path, _extract_pdf_text(path)

    return path, path.read_text(encoding="utf-8", errors="replace")


def _list_directory(directory: str, policy: WorkspaceAccessPolicy, limit: int) -> list[dict[str, Any]]:
    path = _resolve_path(directory or ".", policy)
    if not path.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")
    if not path.is_dir():
        raise ValueError(f"Not a directory: {directory}")

    entries: list[dict[str, Any]] = []
    for item in sorted(path.iterdir(), key=lambda current: (not current.is_dir(), current.name.lower()))[:limit]:
        relative = _display_path(item, policy)
        entries.append(
            {
                "name": item.name,
                "path": relative,
                "uri": f"file://workspace/{relative}",
                "type": "directory" if item.is_dir() else "file",
                "size_bytes": item.stat().st_size if item.is_file() else 0,
                "mime_type": mimetypes.guess_type(item.name)[0] or "application/octet-stream",
            }
        )
    return entries


def _register_workspace_context_capabilities(mcp: FastMCP) -> None:
    @mcp.tool
    def list_workspace_files(directory: str = ".", max_entries: int = 100) -> dict[str, Any]:
        """List files from the configured MCP resource roots for safe exploration and summarization."""
        policy = _load_policy()
        limit = max(1, min(policy.max_list_entries, int(max_entries or 100)))

        try:
            entries = _list_directory(directory, policy, limit)
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "directory": directory,
                "available_roots": [root.as_posix() for root in policy.roots],
            }

        return {
            "status": "ok",
            "directory": directory,
            "available_roots": [root.as_posix() for root in policy.roots],
            "entry_count": len(entries),
            "entries": entries,
        }

    @mcp.tool
    def read_workspace_file(filepath: str, max_chars: int = 4000) -> dict[str, Any]:
        """Read a text file from configured safe roots for summarization and analysis workflows."""
        policy = _load_policy()
        try:
            path, content = _read_file_text(filepath, policy)
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "filepath": filepath,
                "available_roots": [root.as_posix() for root in policy.roots],
            }

        char_limit = max(200, min(20000, int(max_chars or 4000)))
        truncated = content[:char_limit]
        mime_type = mimetypes.guess_type(path.name)[0] or "text/plain"
        return {
            "status": "ok",
            "filepath": _display_path(path, policy),
            "uri": f"file://workspace/{_display_path(path, policy)}",
            "mime_type": mime_type,
            "size_bytes": path.stat().st_size,
            "truncated": len(content) > len(truncated),
            "content": truncated,
        }

    @mcp.resource("config://workspace/policy")
    def workspace_policy_resource() -> str:
        """Return the active workspace resource security policy."""
        policy = _load_policy()
        payload = {
            "roots": [root.as_posix() for root in policy.roots],
            "max_file_bytes": policy.max_file_bytes,
            "max_list_entries": policy.max_list_entries,
            "allowed_extensions": sorted(policy.allowed_extensions),
            "read_only": True,
        }
        return json.dumps(payload, indent=2)

    @mcp.resource("file://workspace/{filepath}")
    def workspace_file_resource(filepath: str) -> str:
        """Read a workspace file as an MCP resource using the configured read-only safe roots."""
        policy = _load_policy()
        _path, content = _read_file_text(filepath, policy)
        return content

    @mcp.prompt
    def summarize_workspace_file(filepath: str, audience: str = "engineering") -> str:
        """Generate a reusable summarization prompt for a workspace file."""
        return (
            f"Summarize the workspace file '{filepath}' for a {audience} audience. "
            "Include a short overview, key findings, important risks, and recommended next steps."
        )

    @mcp.prompt
    def security_review_file(filepath: str, change_context: str = "general review") -> list[dict[str, Any]]:
        """Generate a security-focused prompt for reviewing a workspace file."""
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        f"Perform a security review of '{filepath}' in the context of {change_context}. "
                        "Check input validation, authz/authn, secrets handling, path traversal, command execution, "
                        "and data exposure risks. Return prioritized remediation guidance."
                    ),
                },
            }
        ]


TOOL_SPECS = [
    MCPToolSpec(
        name="workspace_context",
        description="Secure workspace file access, resources, and prompt templates for summarization workflows",
        register=_register_workspace_context_capabilities,
        version="1.1.0",
        tags=("core", "resource", "prompt", "security"),
        risk_level="medium",
    )
]
