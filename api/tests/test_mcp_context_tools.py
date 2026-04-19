from __future__ import annotations

import importlib
import sys
import types
import zipfile
from pathlib import Path


def _load_context_tools_module():
    fake_fastmcp = types.ModuleType("fastmcp")

    class FakeFastMCP:  # pragma: no cover - lightweight import stub only
        pass

    fake_fastmcp.FastMCP = FakeFastMCP
    sys.modules.setdefault("fastmcp", fake_fastmcp)

    if "mcp_server.tools.core.context_tools" in sys.modules:
        return importlib.reload(sys.modules["mcp_server.tools.core.context_tools"])
    return importlib.import_module("mcp_server.tools.core.context_tools")


def test_resolve_path_prefers_existing_file_across_roots(tmp_path, monkeypatch):
    context_tools = _load_context_tools_module()

    workspace_root = tmp_path / "workspace"
    mounted_root = tmp_path / "mounted"
    workspace_root.mkdir()
    mounted_root.mkdir()

    target_file = mounted_root / "825shaikh-resumeVers2.docx"
    target_file.write_bytes(b"placeholder")

    monkeypatch.setenv("MCP_RESOURCE_ROOTS", f"{workspace_root},{mounted_root}")
    monkeypatch.setenv("MCP_RESOURCE_ALLOWED_EXTENSIONS", ".docx")

    policy = context_tools._load_policy()
    resolved = context_tools._resolve_path("825shaikh-resumeVers2.docx", policy)

    assert resolved == target_file.resolve()


def test_read_file_text_extracts_text_from_docx(tmp_path, monkeypatch):
    context_tools = _load_context_tools_module()

    resources_root = tmp_path / "resources"
    resources_root.mkdir()
    docx_path = resources_root / "resume.docx"

    with zipfile.ZipFile(docx_path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """
            <w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">
              <w:body>
                <w:p><w:r><w:t>Arif Shaikh Resume</w:t></w:r></w:p>
                <w:p><w:r><w:t>AI Engineer</w:t></w:r></w:p>
              </w:body>
            </w:document>
            """,
        )

    monkeypatch.setenv("MCP_RESOURCE_ROOTS", str(resources_root))
    monkeypatch.setenv("MCP_RESOURCE_ALLOWED_EXTENSIONS", ".docx")

    policy = context_tools._load_policy()
    _path, content = context_tools._read_file_text("resume.docx", policy)

    assert "Arif Shaikh Resume" in content
    assert "AI Engineer" in content
    assert "<w:document" not in content
    assert "PK" not in content[:20]


def test_read_file_text_extracts_text_from_pdf(tmp_path, monkeypatch):
    context_tools = _load_context_tools_module()

    resources_root = tmp_path / "resources"
    resources_root.mkdir()
    pdf_path = resources_root / "resume.pdf"
    pdf_path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Length 70 >>\nstream\n"
        b"BT\n/F1 12 Tf\n72 720 Td\n(Arif Shaikh PDF Resume) Tj\n(Cloud Architect) Tj\nET\n"
        b"endstream\nendobj\n%%EOF\n"
    )

    monkeypatch.setenv("MCP_RESOURCE_ROOTS", str(resources_root))
    monkeypatch.setenv("MCP_RESOURCE_ALLOWED_EXTENSIONS", ".pdf")

    policy = context_tools._load_policy()
    _path, content = context_tools._read_file_text("resume.pdf", policy)

    assert "Arif Shaikh PDF Resume" in content
    assert "Cloud Architect" in content
