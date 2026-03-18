"""Lightweight platform tools for runner agents.

This module provides a compatibility surface from the legacy SDK while keeping
safe defaults for the new architecture.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_used: Optional[int] = None
    latency_ms: Optional[float] = None
    provider: Optional[str] = None


class LLMProvider:
    OLLAMA = "ollama"
    PLATFORM = "platform"


class LLMClient:
    def __init__(self, provider: str = LLMProvider.OLLAMA, model: Optional[str] = None, base_url: Optional[str] = None):
        self.provider = provider
        self.model = model or os.getenv("LLM_MODEL", "llama3.1")
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.logger = logging.getLogger("runner.tools.llm")

    def chat(self, message: str, system: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 1024) -> LLMResponse:
        # Minimal compatibility behavior; can be upgraded to full provider routing.
        t0 = time.time()
        content = f"[stub-llm:{self.model}] {message}"
        return LLMResponse(content=content, model=self.model, latency_ms=(time.time() - t0) * 1000, provider=self.provider)


@dataclass
class ShellResult:
    stdout: str
    stderr: str
    exit_code: int
    command: str
    duration_ms: float


class ShellExecutor:
    def __init__(self, allowed_commands: Optional[list[str]] = None, timeout: int = 30):
        self.allowed_commands = set(allowed_commands or [])
        self.timeout = timeout
        self.logger = logging.getLogger("runner.tools.shell")

    def run(self, command: str, cwd: Optional[str] = None) -> ShellResult:
        program = command.split()[0] if command.strip() else ""
        if self.allowed_commands and program not in self.allowed_commands:
            raise ValueError(f"Command not allowed: {program}")

        t0 = time.time()
        proc = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=self.timeout)
        return ShellResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            command=command,
            duration_ms=(time.time() - t0) * 1000,
        )


@dataclass
class HTTPResponse:
    status_code: int
    body: str
    headers: Dict[str, Any]


class HTTPClient:
    def get(self, url: str, timeout: int = 10) -> HTTPResponse:
        import urllib.request
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return HTTPResponse(status_code=resp.getcode(), body=body, headers=dict(resp.headers.items()))


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Any] = {}

    def register(self, key: str, tool: Any):
        self._tools[key] = tool

    def get(self, key: str):
        return self._tools.get(key)


@dataclass
class ToolParameter:
    name: str
    description: str
    required: bool = False


@dataclass
class ToolDefinition:
    key: str
    description: str
    parameters: list[ToolParameter]
